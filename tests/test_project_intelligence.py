import numpy as np
import pandas as pd
import pytest

from yanji import agent, db
from yanji.contracts import ChatRequest, ImportOptions, RunConfirm, SkillParams
from yanji.data import import_bytes, mapping_suggestions, remap
from yanji.flask_routes import confirm_run
from yanji.skills.analysis import execute
from yanji.skills.context import Context


def study(pid, reverse=False):
    ids = [f"S{i}" for i in range(12)]
    tax = pd.DataFrame([np.arange(1, 13), np.arange(12, 0, -1)], index=["X", "Y"], columns=ids)
    tax.index.name = "feature_id"
    import_bytes(
        pid,
        "abundance.tsv",
        tax.to_csv(sep="\t").encode(),
        ImportOptions(unit="counts"),
    )
    values = list(range(12))[::-1] if reverse else list(range(12))
    meta = pd.DataFrame({"sample_id": ids, "Calcium": values})
    import_bytes(pid, "clinical.csv", meta.to_csv(index=False).encode(), ImportOptions())


def context(pid, **kw):
    return Context(
        pid,
        db.uid(),
        "s1",
        agent.snapshot(pid),
        SkillParams(variable="Calcium", **kw).model_dump(),
    )


def test_different_projects_produce_different_real_results(client, project):
    pid = project["id"]
    study(pid)
    other = client.post("/api/v1/projects", json={"name": "另一个真实项目"}).json()["id"]
    study(other, True)
    a = execute(context(pid), "taxa_association")
    b = execute(context(other), "taxa_association")
    assert a["status"] == b["status"] == "success"
    ar = {r["feature"]: r for r in a["metrics"]["top"]}
    br = {r["feature"]: r for r in b["metrics"]["top"]}
    assert ar["X"]["rho"] > 0.99 and br["X"]["rho"] < -0.99
    assert ar["X"]["q"] < 0.05
    assert set(a["evidence"][0]["dataset_ids"]).isdisjoint(b["evidence"][0]["dataset_ids"])
    assert (
        client.get(
            f"/api/v1/projects/{other}/datasets/{a['evidence'][0]['dataset_ids'][0]}"
        ).status_code
        == 404
    )
    description = client.get(f"/api/v1/projects/{pid}").json()["context"]
    assert not description["contains_example_data"]
    assert description["matched_metadata"] == 12
    assert description["fields"][0]["name"] == "Calcium"


def test_focused_request_rejects_kitchen_sink(example, monkeypatch):
    from yanji.project_context import describe

    assert describe(example["id"])["contains_example_data"]
    wrong = agent.guided(ChatRequest(message="概览", mode="comparison"), example["id"]).model_dump()
    monkeypatch.setattr(agent, "model_json", lambda messages: wrong)
    with pytest.raises(agent.ModelError, match="taxa_association"):
        agent.create_plan(example["id"], ChatRequest(message="分析钙水平与菌群丰度的关系"))


def test_model_questions_remain_blocking(project, monkeypatch):
    pid = project["id"]
    study(pid)
    body = {
        "objective": "test",
        "summary": "缺少指标",
        "questions": ["请说明所需钙指标的单位与测量含义"],
        "steps": [{"id": "s1", "skill": "data_check"}, {"id": "s2", "skill": "report"}],
    }
    monkeypatch.setattr(agent, "model_json", lambda messages: body)
    p = agent.create_plan(pid, ChatRequest(message="分析钙与菌群丰度的关系"))
    assert p["questions"]
    with pytest.raises(ValueError):
        confirm_run(pid, RunConfirm(plan_id=p["id"]))


