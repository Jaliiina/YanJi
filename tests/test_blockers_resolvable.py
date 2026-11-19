"""Whoever stops a plan (model, resolver or a program check), the user can answer on the plan."""

import numpy as np
import pandas as pd
import pytest

from yanji import agent, db
from yanji.contracts import ChatRequest, ImportOptions, RunConfirm, SkillParams
from yanji.data import Blocker, DataError, import_bytes, load_frame
from yanji.flask_routes import confirm_run
from yanji.worker import run_one

IDS = [f"S{i}" for i in range(12)]


def abundance(pid, name="abundance.tsv"):
    table = pd.DataFrame(
        [np.arange(1, 13), np.arange(12, 0, -1), [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8]],
        index=["X", "Y", "Z"],
        columns=IDS,
    )
    table.index.name = "feature_id"
    return import_bytes(pid, name, table.to_csv(sep="\t").encode(), ImportOptions(unit="counts"))


def clinical(pid, frame, name="clinical.csv"):
    return import_bytes(
        pid, name, frame.to_csv(index=False).encode(), ImportOptions(kind="metadata")
    )


def answerable(plan):
    """The invariant: a stored question always comes with a way to answer it."""
    cards = plan["clarifications"]
    assert plan["questions"] == [card["prompt"] for card in cards]
    for card in cards:
        if card["kind"] == "select":
            assert card["target"] and len(card["items"]) >= card["min_pick"]
        if card["kind"] == "samples":
            assert card["dataset_id"]
    return cards


def answer(client, pid, plan, answers, status=201):
    response = client.post(
        f"/api/v1/projects/{pid}/plans/{plan['id']}/clarify", json={"answers": answers}
    )
    assert response.status_code == status, response.text
    return response.json()


def test_unmatched_samples_are_settled_on_the_plan(client, project, monkeypatch):
    pid = project["id"]
    abundance(pid)
    # S10 is recorded under another name and S11 has no record at all.
    clinical(
        pid,
        pd.DataFrame({"sample_id": IDS[:10] + ["S10_combined"], "年龄": list(range(20, 31))}),
    )
    calls = []

    def model(_messages):
        calls.append(1)
        return {
            "objective": "x",
            "summary": "年龄与各菌种的相关。",
            "steps": [
                {
                    "id": "s1",
                    "skill": "taxa_association",
                    "reason": "回答年龄与菌种的关系",
                    "parameters": {"variable": "年龄"},
                }
            ],
            "questions": [],
        }

    monkeypatch.setattr(agent, "model_json", model)
    first = agent.create_plan(
        pid, ChatRequest(message="年龄和各个菌种富集程度相关性", include_report=False)
    )
    (card,) = answerable(first)
    assert card["kind"] == "samples" and card["source"] == "check"
    assert [(item["value"], item["hint"]) for item in card["items"]] == [
        ("S10", "S10_combined"),
        ("S11", ""),
    ]
    assert card["choices"] == ["S10_combined"]
    with pytest.raises(DataError):
        confirm_run(pid, RunConfirm(plan_id=first["id"]))
    wrong = [{"id": card["id"], "mapping": {"S11": "S0"}}]
    assert "还没有被使用" in answer(client, pid, first, wrong, 422)["detail"]
    second = answer(client, pid, first, [{"id": card["id"], "mapping": {"S10": "S10_combined"}}])
    assert not second["questions"] and not second["clarifications"]
    # The checks were answered, so the design is kept and the model is not asked again.
    assert len(calls) == 1 and second["steps"] == first["steps"]
    assert second["origin"] == "model"
    assert second["snapshot"]["study"]["excluded_samples"] == ["S11"]
    assert "S10" in load_frame(db.get(second["snapshot"]["datasets"]["metadata"])).index
    assert "S11" in second["clarification_log"][-1]["answer"]
    run = confirm_run(pid, RunConfirm(plan_id=second["id"]))
    run_one(run)
    result = db.get(run["id"])["results"][-1]
    assert result["status"] == "success", result["summary"]
    assert result["metrics"]["samples"] == 11


