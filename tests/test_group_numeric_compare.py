"""Metadata/table numeric-by-group questions must run a real contrast, not distributions."""

import numpy as np
import pandas as pd

from yanji import agent, db
from yanji.contracts import ChatRequest, ImportOptions, RunConfirm
from yanji.data import import_bytes
from yanji.flask_routes import confirm_run
from yanji.worker import run_one


def clinical(pid):
    rng = np.random.default_rng(1)
    frame = pd.DataFrame(
        {
            "sample_id": [f"S{i}" for i in range(20)],
            "性别": ["男"] * 10 + ["女"] * 10,
            "Zinc": list(rng.normal(95, 8, 10)) + list(rng.normal(80, 8, 10)),
            "年龄": rng.integers(4, 12, 20),
        }
    )
    return import_bytes(
        pid,
        "clinical.tsv",
        frame.to_csv(sep="\t", index=False).encode(),
        ImportOptions(kind="metadata"),
    )


def test_sex_zinc_routes_to_group_numeric_compare(project):
    pid = project["id"]
    clinical(pid)
    plan = agent.create_plan(
        pid,
        ChatRequest(
            message="男女的zn含量组间差异是否显著",
            include_report=False,
        ),
    )
    assert any(s["skill"] == "group_numeric_compare" for s in plan["steps"])
    step = next(s for s in plan["steps"] if s["skill"] == "group_numeric_compare")
    assert step["parameters"]["group_by"] == "性别"
    assert step["parameters"]["variable"] == "Zinc"
    assert not any(s["skill"] == "field_distribution" for s in plan["steps"])
    run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
    run_one(run)
    result = db.get(run["id"])["results"][-1]
    assert result["status"] == "success", result["summary"]
    assert result["metrics"]["test"] == "Mann-Whitney"
    assert result["metrics"]["p"] < 0.05


def test_age_sex_association_uses_group_compare(project):
    pid = project["id"]
    clinical(pid)
    plan = agent.create_plan(
        pid,
        ChatRequest(message="分析年龄与性别的相关性", include_report=False),
    )
    step = next(s for s in plan["steps"] if s["skill"] == "group_numeric_compare")
    assert {step["parameters"]["group_by"], step["parameters"]["variable"]} == {
        "性别",
        "年龄",
    }


def test_group_numeric_compare_rejects_distribution_substitute(project, monkeypatch):
    pid = project["id"]
    clinical(pid)
    import yanji.routing as routing

    monkeypatch.setattr(routing, "resolve_group_numeric", lambda *_a, **_k: None)

    def fake(_messages):
        return {
            "objective": "男女的zn含量组间差异是否显著",
            "summary": "只能描述",
            "steps": [
                {
                    "id": "s1",
                    "skill": "field_distribution",
                    "reason": "看分布",
                    "parameters": {
                        "dataset_id": db.list_records("dataset", pid)[0]["id"],
                        "fields": ["性别", "Zinc"],
                    },
                }
            ],
            "questions": [],
        }

    monkeypatch.setattr(agent, "model_json", fake)
    try:
        agent.create_plan(
            pid,
            ChatRequest(message="男女的zn含量组间差异是否显著", include_report=False),
        )
        raised = False
    except agent.ModelError as exc:
        raised = "group_numeric_compare" in str(exc) or "组间" in str(exc)
    assert raised


def test_revise_replans_with_instruction(project, monkeypatch):
    pid = project["id"]
    clinical(pid)
    first = agent.create_plan(
        pid,
        ChatRequest(message="男女的zn含量组间差异是否显著", include_report=False),
    )
    dataset_id = next(
        s["parameters"]["dataset_id"]
        for s in first["steps"]
        if s["skill"] == "group_numeric_compare"
    )

    def fake(messages):
        log = messages[1]["content"]
        assert "请改用年龄" in log or "请改用年龄" in str(log)
        return {
            "objective": first["objective"],
            "summary": "按说明改为年龄。",
            "steps": [
                {
                    "id": "s1",
                    "skill": "group_numeric_compare",
                    "reason": "按性别比较年龄",
                    "parameters": {
                        "dataset_id": dataset_id,
                        "group_by": "性别",
                        "variable": "年龄",
                    },
                }
            ],
            "questions": [],
        }

    monkeypatch.setattr(agent, "model_json", fake)
    from yanji.contracts import ReviseRequest

    revised = agent.revise(pid, first["id"], ReviseRequest(message="请改用年龄作为比较指标"))
    step = next(s for s in revised["steps"] if s["skill"] == "group_numeric_compare")
    assert step["parameters"]["variable"] == "年龄"
    assert revised["clarification_log"][-1]["answer"] == "请改用年龄作为比较指标"