def test_valid_focused_plan_uses_real_fields(project, monkeypatch):
    pid = project["id"]
    study(pid)

    def model(messages):
        assert "Calcium" in messages[1]["content"]
        return {
            "objective": "test",
            "summary": "钙与物种关联",
            "steps": [
                {
                    "id": "s1",
                    "skill": "taxa_association",
                    "parameters": {"variable": "Calcium"},
                    "reason": "回答钙与丰度的关联",
                },
                {"id": "s2", "skill": "report", "depends_on": ["s1"]},
            ],
            "questions": [],
        }

    monkeypatch.setattr(agent, "model_json", model)
    p = agent.create_plan(pid, ChatRequest(message="分析钙与菌群丰度的关系"))
    assert not p["questions"] and len(p["steps"]) == 2
    p = agent.create_plan(
        pid,
        ChatRequest(message="分析钙与菌群丰度的关系", parameters=SkillParams(variable="不存在")),
    )
    assert p["questions"]


def test_missing_constant_and_mapping_are_explicit(project):
    pid = project["id"]
    study(pid)
    assert execute(context(pid), "diversity_association")["status"] == "success"
    assert execute(context(pid), "variable_distribution")["status"] == "success"
    import_bytes(pid, "meta.csv", b"sample_id,Calcium\nS0,2\nS1,2", ImportOptions())
    assert execute(context(pid), "taxa_association")["status"] == "skipped"


def test_real_calcium_association(project):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "raw_data"
    excel = next(root.glob("*.xlsx"), None)
    if not excel:
        pytest.skip("local research data absent")
    pid = project["id"]
    for path in [root / "taxonomy.tsv", excel]:
        d = import_bytes(pid, path.name, path.read_bytes(), ImportOptions())
        if d["data_type"] == "metadata":
            remap(d["id"], mapping_suggestions(pid, d)["mapping"], [])
    out = execute(context(pid), "taxa_association")
    assert out["status"] == "success", out["summary"]
    assert out["metrics"]["samples"] > 150 and out["metrics"]["tested"] > 10
    assert all(0 <= r["q"] <= 1 for r in out["metrics"]["top"])


def test_functional_association_uses_totals_only(project):
    pid = project["id"]
    study(pid)
    ids = [f"S{i}" for i in range(12)]
    data = pd.DataFrame(
        [np.arange(1, 13) / 20, np.arange(12, 0, -1) / 20], index=["P1", "P1|species"], columns=ids
    )
    data.index.name = "# Pathway"
    import_bytes(pid, "pathabundance_relab.tsv", data.to_csv(sep="\t").encode(), ImportOptions())
    out = execute(context(pid), "functional_association")
    assert out["status"] == "success" and out["metrics"]["tested"] == 1
    assert out["metrics"]["top"][0]["feature"] == "P1"


def test_association_worker_report_and_exports(project):
    from pathlib import Path

    from yanji.reports import export
    from yanji.worker import run_one

    pid = project["id"]
    study(pid)
    p = agent.create_plan(
        pid,
        ChatRequest(
            message="Calcium 与菌群丰度关联",
            mode="skill",
            skill_id="taxa_association",
            parameters=SkillParams(variable="Calcium"),
        ),
    )
    assert not p["questions"]
    run = confirm_run(pid, RunConfirm(plan_id=p["id"]))
    run_one(run)
    out = db.get(run["id"], "run")
    assert out["status"] == "completed"
    report = db.list_records("report", pid)[-1]
    text = "\n".join(s["text"] for s in report["sections"])
    assert "Calcium" in text and "12 个匹配有效样本" in text and "clinical.csv" in text
    for kind in ["docx", "pdf", "zip"]:
        assert Path(export(report["id"], kind)).stat().st_size > 1000


def test_legacy_model_plan_requires_replanning(client, example):
    p = agent.create_plan(example["id"], ChatRequest(message="旧版方案", mode="overview"))
    db.update(p["id"], origin="model", planner_version="1.0")
    response = client.post(f"/api/v1/projects/{example['id']}/runs", json={"plan_id": p["id"]})
    assert response.status_code == 409 and "重新生成" in response.json()["detail"]
