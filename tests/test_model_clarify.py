import json

import numpy as np
import pytest

from yanji import agent, db
from yanji.contracts import ChatRequest, ImportOptions, RunConfirm, SkillParams
from yanji.data import import_bytes
from yanji.flask_routes import confirm_run
from yanji.worker import run_one

GOAL = "分析钙与自闭症严重程度的关系"
LEVELS = ["Autism（重度）", "Autism（中度）", "Autism（轻度）"]


def cohort(pid):
    rows = ["编号\tCalcium\tCARS 总分\tABC 总分\t诊断\t年龄"]
    for i in range(9):
        rows.append(f"{i + 1}\t{10 + i}\t{50 - 2 * i}\t{60 + i % 4}\t{LEVELS[i // 3]}\t{5 + i}")
    return import_bytes(pid, "cohort.tsv", "\n".join(rows).encode(), ImportOptions(kind="table"))


def asking(extra_questions=()):
    return {
        "objective": GOAL,
        "summary": "需要先确定严重程度用哪一列。",
        "steps": [{"id": "s1", "skill": "data_check", "reason": "等待补充"}],
        "questions": list(extra_questions),
        "clarifications": [
            {
                "id": "c1",
                "kind": "choice",
                "prompt": "“自闭症严重程度”希望用哪一个指标衡量？",
                "concept": "自闭症严重程度",
                "choices": ["CARS 总分", "ABC 总分", "诊断"],
            },
            {
                "id": "c2",
                "kind": "unit",
                "prompt": "Calcium 的检测单位是什么？",
                "field": "Calcium",
            },
            {
                "id": "c3",
                "kind": "encoding",
                "prompt": "“诊断”各等级由重到轻的顺序是什么？",
                "field": "诊断",
            },
            {"id": "c4", "kind": "text", "prompt": "样本类型是血清、头发还是其他？"},
            {"id": "c5", "kind": "unit", "prompt": "不存在的列的单位？", "field": "编造列"},
        ],
    }


def test_every_model_question_can_be_answered_and_replanned(client, project, monkeypatch):
    pid = project["id"]
    table = cohort(pid)
    seen = []

    def model(messages):
        log = json.loads(messages[1]["content"])["clarification_log"]
        seen.append(log)
        if not log:
            return asking()
        return {
            "objective": GOAL,
            "summary": "按你的说明，用 CARS 总分表示严重程度，计算它与钙的秩相关。",
            "steps": [
                {
                    "id": "s1",
                    "skill": "table_correlation",
                    "reason": "回答钙与严重程度的关系",
                    "parameters": {
                        "dataset_id": table["id"],
                        "x": "Calcium",
                        "y": "CARS 总分",
                    },
                }
            ],
            "questions": [],
        }

    monkeypatch.setattr(agent, "model_json", model)
    first = agent.create_plan(pid, ChatRequest(message=GOAL, include_report=False))
    cards = first["clarifications"]
    # A column choice becomes a real column picker; an unknown column falls back to text.
    assert [card["kind"] for card in cards] == [
        "bind_field",
        "unit",
        "encoding",
        "text",
        "text",
    ]
    assert [option["field"] for option in cards[0]["options"]] == [
        "CARS 总分",
        "ABC 总分",
        "诊断",
    ]
    assert cards[2]["values"] == LEVELS
    assert first["questions"] == [card["prompt"] for card in cards]
    with pytest.raises(ValueError):
        confirm_run(pid, RunConfirm(plan_id=first["id"]))
    answers = [
        {"id": "c1", "dataset_id": table["id"], "field": "CARS 总分"},
        {"id": "c2", "unit": "mg/L"},
        {"id": "c3", "encoding": " > ".join(LEVELS)},
        {"id": "c4", "text": "血清"},
        {"id": "c5", "text": ""},
    ]
    response = client.post(
        f"/api/v1/projects/{pid}/plans/{first['id']}/clarify",
        json={"answers": answers},
    )
    assert response.status_code == 201, response.text
    second = response.json()
    assert not second["questions"] and not second["clarifications"]
    log = {note["question"]: note["answer"] for note in seen[-1]}
    assert log["“自闭症严重程度”希望用哪一个指标衡量？"] == "使用列「CARS 总分」"
    assert log["样本类型是血清、头发还是其他？"] == "血清"
    assert log["不存在的列的单位？"] == "（未回答）"
    assert second["clarification_log"] == seen[-1]
    saved = {field["name"]: field for field in db.get(table["id"])["understanding"]["fields"]}
    assert saved["Calcium"]["unit"] == "mg/L"
    assert saved["CARS 总分"]["meaning"] == "自闭症严重程度"
    assert saved["诊断"]["role"] == "ordinal"
    run = confirm_run(pid, RunConfirm(plan_id=second["id"]))
    run_one(run)
    result = db.get(run["id"])["results"][-1]
    assert result["status"] == "success", result["summary"]
    assert np.isclose(result["metrics"]["rho"], -1)


def test_plain_model_questions_get_an_answer_box(project, monkeypatch):
    pid = project["id"]
    cohort(pid)
    body = asking(["请说明钙指标的测量含义"])
    body.pop("clarifications")
    monkeypatch.setattr(agent, "model_json", lambda _messages: dict(body))
    plan = agent.create_plan(pid, ChatRequest(message=GOAL, include_report=False))
    assert [(card["kind"], card["prompt"]) for card in plan["clarifications"]] == [
        ("text", "请说明钙指标的测量含义")
    ]


def test_ordinal_levels_can_be_rank_correlated_once_ordered(client, project):
    pid = project["id"]
    table = cohort(pid)
    base = f"/api/v1/projects/{pid}/datasets/{table['id']}/understanding"

    def plan():
        return agent.create_plan(
            pid,
            ChatRequest(
                message="钙与诊断等级",
                mode="skill",
                skill_id="table_correlation",
                include_report=False,
                parameters=SkillParams(dataset_id=table["id"], x="Calcium", y="诊断"),
            ),
        )

    unordered = {
        "fields": [{"name": "诊断", "role": "ordinal"}],
        "expected_revision": 0,
    }
    assert client.put(base, json=unordered).status_code == 200
    assert any("等级" in question for question in plan()["questions"])
    ordered = {
        "fields": [{"name": "诊断", "role": "ordinal", "encoding": " > ".join(LEVELS)}],
        "expected_revision": 1,
    }
    assert client.put(base, json=ordered).status_code == 200
    ready = plan()
    assert not ready["questions"]
    run = confirm_run(pid, RunConfirm(plan_id=ready["id"]))
    run_one(run)
    result = db.get(run["id"])["results"][-1]
    assert result["status"] == "success", result["summary"]
    # Calcium rises while the level code rises from 1 (重度) to 3 (轻度).
    assert result["metrics"]["samples"] == 9 and result["metrics"]["rho"] > 0.9
    assert any("等级顺序" in warning for warning in result["warnings"])
