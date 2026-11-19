"""Regression: the user's quartile question must execute grouped enrichment."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from yanji import agent, data, db, worker
from yanji.contracts import (
    AnalysisPlan,
    ChatRequest,
    ImportOptions,
    Preparation,
    RunConfirm,
    StudyConfig,
)
from yanji.flask_routes import confirm_run
from yanji.preparation import compile_cohorts, prepare

GOAL = "用镁含量进行分组，上四分位数和下四分位数分别为高低镁组，寻找每个组的富集菌种，并分别展示丰度top3"


@pytest.fixture
def inputs(project):
    pid = project["id"]
    ids = [f"S{i:02d}" for i in range(1, 26)]
    meta = pd.DataFrame(
        {
            "sample_id": ids + ["unmatched"],
            "Magnesium": list(range(1, 25)) + [""] + [99999],
            "age": [30] * 26,
        }
    )
    metadata = data.import_bytes(
        pid,
        "participants.tsv",
        meta.to_csv(sep="\t", index=False).encode(),
        ImportOptions(kind="metadata"),
    )
    matrix = pd.DataFrame(
        [np.linspace(0.9, 0.1, 25), np.linspace(0.1, 0.9, 25)],
        index=["low_bug", "high_bug"],
        columns=ids,
    )
    taxonomy = data.import_bytes(
        pid,
        "abundance.tsv",
        matrix.to_csv(sep="\t", index_label="feature").encode(),
        ImportOptions(kind="taxonomy", unit="fraction"),
    )
    return pid, metadata, taxonomy


def design(metadata):
    recipe = {
        "op": "quantile_group",
        "dataset_id": metadata["id"],
        "column": "Magnesium",
        "output": "Mg_group",
        "low_label": "低镁组",
        "high_label": "高镁组",
        "lower": 0.25,
        "upper": 0.75,
    }
    return {
        "objective": GOAL,
        "summary": "按镁上下四分位分组，排除中间区间；在派生队列比较高低组并各自排名。",
        "steps": [
            {
                "id": "s1",
                "skill": "prepare_cohort",
                "parameters": {"preparation": [recipe]},
            },
            {
                "id": "s2",
                "skill": "differential",
                "parameters": {"group_values": ["低镁组", "高镁组"]},
                "cohort_from": "s1",
                "depends_on": ["s1"],
            },
            {
                "id": "s3",
                "skill": "group_feature_summary",
                "parameters": {"top_n": 3},
                "cohort_from": "s1",
                "depends_on": ["s1"],
            },
        ],
    }


def test_model_repairs_continuous_substitution_and_executes_real_worker(inputs, monkeypatch):
    pid, metadata, taxonomy = inputs
    good = design(metadata)
    bad = {
        "objective": GOAL,
        "summary": "改用连续关联",
        "steps": [
            {
                "id": "s1",
                "skill": "taxa_association",
                "parameters": {"variable": "Magnesium"},
            }
        ],
    }
    calls = []

    def model(messages):
        calls.append(deepcopy(messages))
        return deepcopy(bad if len(calls) == 1 else good)

    monkeypatch.setattr(agent, "model_json", model)
    plan = agent.create_plan(
        pid,
        ChatRequest(
            message=GOAL,
            include_report=False,
            dataset_ids=[metadata["id"], taxonomy["id"]],
            study=StudyConfig(independent=True),
        ),
    )
    assert len(calls) == 2 and "派生队列" in calls[1][-1]["content"]
    assert not plan["questions"], plan["questions"]
    preview = plan["preparation_preview"][0]
    assert preview["included"] == 12 and preview["excluded"] == 14
    op = preview["operations"][0]
    assert op["low_threshold"] == 6.75 and op["high_threshold"] == 18.25
    assert op["counts"] == {"低镁组": 6, "高镁组": 6}
    assert not db.list_records("run", pid)
    run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
    worker.run_one(run)
    finished = db.get(run["id"], "run")
    assert finished["status"] == "completed" and not finished["partial"]
    preparation, differential, summary = finished["results"]
    assert preparation["metrics"]["included"] == 12
    assert differential["metrics"]["group_counts"] == {"低镁组": 6, "高镁组": 6}
    enriched = differential["metrics"]["enriched_by_group"]
    assert enriched["低镁组"][0]["feature"] == "low_bug"
    assert enriched["高镁组"][0]["feature"] == "high_bug"
    ranks = summary["metrics"]["top_by_group"]
    assert ranks["低镁组"][0]["index"] == "low_bug"
    assert ranks["高镁组"][0]["index"] == "high_bug"
    # Source data is never modified by an analysis-specific derived cohort.
    assert "Mg_group" not in data.load_frame(metadata)
    assert db.get(pid, "project")["study"] == {
        "group_column": None,
        "independent": False,
        "excluded_samples": [],
    }


def test_independence_answer_retains_recipe_and_does_not_replan(inputs, monkeypatch, client):
    pid, metadata, taxonomy = inputs
    monkeypatch.setattr(agent, "model_json", lambda _: deepcopy(design(metadata)))
    plan = agent.create_plan(pid, ChatRequest(message=GOAL, include_report=False))
    assert len(plan["clarifications"]) == 1
    assert plan["clarifications"][0]["code"] == "independence_unconfirmed"
    assert (
        client.post(f"/api/v1/projects/{pid}/runs", json={"plan_id": plan["id"]}).status_code == 422
    )

    def unexpected(_):
        raise AssertionError("Answering an independence check must not replace the design")

    monkeypatch.setattr(agent, "model_json", unexpected)
    response = client.post(
        f"/api/v1/projects/{pid}/plans/{plan['id']}/clarify",
        json={"answers": [{"id": plan["clarifications"][0]["id"], "picked": ["yes"]}]},
    )
    assert response.status_code == 201, response.text
    revised = response.json()
    assert not revised["questions"] and revised["steps"][1]["cohort_from"] == "s1"
    assert revised["steps"][1]["parameters"]["preparation"]


def test_composable_filter_arithmetic_and_threshold(inputs):
    _, metadata, taxonomy = inputs
    recipe = [
        Preparation(
            op="filter",
            dataset_id=metadata["id"],
            column="Magnesium",
            operator="ge",
            values=["5"],
        ),
        Preparation(
            op="arithmetic",
            dataset_id=metadata["id"],
            column="Magnesium",
            output="Mg_scaled",
            arithmetic="divide",
            operand=2,
        ),
        Preparation(
            op="threshold_group",
            dataset_id=metadata["id"],
            column="Mg_scaled",
            output="group",
            threshold=7.5,
        ),
    ]
    prepared = prepare([metadata, taxonomy], recipe)
    assert len(prepared.frame) == 20
    assert prepared.frame.group.value_counts().to_dict() == {"低值组": 11, "高值组": 9}
    assert prepared.frame.loc["S05", "Mg_scaled"] == 2.5


def test_tied_quantiles_and_invalid_dependencies_block(inputs):
    _, metadata, taxonomy = inputs
    recipe = [
        Preparation(
            op="quantile_group",
            dataset_id=metadata["id"],
            column="age",
            output="age_group",
        )
    ]
    with pytest.raises(data.DataError, match="重合"):
        prepare([metadata, taxonomy], recipe)
    plan = AnalysisPlan.model_validate(design(metadata))
    plan.steps[1].depends_on = []
    with pytest.raises(data.DataError, match="依赖"):
        compile_cohorts(plan)
    plan = AnalysisPlan.model_validate(design(metadata))
    plan.steps[1].parameters.preparation = [
        Preparation(
            op="quantile_group",
            dataset_id=metadata["id"],
            column="age",
            output="age_group",
        )
    ]
    with pytest.raises(data.DataError, match="不一致"):
        compile_cohorts(plan)


def test_recipe_changes_cache_and_overwrite_is_rejected(inputs):
    pid, metadata, taxonomy = inputs
    plan = AnalysisPlan.model_validate(design(metadata))
    compile_cohorts(plan)
    snap = agent.snapshot(pid)
    a = worker.cache_key(snap, plan.steps[1].model_dump())
    plan.steps[1].parameters.preparation[0].lower = 0.2
    assert a != worker.cache_key(snap, plan.steps[1].model_dump())
    with pytest.raises(data.DataError, match="覆盖"):
        prepare(
            [metadata, taxonomy],
            [
                Preparation(
                    op="quantile_group",
                    dataset_id=metadata["id"],
                    column="Magnesium",
                    output="Magnesium",
                )
            ],
        )


def test_replot_retains_cohort_and_independence(inputs, monkeypatch):
    pid, metadata, taxonomy = inputs
    monkeypatch.setattr(agent, "model_json", lambda _: deepcopy(design(metadata)))
    first = agent.create_plan(
        pid,
        ChatRequest(message=GOAL, include_report=False, study=StudyConfig(independent=True)),
    )
    params = first["steps"][1]["parameters"]
    params["palette"] = "ocean"
    from yanji.contracts import SkillParams

    second = agent.create_plan(
        pid,
        ChatRequest(
            message="重新作图",
            mode="skill",
            skill_id="differential",
            include_report=False,
            parameters=SkillParams.model_validate(params),
            study=StudyConfig(independent=True),
        ),
    )
    assert not second["questions"], second["questions"]
    assert [s["skill"] for s in second["steps"]] == ["prepare_cohort", "differential"]
    assert second["steps"][1]["cohort_from"] == "s1"
    assert second["preparation_preview"] == first["preparation_preview"]


def test_wrong_top_scope_and_wrong_quantile_are_rejected(inputs):
    from yanji.preparation import assert_intent

    _, metadata, _ = inputs
    plan = AnalysisPlan.model_validate(design(metadata))
    plan.steps[2].skill = "composition"
    with pytest.raises(data.DataError, match="各组分别"):
        assert_intent(plan, GOAL)
    plan = AnalysisPlan.model_validate(design(metadata))
    plan.steps[0].parameters.preparation[0].lower = 0.2
    with pytest.raises(data.DataError, match="P25/P75"):
        assert_intent(plan, GOAL)


def test_boundary_ties_stay_together_and_missing_metadata_is_audited(inputs):
    pid, metadata, taxonomy = inputs
    ops = [
        Preparation(
            op="recode",
            dataset_id=metadata["id"],
            column="age",
            output="age_band",
            mapping={"30": "成年"},
        ),
        Preparation(
            op="quantile_group",
            dataset_id=metadata["id"],
            column="Magnesium",
            output="Mg_group",
        ),
    ]
    prepared = prepare(
        [metadata, {**taxonomy, "samples": taxonomy["samples"] + ["missing_metadata"]}],
        ops,
    )
    assert prepared.membership.loc["missing_metadata", "status"] == "缺少样本信息"
    assert not prepared.membership.loc["missing_metadata", "included"]
    rows = pd.DataFrame({"sample_id": taxonomy["samples"], "Mg": [1] * 8 + [2] * 8 + [3] * 9})
    tied = data.import_bytes(
        pid,
        "ties.tsv",
        rows.to_csv(sep="\t", index=False).encode(),
        ImportOptions(kind="metadata"),
    )
    result = prepare(
        [tied, taxonomy],
        [Preparation(op="quantile_group", dataset_id=tied["id"], column="Mg", output="group")],
    )
    assert result.frame.group.value_counts().to_dict() == {"高值组": 9, "低值组": 8}
    assert result.frame.loc[result.frame.Mg == "1", "group"].eq("低值组").all()
