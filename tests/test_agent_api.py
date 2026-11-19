import json

import pytest

from yanji import agent, db
from yanji.contracts import ChatRequest


def test_plan_needs_confirmation(client, example):
    pid = example["id"]
    p = client.post(
        f"/api/v1/projects/{pid}/chat", json={"message": "总体概览", "mode": "overview"}
    ).json()
    assert not db.list_records("run", pid)
    r = client.post(f"/api/v1/projects/{pid}/runs", json={"plan_id": p["id"]})
    assert r.status_code == 201 and r.json()["status"] == "queued"
    r2 = client.post(f"/api/v1/projects/{pid}/runs", json={"plan_id": p["id"]})
    assert r2.json()["id"] == r.json()["id"]


def test_stale_plan_rejected(client, example):
    pid = example["id"]
    p = agent.create_plan(pid, ChatRequest(message="概览", mode="overview"))
    db.update(pid, study={"group_column": None, "independent": False})
    r = client.post(f"/api/v1/projects/{pid}/runs", json={"plan_id": p["id"]})
    assert r.status_code == 409


def test_missing_groups_block(client, example):
    pid = example["id"]
    db.update(pid, study={})
    p = agent.create_plan(pid, ChatRequest(message="比较", mode="comparison"))
    assert p["questions"]
    r = client.post(f"/api/v1/projects/{pid}/runs", json={"plan_id": p["id"]})
    assert r.status_code == 422


def test_unknown_skill_repair(example, monkeypatch):
    count = []
    good = agent.guided(ChatRequest(message="概览", mode="overview"), example["id"]).model_dump()
    bad = {**good, "steps": [{**good["steps"][0], "skill": "execute_shell"}]}

    def model(messages):
        count.append(1)
        return bad if len(count) < 3 else good

    monkeypatch.setattr(agent, "model_json", model)
    p = agent.create_plan(example["id"], ChatRequest(message="看看组成"))
    assert len(count) == 3 and p["origin"] == "model" and p["steps"][-1]["skill"] == "report"


def test_bad_model_stops_after_three(example, monkeypatch):
    count = []

    def model(messages):
        count.append(1)
        return {"wrong": "data"}

    monkeypatch.setattr(agent, "model_json", model)
    with pytest.raises(agent.ModelError):
        agent.create_plan(example["id"], ChatRequest(message="分析"))
    assert len(count) == 3


def test_origin_protection_and_isolation(client, project, example):
    assert (
        client.post(
            "/api/v1/projects", json={"name": "x"}, headers={"Origin": "https://untrusted.example"}
        ).status_code
        == 403
    )
    ds = db.get(example["id"], "project")["active_datasets"]["taxonomy"]
    assert client.get(f"/api/v1/projects/{project['id']}/datasets/{ds}").status_code == 404
    settings = client.get("/api/v1/settings/model").json()
    assert "api_key" not in settings


def test_no_shell_or_unknown_parameters(client, example):
    r = client.post(
        f"/api/v1/projects/{example['id']}/chat",
        json={"message": "概览", "mode": "overview", "parameters": {"shell": "rm"}},
    )
    assert r.status_code == 422


def test_import_preview_mapping_and_templates(client, project):
    pid = project["id"]
    result = client.post(
        f"/api/v1/projects/{pid}/datasets",
        files={"file": ("tax.tsv", b"ID\tA\tB\nx\t.3\t.4", "text/plain")},
        data={"options": json.dumps({"unit": "fraction"})},
    )
    assert result.status_code == 201, result.text
    d = result.json()
    view = client.get(f"/api/v1/projects/{pid}/datasets/{d['id']}").json()
    assert view["preview"]["rows"][0][0] == "x"
    mapped = client.post(
        f"/api/v1/projects/{pid}/datasets/{d['id']}/mapping",
        json={"mapping": {"A": "S1", "B": "S2"}, "excluded_samples": []},
    )
    assert mapped.status_code == 201 and mapped.json()["revision"] == 2
    assert client.get("/api/v1/templates/metadata").status_code == 200
    assert (
        client.post(
            f"/api/v1/projects/{pid}/datasets", files={"file": ("bad.html", b"bad")}
        ).status_code
        == 422
    )
    assert (
        client.delete(f"/api/v1/projects/{pid}/datasets/{mapped.json()['id']}").status_code == 200
    )


def test_repeated_subject_blocked_before_confirmation(client, example):
    from yanji.contracts import ImportOptions
    from yanji.data import import_bytes
    from yanji.examples import frames, raw

    _, meta, _ = frames()
    meta.loc[1, "subject_id"] = meta.loc[0, "subject_id"]
    import_bytes(example["id"], "metadata.tsv", raw(meta, False), ImportOptions(kind="metadata"))
    plan = agent.create_plan(example["id"], ChatRequest(message="比较独立两组", mode="comparison"))
    assert any("重复受试者" in q for q in plan["questions"])


def test_model_auth_json_and_private_errors(monkeypatch):
    import httpx

    real = httpx.Client
    monkeypatch.setattr(
        agent,
        "model_config",
        lambda: {
            "base_url": "https://example.invalid/v1",
            "api_key": "fake-private-secret",
            "model": "test-model",
        },
    )

    def handler(request):
        assert request.headers["Authorization"] == "Bearer fake-private-secret"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {"total_tokens": 9},
            },
        )

    monkeypatch.setattr(
        agent.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    assert agent.model_json([{"role": "user", "content": "test"}]) == {"ok": True}
    assert db.list_records("model_call")[-1]["total_tokens"] == 9

    def bad(request):
        return httpx.Response(401, text="fake-private-secret")

    monkeypatch.setattr(
        agent.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(bad), **kw)
    )
    with pytest.raises(agent.ModelError) as caught:
        agent.model_json([])
    assert "401" in str(caught.value) and "fake-private-secret" not in str(caught.value)


def test_model_timeout_is_bounded(monkeypatch):
    import httpx

    count = []
    real = httpx.Client
    monkeypatch.setattr(
        agent,
        "model_config",
        lambda: {"base_url": "https://example.invalid/v1", "api_key": "fake", "model": "test"},
    )

    def handler(request):
        count.append(1)
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(
        agent.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    with pytest.raises(agent.ModelError):
        agent.model_json([])
    assert len(count) == 2


def test_model_selected_parameters_survive_defaults(example, monkeypatch):
    from yanji.contracts import SkillParams

    body = agent.guided(
        ChatRequest(message="查看属级组成", mode="overview"), example["id"]
    ).model_dump()
    for step in body["steps"]:
        step["parameters"]["rank"] = "genus"
        step["parameters"]["top_n"] = 8
    monkeypatch.setattr(agent, "model_json", lambda messages: body)
    plan = agent.create_plan(example["id"], ChatRequest(message="查看前八个属"))
    assert all(
        s["parameters"]["rank"] == "genus" and s["parameters"]["top_n"] == 8 for s in plan["steps"]
    )
    plan = agent.create_plan(
        example["id"], ChatRequest(message="查看属级组成", parameters=SkillParams(top_n=5))
    )
    assert all(
        s["parameters"]["rank"] == "genus" and s["parameters"]["top_n"] == 5 for s in plan["steps"]
    )