def test_group_comparison_is_set_up_by_answering(client, example):
    pid = example["id"]
    db.update(pid, study={})
    first = agent.create_plan(pid, ChatRequest(message="比较两组", mode="comparison"))
    cards = {card["target"]: card for card in answerable(first)}
    assert set(cards) == {"study.group_column", "study.independent"}
    assert [item["value"] for item in cards["study.group_column"]["items"]] == ["group"]
    picks = [
        {"id": cards["study.group_column"]["id"], "picked": ["group"]},
        {"id": cards["study.independent"]["id"], "picked": ["no"]},
    ]
    # A design the platform cannot test stays stopped, and can still be answered.
    paired = answer(client, pid, first, picks)
    assert [card["target"] for card in answerable(paired)] == ["study.independent"]
    ready = answer(
        client, pid, paired, [{"id": paired["clarifications"][0]["id"], "picked": ["yes"]}]
    )
    assert not ready["questions"] and ready["origin"] == "guided"
    assert ready["snapshot"]["study"] == {
        "group_column": "group",
        "independent": True,
        "excluded_samples": [],
    }
    assert confirm_run(pid, RunConfirm(plan_id=ready["id"]))["status"] == "queued"


def test_two_groups_are_chosen_from_the_real_values(client, project):
    pid = project["id"]
    abundance(pid)
    clinical(pid, pd.DataFrame({"sample_id": IDS, "arm": ["A", "B", "C"] * 4}))
    study = {"group_column": "arm", "independent": True, "excluded_samples": []}
    assert client.put(f"/api/v1/projects/{pid}/study", json=study).status_code == 200
    first = agent.create_plan(
        pid,
        ChatRequest(
            message="组间差异", mode="skill", skill_id="differential", include_report=False
        ),
    )
    (card,) = answerable(first)
    assert card["target"] == "param.groups" and card["min_pick"] == 2
    assert [item["label"] for item in card["items"]] == [
        "A（4 个样本）",
        "B（4 个样本）",
        "C（4 个样本）",
    ]
    answer(client, pid, first, [{"id": card["id"], "picked": ["A"]}], 422)
    ready = answer(client, pid, first, [{"id": card["id"], "picked": ["C", "A"]}])
    assert not ready["questions"]
    step = ready["steps"][-1]
    assert (step["parameters"]["group_a"], step["parameters"]["group_b"]) == ("C", "A")


def test_missing_variable_and_duplicate_tables_are_picked(client, project):
    pid = project["id"]
    frame = pd.DataFrame({"sample_id": IDS, "Calcium": range(12), "note": ["a"] * 12})
    files = [
        abundance(pid)["id"],
        clinical(pid, frame)["id"],
        clinical(pid, frame, "clinical-old.csv")["id"],
    ]
    first = agent.create_plan(
        pid,
        ChatRequest(
            message="指标与菌群",
            mode="skill",
            skill_id="taxa_association",
            dataset_ids=files,
            include_report=False,
            parameters=SkillParams(variable="不存在"),
        ),
    )
    cards = {card["target"]: card for card in answerable(first)}
    assert set(cards) == {"inputs", "param.variable"}
    assert [item["value"] for item in cards["param.variable"]["items"]] == ["Calcium"]
    assert [item["value"] for item in cards["inputs"]["items"]] == files[1:]
    keep = files[1]
    ready = answer(
        client,
        pid,
        first,
        [
            {"id": cards["inputs"]["id"], "picked": [keep]},
            {"id": cards["param.variable"]["id"], "picked": ["Calcium"]},
        ],
    )
    assert not ready["questions"]
    assert ready["snapshot"]["datasets"]["metadata"] == keep
    assert ready["steps"][-1]["parameters"]["variable"] == "Calcium"
    assert confirm_run(pid, RunConfirm(plan_id=ready["id"]))["status"] == "queued"


