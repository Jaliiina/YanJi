import pytest

from yanji import agent, db
from yanji.data import DataError
from yanji.writing_support import (
    LiteratureRequest,
    WritingRequest,
    attach,
    draft,
    retrieve,
)


def test_fixed_and_agent_retrieval_record_actual_actions(project, monkeypatch):
    from yanji import writing_support as w

    monkeypatch.setattr(
        w,
        "search",
        lambda q: [
            {
                "id": "paper-1",
                "title": "真实接口返回题名",
                "snippet": "摘要",
                "url": "https://example.org/paper",
                "level": "摘要",
            }
        ],
    )
    monkeypatch.setattr(
        w, "read", lambda hit: {**hit, "snippet": "实际返回正文", "level": "正文节选"}
    )
    fixed = retrieve(project["id"], LiteratureRequest(query="方法"))
    assert fixed["status"] == "completed"
    assert [s["action"] for s in fixed["steps"]] == ["search", "get", "finish"]
    actions = iter(
        [
            {"action": "search", "query": "方法"},
            {"action": "finish", "reason": "已有证据不足以继续"},
        ]
    )
    monkeypatch.setattr(agent, "model_json", lambda *a, **kw: next(actions))
    model = retrieve(project["id"], LiteratureRequest(query="方法", mode="agent"))
    assert [s["action"] for s in model["steps"]] == ["search", "finish"]
    assert model["items"][0]["level"] == "摘要"


def test_unseen_paper_and_unavailable_service_fail_explicitly(project, monkeypatch):
    monkeypatch.setattr(
        agent, "model_json", lambda *a, **kw: {"action": "get", "paper_id": "invented"}
    )
    result = retrieve(project["id"], LiteratureRequest(query="问题", mode="agent"))
    assert result["status"] == "failed" and not result["items"]
    assert "尚未检索" in result["error"]


def test_writing_draft_has_valid_evidence_and_never_overwrites_report(project, monkeypatch):
    report = db.create(
        "report",
        project["id"],
        revision=1,
        sections=[
            {
                "id": "discussion",
                "title": "讨论",
                "text": "旧正文",
                "evidence_ids": [],
                "artifact_ids": [],
            }
        ],
        evidence=[{"id": "ev1", "statement": "实际结果", "values": {"n": 6}}],
    )
    monkeypatch.setattr(
        agent,
        "model_json",
        lambda *a, **kw: {"text": "待审核新正文", "evidence_ids": ["ev1"]},
    )
    body = WritingRequest(section_id="discussion", instruction="整理讨论", expected_revision=1)
    result = draft(report, body)
    assert (
        result["review_status"] == "pending"
        and db.get(report["id"])["sections"][0]["text"] == "旧正文"
    )
    assert db.list_records("writing_draft", project["id"])
    monkeypatch.setattr(
        agent,
        "model_json",
        lambda *a, **kw: {"text": "编造", "evidence_ids": ["unknown"]},
    )
    with pytest.raises(DataError):
        draft(report, body)
    with pytest.raises(DataError):
        draft(report, body.model_copy(update={"expected_revision": 0}))


def test_attachment_pins_source_and_checks_revision(project):
    report = db.create("report", project["id"], revision=1, sections=[], evidence=[])
    retrieval = db.create(
        "retrieval",
        project["id"],
        items=[
            {
                "id": "p1",
                "title": "题名",
                "snippet": "实际片段",
                "level": "摘要",
                "url": "https://example.org/p1",
            }
        ],
    )
    updated = attach(report, retrieval, "p1", 1)
    assert updated["revision"] == 2 and updated["evidence"][0]["values"]["content_sha256"]
    assert updated["sections"][-1]["id"] == "references"
    with pytest.raises(DataError):
        attach(report, retrieval, "p1", 1)
