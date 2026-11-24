"""Deleting a project removes its records and the files kept for it."""

import pytest

from yanji import agent, data, db
from yanji.config import runtime_root
from yanji.contracts import ChatRequest, ImportOptions, RunConfirm
from yanji.flask_routes import confirm_run


def test_delete_removes_records_and_files(client, project):
    pid = project["id"]
    kept = client.post("/api/v1/projects", json={"name": "保留的项目"}).json()
    dataset = data.import_bytes(
        pid,
        "samples.tsv",
        b"sample_id\tvalue\nA\t1\nB\t2",
        ImportOptions(kind="metadata"),
    )
    plan = agent.create_plan(
        pid,
        ChatRequest(
            mode="skill",
            skill_id="data_check",
            message="检查数据",
            include_report=False,
        ),
    )
    response = client.delete(f"/api/v1/projects/{pid}")
    assert response.status_code == 200 and response.json() == {"id": pid, "deleted": True}
    assert pid not in [p["id"] for p in client.get("/api/v1/projects").json()]
    for record_id, kind in (
        (pid, "project"),
        (dataset["id"], "dataset"),
        (plan["id"], "plan"),
    ):
        with pytest.raises(KeyError):
            db.get(record_id, kind)
    assert not (runtime_root() / "projects" / pid).exists()
    assert not (runtime_root() / dataset["storage"]).exists()
    assert client.post(f"/api/v1/projects/{pid}/restore").status_code == 404
    assert (
        client.post(f"/api/v1/projects/{pid}/runs", json={"plan_id": plan["id"]}).status_code == 404
    )
    assert kept["id"] in [p["id"] for p in client.get("/api/v1/projects").json()]


def test_delete_blocks_active_analysis_and_preserves_project(client, project):
    pid = project["id"]
    data.import_bytes(
        pid,
        "samples.tsv",
        b"sample_id\tvalue\nA\t1\nB\t2",
        ImportOptions(kind="metadata"),
    )
    plan = agent.create_plan(
        pid,
        ChatRequest(
            mode="skill",
            skill_id="data_check",
            message="检查数据",
            include_report=False,
        ),
    )
    run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
    for status in ["queued", "running"]:
        db.update(run["id"], status=status)
        response = client.delete(f"/api/v1/projects/{pid}")
        assert response.status_code == 409 and "先停止" in response.json()["detail"]
        assert not db.get(pid, "project")["archived"]
    db.update(run["id"], status="cancelled")
    assert client.delete(f"/api/v1/projects/{pid}").status_code == 200
    assert client.post(f"/api/v1/projects/{pid}/runs/{run['id']}/retry").status_code == 404


def test_missing_project_cannot_be_deleted_or_restored(client):
    assert client.delete("/api/v1/projects/missing").status_code == 404
    assert client.post("/api/v1/projects/missing/restore").status_code == 404
