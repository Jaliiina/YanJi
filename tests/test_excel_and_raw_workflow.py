"""Excel boundary cases and an opt-in-by-presence regression on the user's three schemas."""

import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from yanji import agent, db
from yanji.contracts import ChatRequest, ImportOptions, RunConfirm, SkillParams
from yanji.data import DataError, import_bytes, inspect, mapping_suggestions, remap
from yanji.flask_routes import confirm_run
from yanji.reports import export
from yanji.skills.analysis import execute
from yanji.skills.context import Context
from yanji.worker import run_one


def workbook(headers, rows):
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    extra = book.create_sheet("补充表")
    extra.append(["F号", "指标", None])
    extra.append(["F1", 10, None])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_excel_auto_identifier_missing_and_sheet(client, project):
    raw = workbook(["序号", "Zn分组", "F号", "年龄"], [[1, "低", "F1", 8], [2, "高", "F2", None]])
    frame, info = inspect(raw, "samples.xlsx", ImportOptions())
    assert info["data_type"] == "metadata"
    assert info["samples"] == ["F1", "F2"]
    assert frame.loc["F2", "年龄"] == ""
    frame, info = inspect(raw, "samples.xlsx", ImportOptions(sheet="补充表"))
    assert frame.shape == (1, 1)
    assert info["transformations"][0]["sheet"] == "补充表"
    with pytest.raises(DataError, match="工作表不存在"):
        inspect(raw, "x.xlsx", ImportOptions(sheet="不存在"))
    pid = project["id"]
    r = client.post(f"/api/v1/projects/{pid}/import-preview", files={"file": ("x.xlsx", raw)})
    assert r.status_code == 200 and len(r.json()["sheets"]) == 2
    r = client.post(f"/api/v1/projects/{pid}/datasets", files={"file": ("x.xlsx", raw)})
    assert r.status_code == 201 and r.json()["samples"] == ["F1", "F2"]


def test_excel_duplicate_ids_rejected():
    with pytest.raises(DataError, match="重复"):
        inspect(workbook(["F号", "group"], [["F1", "A"], ["F1", "B"]]), "x.xlsx", ImportOptions())
    with pytest.raises(DataError, match="无法读取"):
        inspect(b"invalid zip", "x.xlsx", ImportOptions())


def test_metadata_only_analysis(project):
    pid = project["id"]
    raw = workbook(["F号", "group", "age"], [["F1", "A", 8], ["F2", "B", None]])
    import_bytes(pid, "meta.xlsx", raw, ImportOptions())
    plan = agent.create_plan(pid, ChatRequest(message="查看样本信息", mode="overview"))
    assert [s["skill"] for s in plan["steps"]] == ["data_check", "metadata_overview", "report"]
    ctx = Context(pid, db.uid(), "s1", agent.snapshot(pid), SkillParams().model_dump())
    result = execute(ctx, "metadata_overview")
    assert result["status"] == "success" and result["metrics"]["samples"] == 2
    assert result["artifacts"] and result["evidence"]


def test_real_three_schemas_through_worker_and_exports(client, project):
    root = Path(__file__).resolve().parents[1] / "raw_data"
    excel = next(root.glob("*.xlsx"), None)
    if (
        excel is None
        or not (root / "taxonomy.tsv").exists()
        or not (root / "pathabundance_relab_stratified.tsv").exists()
    ):
        pytest.skip("Local research fixtures are not distributed with source")
    pid = project["id"]
    for path in [root / "taxonomy.tsv", excel, root / "pathabundance_relab_stratified.tsv"]:
        # Exercise the actual HTTP file upload boundary.
        r = client.post(
            f"/api/v1/projects/{pid}/datasets", files={"file": (path.name, path.read_bytes())}
        )
        assert r.status_code == 201, r.text
    datasets = client.get(f"/api/v1/projects/{pid}").json()["datasets"]
    tax = next(d for d in datasets if d["data_type"] == "taxonomy")
    functional = next(d for d in datasets if d["data_type"] == "functional")
    metadata = next(d for d in datasets if d["data_type"] == "metadata")
    assert len(tax["samples"]) == len(functional["samples"]) == 191
    assert len(metadata["samples"]) == 200
    assert functional["summary"]["total_pathways"] == 0
    suggestions = mapping_suggestions(pid, functional)
    assert not suggestions["unmatched"]
    remap(functional["id"], suggestions["mapping"], [])
    meta_suggestions = mapping_suggestions(pid, metadata)
    assert meta_suggestions["mapping"]["F2430-Z"] == "F2430"
    assert meta_suggestions["mapping"]["F2429-L"] == "F2429"
    metadata = remap(metadata["id"], meta_suggestions["mapping"], [])
    assert set(tax["samples"]) <= set(metadata["samples"])
    study = {"group_column": "Zn分组", "independent": True, "excluded_samples": []}
    assert client.put(f"/api/v1/projects/{pid}/study", json=study).status_code == 200
    blocked = agent.create_plan(pid, ChatRequest(message="组间比较", mode="comparison"))
    assert any("比较的组别" in q or "两个比较组" in q for q in blocked["questions"])
    for mode in ["overview", "comparison"]:
        plan = agent.create_plan(
            pid,
            ChatRequest(
                message="真实数据流程验证",
                mode=mode,
                parameters=SkillParams(group_a="低水平组", group_b="高水平组", permutations=99),
            ),
        )
        assert not plan["questions"]
        run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
        run_one(run)
        completed = db.get(run["id"], "run")
        assert completed["status"] == "completed"
        assert all(r["status"] == "success" for r in completed["results"]), [
            (r["skill"], r["summary"]) for r in completed["results"]
        ]
        report = db.list_records("report", pid)[-1]
        for kind in ["pdf", "docx", "zip"]:
            artifact = export(report["id"], kind)
            assert Path(artifact).stat().st_size > 1000