def test_level_order_asked_by_a_check_keeps_the_step(client, project):
    pid = project["id"]
    levels = ["重度", "中度", "轻度"]
    rows = ["编号\tCalcium\t诊断"] + [f"{i + 1}\t{10 + i}\t{levels[i // 3]}" for i in range(9)]
    table = import_bytes(pid, "cohort.tsv", "\n".join(rows).encode(), ImportOptions(kind="table"))
    base = f"/api/v1/projects/{pid}/datasets/{table['id']}/understanding"
    body = {"fields": [{"name": "诊断", "role": "ordinal"}], "expected_revision": 0}
    assert client.put(base, json=body).status_code == 200
    first = agent.create_plan(
        pid,
        ChatRequest(
            message="钙与诊断等级",
            mode="skill",
            skill_id="table_correlation",
            include_report=False,
            parameters=SkillParams(dataset_id=table["id"], x="Calcium", y="诊断"),
        ),
    )
    (card,) = answerable(first)
    assert card["kind"] == "encoding" and card["values"] == levels
    ready = answer(client, pid, first, [{"id": card["id"], "encoding": " > ".join(levels)}])
    assert not ready["questions"] and ready["steps"] == first["steps"]
    run = confirm_run(pid, RunConfirm(plan_id=ready["id"]))
    run_one(run)
    assert db.get(run["id"])["results"][-1]["status"] == "success"


def test_unsupported_adjustment_can_be_accepted(client, example):
    pid = example["id"]
    first = agent.create_plan(
        pid, ChatRequest(message="校正年龄这个协变量后看菌群组成", mode="overview")
    )
    (card,) = answerable(first)
    assert card["target"] == "accept"
    declined = answer(client, pid, first, [{"id": card["id"], "picked": ["no"]}])
    assert [item["target"] for item in answerable(declined)] == ["accept"]
    ready = answer(
        client, pid, declined, [{"id": declined["clarifications"][0]["id"], "picked": ["yes"]}]
    )
    assert not ready["questions"] and ready["accepted"] == ["adjustment_unsupported"]
    assert confirm_run(pid, RunConfirm(plan_id=ready["id"]))["status"] == "queued"


def test_a_dead_end_is_handed_to_the_planner_with_the_users_words(client, example, monkeypatch):
    from yanji.examples import frames, raw

    pid = example["id"]
    _, meta, _ = frames()
    meta.loc[1, "subject_id"] = meta.loc[0, "subject_id"]
    import_bytes(pid, "metadata.tsv", raw(meta, False), ImportOptions(kind="metadata"))
    first = agent.create_plan(pid, ChatRequest(message="比较独立两组", mode="comparison"))
    (card,) = answerable(first)
    assert card["kind"] == "text" and card["required"] and "重复受试者" in card["prompt"]
    answer(client, pid, first, [{"id": card["id"], "text": " "}], 422)
    seen = []

    def model(messages):
        seen.append(messages[1]["content"])
        plan = agent.guided(ChatRequest(message="x", mode="overview"), pid).model_dump()
        return {**plan, "summary": "按你的说明只做描述。"}

    monkeypatch.setattr(agent, "model_json", model)
    second = answer(client, pid, first, [{"id": card["id"], "text": "只做描述性概览"}])
    assert "只做描述性概览" in seen[0] and "重复受试者" in seen[0]
    assert second["origin"] == "model" and not second["questions"]


def test_a_check_nobody_planned_for_still_gets_an_answer_box(example, monkeypatch):
    monkeypatch.setattr(
        agent,
        "checks",
        lambda *_args, **_kwargs: [
            Blocker("以后新增的某项检查没有通过。", "brand_new", steps=["s1"])
        ],
    )
    plan = agent.create_plan(example["id"], ChatRequest(message="概览", mode="overview"))
    (card,) = answerable(plan)
    assert card["kind"] == "text" and card["required"] and card["code"] == "brand_new"
