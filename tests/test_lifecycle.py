import os
import subprocess
import sys
import zipfile
from unittest.mock import patch

from pypdf import PdfReader

from yanji import agent, db, worker
from yanji.contracts import ChatRequest, RunConfirm
from yanji.flask_routes import confirm_run
from yanji.reports import export


def short_plan(pid):
    return agent.create_plan(
        pid, ChatRequest(message="数据体检", mode="skill", skill_id="data_check")
    )


def test_claim_cancel_retry_and_recovery(client, example):
    pid = example["id"]
    plan = short_plan(pid)
    run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
    claimed = worker.claim_next()
    assert claimed["id"] == run["id"]
    assert worker.claim_next() is None
    worker.recover()
    assert db.get(run["id"])["status"] == "interrupted"
    retry = client.post(f"/api/v1/projects/{pid}/runs/{run['id']}/retry")
    assert retry.status_code == 200 and retry.json()["status"] == "queued"
    cancel = client.post(f"/api/v1/projects/{pid}/runs/{run['id']}/cancel")
    assert cancel.json()["status"] == "cancelled"
    assert worker.claim_next() is None


def test_full_worker_report_edit_and_exports(client, example, monkeypatch, tmp_path):
    pid = example["id"]
    plan = short_plan(pid)
    run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
    with patch("yanji.reports.model_json", return_value={"notes": []}):
        worker.run_one(worker.claim_next())
    completed = db.get(run["id"])
    assert completed["status"] == "completed"
    report = db.list_records("report", pid)[-1]
    root = f"/api/v1/projects/{pid}/reports/{report['id']}"
    bad = {
        "title": "研究报告",
        "sections": [{**report["sections"][0], "evidence_ids": ["invented"]}],
        "expected_revision": 1,
    }
    assert client.put(root, json=bad).status_code == 422
    body = {"title": "编辑后的中文报告", "sections": report["sections"], "expected_revision": 1}
    saved = client.put(root, json=body)
    assert saved.status_code == 200 and saved.json()["revision"] == 2
    assert client.put(root, json=body).status_code == 409
    paths = {kind: export(report["id"], kind) for kind in ("pdf", "docx", "zip")}
    assert "编辑后的中文报告" in "".join(p.extract_text() for p in PdfReader(paths["pdf"]).pages)
    with zipfile.ZipFile(paths["docx"]) as z:
        assert "word/fonts/yanji.odttf" in z.namelist()
        assert "编辑后的中文报告" in z.read("word/document.xml").decode()
    with zipfile.ZipFile(paths["zip"]) as z:
        assert ".env" not in z.namelist()
        assert any(x.startswith("inputs/") for x in z.namelist())
        extracted = tmp_path / "repro"
        z.extractall(extracted)
    env = {**os.environ, "PYTHONPATH": str(extracted / "src")}
    result = subprocess.run(
        [sys.executable, str(extracted / "reproduce.py")],
        cwd=extracted,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert (extracted / "reproduced/results.json").exists()
    # Cache reuse must retain checked output while rebinding evidence IDs.
    plan2 = short_plan(pid)
    run2 = confirm_run(pid, RunConfirm(plan_id=plan2["id"]))
    with patch("yanji.reports.model_json", return_value={"notes": []}):
        worker.run_one(worker.claim_next())
    assert db.get(run2["id"])["results"][0]["reused_from"] == run["id"]


def test_report_unverified_narrative_falls_back(example, monkeypatch):
    from yanji.reports import create_report

    monkeypatch.setattr(
        "yanji.reports.model_json",
        lambda *a, **kw: {"notes": [{"evidence_id": "fake", "text": "编造结论"}]},
    )
    r = create_report(example["id"], "test", "测试", [], agent.snapshot(example["id"]))
    assert r["ai_status"] == "template" and r["ai_warning"]


def test_live_step_cancel(client, example):
    # Cancellation before a claimed step starts must preserve queue state and avoid running tools.
    pid = example["id"]
    plan = short_plan(pid)
    run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
    claimed = worker.claim_next()
    db.update(run["id"], cancel_requested=True)
    worker.run_one(claimed)
    assert db.get(run["id"])["status"] == "cancelled"
    assert not db.get(run["id"])["results"]


def test_cancel_active_subprocess(client, example):
    import threading
    import time

    pid = example["id"]
    plan = short_plan(pid)
    run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
    claimed = worker.claim_next()
    thread = threading.Thread(target=worker.run_one, args=(claimed,))
    thread.start()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = db.get(run["id"])
        if state.get("child_pid"):
            break
        time.sleep(0.02)
    assert state.get("child_pid")
    assert client.post(f"/api/v1/projects/{pid}/runs/{run['id']}/cancel").status_code == 200
    thread.join(timeout=10)
    assert not thread.is_alive() and db.get(run["id"])["status"] == "cancelled"


def test_stale_report_keeps_user_content(client, example):
    from yanji.reports import create_report

    with patch("yanji.reports.model_json", return_value={"notes": []}):
        report = create_report(
            example["id"], "stale-test", "研究目标", [], agent.snapshot(example["id"])
        )
    db.update(example["id"], study={"group_column": None, "independent": False})
    fetched = client.get(f"/api/v1/projects/{example['id']}/reports/{report['id']}").json()
    assert fetched["stale"] is True
    assert next(s for s in fetched["sections"] if s["id"] == "purpose")["text"] == "研究目标"


def test_report_uses_only_approved_interpretation_codes(example, monkeypatch):
    from yanji.reports import create_report

    output = {
        "skill": "composition",
        "summary": "描述性结果",
        "method": "已审核方法",
        "warnings": [],
        "artifacts": [],
        "evidence": [
            {
                "id": "s1:overview",
                "statement": "描述性结果",
                "values": {},
                "artifact_ids": [],
                "dataset_ids": [],
                "parameters": {},
            }
        ],
    }
    monkeypatch.setattr(
        "yanji.reports.model_json",
        lambda *a, **kw: {
            "notes": [{"evidence_id": "s1:overview", "note_code": "relative_abundance"}]
        },
    )
    report = create_report(
        example["id"], "approved-test", "目的", [output], agent.snapshot(example["id"])
    )
    assert report["ai_status"] == "assisted"
    assert (
        "不能据此推断微生物绝对数量"
        in next(s for s in report["sections"] if s["id"] == "result_0")["text"]
    )
