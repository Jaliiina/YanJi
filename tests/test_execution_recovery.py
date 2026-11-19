"""Progress survives independent branch failure; retry never reruns successful work."""

import pytest

from yanji import agent, db, worker
from yanji.contracts import AnalysisPlan, ChatRequest, RunConfirm
from yanji.flask_routes import confirm_run


def test_independent_branch_continues_and_retry_keeps_nonprefix_success(
    client, example, monkeypatch
):
    pid = example["id"]
    plan = agent.create_plan(
        pid,
        ChatRequest(mode="skill", skill_id="data_check", message="体检", include_report=False),
    )
    steps = [
        {"id": "s1", "skill": "data_check", "parameters": {}, "depends_on": []},
        {"id": "s2", "skill": "data_check", "parameters": {}, "depends_on": []},
        {"id": "s3", "skill": "data_check", "parameters": {}, "depends_on": ["s1"]},
    ]
    db.update(plan["id"], steps=steps)
    run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
    called = []

    def compute(run, step, *args):
        called.append(step["id"])
        if step["id"] == "s1":
            raise RuntimeError("temporary failure")
        return {
            "skill": "data_check",
            "status": "success",
            "summary": "真实完成",
            "method": "检查",
            "metrics": {},
            "evidence": [],
            "artifacts": [],
        }

    monkeypatch.setattr(worker, "execute_step", compute)
    worker.run_one(run)
    state = db.get(run["id"], "run")
    assert state["status"] == "failed" and state["progress"] == 33
    assert called == ["s1", "s2"]
    assert [r["status"] for r in state["results"]] == ["failed", "success", "skipped"]
    response = client.post(f"/api/v1/projects/{pid}/runs/{run['id']}/retry")
    assert response.status_code == 200
    assert [r["step_id"] for r in response.json()["results"]] == ["s2"]

    def fixed(run, step, *args):
        called.append(step["id"])
        return {
            "skill": "data_check",
            "status": "success",
            "summary": "真实完成",
            "method": "检查",
            "metrics": {},
            "evidence": [],
            "artifacts": [],
        }

    monkeypatch.setattr(worker, "execute_step", fixed)
    worker.run_one(worker.claim_next())
    state = db.get(run["id"], "run")
    assert state["status"] == "completed" and not state["partial"]
    assert called == ["s1", "s2", "s1", "s3"]
    assert [r["step_id"] for r in state["results"]] == ["s1", "s2", "s3"]


def test_synthesis_requires_real_inputs_not_just_execution_order(example):
    plan = AnalysisPlan.model_validate(
        {
            "objective": "联合研究",
            "summary": "联合证据",
            "steps": [
                {"id": "s1", "skill": "partial_correlation"},
                {"id": "s2", "skill": "partial_correlation"},
                {
                    "id": "s3",
                    "skill": "association_heatmap",
                    "depends_on": ["s1", "s2"],
                    "inputs": {"data": {"step_id": "s1", "output": "associations"}},
                },
            ],
            "research_design": {
                "aims": [
                    {
                        "id": "a1",
                        "question": "第一项关系",
                        "relation": "association",
                        "step_ids": ["s1"],
                    },
                    {
                        "id": "a2",
                        "question": "第二项关系",
                        "relation": "association",
                        "step_ids": ["s2"],
                    },
                ],
                "synthesis_step": "s3",
            },
        }
    )
    with pytest.raises(ValueError, match="综合步骤没有读取"):
        agent.validate_plan(plan, example["id"])


def test_codegen_receives_source_key_structure_for_result_join(example):
    from yanji import data
    from yanji.result_inputs import describe_bindings

    pid = example["id"]
    taxonomy = next(d for d in data.active(pid) if d["data_type"] == "taxonomy")
    plan = AnalysisPlan.model_validate(
        {
            "objective": "汇总关联",
            "summary": "按实际键对齐",
            "steps": [
                {
                    "id": "s1",
                    "skill": "taxa_association",
                    "parameters": {"dataset_id": taxonomy["id"], "variable": "x"},
                },
                {
                    "id": "s2",
                    "skill": "custom_analysis",
                    "program": {
                        "method": "提取真实物种标识",
                        "inputs": [taxonomy["id"]],
                        "requirements": [{"id": "r1", "description": "保留原标识"}],
                        "outputs": [
                            {
                                "name": "features",
                                "kind": "table",
                                "title": "特征标识",
                                "columns": ["species"],
                            }
                        ],
                        "code": "frame = tables.copy()",
                    },
                },
                {
                    "id": "s3",
                    "skill": "custom_analysis",
                    "depends_on": ["s1", "s2"],
                    "inputs": {
                        "associations": {"step_id": "s1", "output": "associations"},
                        "features": {"step_id": "s2", "output": "features"},
                    },
                },
            ],
        }
    )
    context = describe_bindings(plan.steps[2], plan, data.active(pid))
    assert context["associations"]["key_examples"]["feature"]
    assert context["features"]["producer_code"] == "frame = tables.copy()"
    assert context["features"]["source_structure"][0]["feature_examples"]
