import json

import numpy as np

from yanji import agent, db
from yanji.contracts import ChatRequest, ImportOptions, RunConfirm, SkillParams
from yanji.data import import_bytes, load_frame
from yanji.flask_routes import confirm_run
from yanji.worker import run_one


def table(pid):
    raw = "记录\t性别\t年龄\t评分\n001\t1\t8\t10\n002\t2\t9\t12\n003\t1\t10\t14\n004\t2\t11\t16\n005\t1\t12\t18\n006\t2\t13\t20\n".encode()
    return import_bytes(pid, "任意列名.tsv", raw, ImportOptions(kind="table"))


def test_field_meanings_invalidate_plan_and_reject_stale_writes(client, project):
    pid = project["id"]
    d = table(pid)
    base = f"/api/v1/projects/{pid}/datasets/{d['id']}"
    profile = client.get(base).json()["field_profile"]
    assert next(f for f in profile["fields"] if f["name"] == "性别")["role"] == "categorical"
    assert next(f for f in profile["fields"] if f["name"] == "年龄")["unit"] == ""
    plan = agent.create_plan(
        pid,
        ChatRequest(
            message="相关",
            mode="skill",
            skill_id="table_correlation",
            parameters=SkillParams(dataset_id=d["id"], x="年龄", y="评分"),
            include_report=False,
        ),
    )
    assert not plan["questions"] and not db.list_records("run", pid)
    body = {
        "description": "每行一人，年龄单位是岁",
        "fields": [{"name": "年龄", "meaning": "年龄", "unit": "岁", "role": "numeric"}],
        "expected_revision": 0,
    }
    assert client.put(base + "/understanding", json=body).status_code == 200
    assert (
        client.post(f"/api/v1/projects/{pid}/runs", json={"plan_id": plan["id"]}).status_code == 409
    )
    assert client.put(base + "/understanding", json=body).status_code == 422
    assert db.list_records("understanding", pid)[0]["description"] == body["description"]
    bad = {
        **body,
        "expected_revision": 1,
        "fields": [{"name": "不存在", "meaning": "某指标"}],
    }
    assert client.put(base + "/understanding", json=bad).status_code == 422


def test_suggest_is_a_draft_and_cannot_invent_fields(client, project, monkeypatch):
    d = table(project["id"])
    url = f"/api/v1/projects/{project['id']}/datasets/{d['id']}/understanding/suggest"
    monkeypatch.setattr(
        agent,
        "model_json",
        lambda _: {"fields": [{"name": "年龄", "unit": "岁", "role": "numeric"}]},
    )
    assert client.post(url, json={"description": "年龄单位岁"}).json()["fields"][0]["unit"] == "岁"
    assert not db.get(d["id"]).get("understanding")
    monkeypatch.setattr(agent, "model_json", lambda _: {"fields": [{"name": "编造字段"}]})
    assert client.post(url, json={"description": "说明"}).status_code == 422


def test_correlation_executes_after_approval_with_actual_numbers(client, project):
    pid = project["id"]
    d = table(pid)
    plan = agent.create_plan(
        pid,
        ChatRequest(
            message="年龄与评分相关",
            mode="skill",
            skill_id="table_correlation",
            include_report=False,
            parameters=SkillParams(dataset_id=d["id"], x="年龄", y="评分"),
        ),
    )
    assert [s["skill"] for s in plan["steps"]] == ["data_check", "table_correlation"]
    run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
    run_one(run)
    result = db.get(run["id"])["results"][-1]
    assert result["status"] == "success" and result["metrics"]["samples"] == 6
    assert np.isclose(result["metrics"]["rho"], 1)
    assert {"chart", "png", "svg", "table"} <= {a["artifact_type"] for a in result["artifacts"]}
    assert not db.list_records("report", pid)


def test_cross_project_table_binding_is_blocked(project, client):
    d = table(project["id"])
    other = client.post("/api/v1/projects", json={"name": "别的研究"}).json()
    p = (
        agent.create_plan(
            other["id"],
            ChatRequest(
                message="绘图",
                mode="skill",
                skill_id="sankey",
                parameters=SkillParams(
                    dataset_id=d["id"], source="记录", target="性别", weight="年龄"
                ),
            ),
        )
        if db.get(other["id"])["active_datasets"]
        else None
    )
    # Even with a local table, another project's table ID must never be used.
    table(other["id"])
    p = agent.create_plan(
        other["id"],
        ChatRequest(
            message="绘图",
            mode="skill",
            skill_id="sankey",
            parameters=SkillParams(dataset_id=d["id"], source="记录", target="性别", weight="年龄"),
        ),
    )
    assert p["questions"]
    assert client.get(f"/api/v1/projects/{other['id']}/datasets/{d['id']}").status_code == 404


def test_sankey_uses_actual_edges_and_rejects_negative_weights(project):
    pid = project["id"]
    d = import_bytes(
        pid,
        "edges.tsv",
        b"from\tto\tweight\nA\tB\t2\nA\tB\t3\nC\tB\t1",
        ImportOptions(),
    )
    assert d["data_type"] == "table" and len(load_frame(d)) == 3
    p = agent.create_plan(
        pid,
        ChatRequest(
            message="桑基图",
            mode="skill",
            skill_id="sankey",
            include_report=False,
            parameters=SkillParams(dataset_id=d["id"], source="from", target="to", weight="weight"),
        ),
    )
    run = confirm_run(pid, RunConfirm(plan_id=p["id"]))
    run_one(run)
    out = db.get(run["id"])["results"][-1]
    assert out["metrics"]["edges"] == 2
    from yanji.config import runtime_root

    chart = next(a for a in out["artifacts"] if a["artifact_type"] == "chart")
    links = json.loads((runtime_root() / chart["storage"]).read_text())["series"][0]["links"]
    assert {x["source"]: x["value"] for x in links} == {"L:A": 5, "L:C": 1}
    negative = import_bytes(pid, "bad.tsv", b"from\tto\tweight\nA\tB\t-1", ImportOptions())
    blocked = agent.create_plan(
        pid,
        ChatRequest(
            message="桑基图",
            mode="skill",
            skill_id="sankey",
            parameters=SkillParams(
                dataset_id=negative["id"], source="from", target="to", weight="weight"
            ),
        ),
    )
    assert any("非负" in q for q in blocked["questions"])


def test_reinterpret_preserves_original_and_removes_old_active_slot(client, project):
    pid = project["id"]
    d = table(pid)
    r = client.post(
        f"/api/v1/projects/{pid}/datasets/{d['id']}/reinterpret",
        json={"kind": "metadata", "id_column": "记录"},
    )
    assert r.status_code == 200, r.text
    newer = r.json()
    assert newer["samples"][0] == "001" and newer["revision"] == 2
    assert d["id"] not in db.get(pid)["active_datasets"].values()
    assert load_frame(d).columns.tolist()[0] == "记录"
