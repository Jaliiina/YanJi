import io
import json

from openpyxl import Workbook

from yanji import agent, data, db
from yanji.contracts import (
    ChatRequest,
    ImportOptions,
    RunConfirm,
    SkillParams,
    StudyConfig,
)
from yanji.flask_routes import confirm_run


def test_project_name_notes_and_no_automatic_rename(client):
    assert client.post("/api/v1/projects", json={"name": "  "}).status_code == 422
    p = client.post(
        "/api/v1/projects", json={"name": "新研究", "description": "记录研究目的"}
    ).json()
    data.import_bytes(p["id"], "other.csv", b"sample_id,age\n001,8\n002,9", ImportOptions())
    assert db.get(p["id"])["name"] == "新研究"
    updated = client.put(
        f"/api/v1/projects/{p['id']}",
        json={"name": " 项目A ", "description": "修改备注"},
    )
    assert updated.json()["name"] == "项目A"
    assert client.get(f"/api/v1/projects/{p['id']}").json()["description"] == "修改备注"


def test_same_type_materials_are_retained_and_inputs_are_explicit(client, project):
    pid = project["id"]
    a = data.import_bytes(
        pid,
        "first.tsv",
        b"sample_id\tage\nA\t1\nB\t2\nC\t3\nD\t4\nE\t5",
        ImportOptions(),
    )
    b = data.import_bytes(
        pid,
        "second.tsv",
        b"sample_id\tage\nX\t10\nY\t20\nZ\t30\nU\t40\nV\t50",
        ImportOptions(),
    )
    files = client.get(f"/api/v1/projects/{pid}").json()["datasets"]
    assert {d["id"] for d in files} == {a["id"], b["id"]}
    p = agent.create_plan(
        pid,
        ChatRequest(
            message="第一份年龄分布",
            mode="skill",
            skill_id="variable_distribution",
            dataset_ids=[a["id"]],
            include_report=False,
            parameters=SkillParams(variable="age"),
        ),
    )
    assert not p["questions"] and list(p["snapshot"]["datasets"].values()) == [a["id"]]
    # A new unrelated file must not silently replace the approved source.
    data.import_bytes(pid, "third.tsv", b"sample_id\tage\nF\t8\nG\t9", ImportOptions())
    run = confirm_run(pid, RunConfirm(plan_id=p["id"]))
    assert list(run["snapshot"]["datasets"].values()) == [a["id"]]
    ambiguous = agent.create_plan(
        pid,
        ChatRequest(
            message="样本概览",
            mode="skill",
            skill_id="metadata_overview",
            dataset_ids=[a["id"], b["id"]],
        ),
    )
    assert any("多份" in q for q in ambiguous["questions"])


def test_record_json_and_incompatible_structure(project):
    raw = json.dumps([{"id": "001", "x": 1, "y": None}, {"id": "002", "x": 2, "y": 3}]).encode()
    frame, info = data.inspect(raw, "records.json", ImportOptions(kind="table"))
    assert (
        info["data_type"] == "table" and frame.iloc[0]["id"] == "001" and frame.iloc[0]["y"] == ""
    )
    import pytest

    with pytest.raises(data.DataError, match="嵌套"):
        data.inspect(b'[{"x":{"nested":1},"y":2}]', "nested.json", ImportOptions())


def test_reading_options_and_preview_correction(client, project):
    pid = project["id"]
    raw = "说明文字\n编号;年龄;组别\n001;8;甲\n002;9;乙".encode("gb18030")
    frame, _ = data.inspect(raw, "legacy.csv", ImportOptions(kind="table", header_row=2))
    assert frame.columns.tolist() == ["编号", "年龄", "组别"] and frame.iloc[0]["编号"] == "001"
    url = f"/api/v1/projects/{pid}/import-preview"
    bad = client.post(url, files={"file": ("legacy.csv", raw)})
    assert bad.status_code == 200 and bad.json()["issue"] and bad.json()["preview"] is None
    good = client.post(
        url,
        files={"file": ("legacy.csv", raw)},
        data={"options": json.dumps({"header_row": 2})},
    )
    assert good.json()["preview"]["columns"] == ["编号", "年龄", "组别"]


def test_workbook_sheets_remain_separate_materials(project):
    book = Workbook()
    book.active.title = "样本表"
    book.active.append(["sample_id", "age"])
    book.active.append(["001", 8])
    sheet = book.create_sheet("量表")
    sheet.append(["sample_id", "score"])
    sheet.append(["001", 10])
    buf = io.BytesIO()
    book.save(buf)
    for name in ["样本表", "量表"]:
        data.import_bytes(project["id"], "study.xlsx", buf.getvalue(), ImportOptions(sheet=name))
    assert len(data.materials(project["id"])) == 2
    assert {d["transformations"][0]["sheet"] for d in data.materials(project["id"])} == {
        "样本表",
        "量表",
    }


def test_group_choices_belong_to_task_not_project(client, project):
    pid = project["id"]
    samples = [f"S{i}" for i in range(6)]
    tax = data.import_bytes(
        pid,
        "tax.tsv",
        ("ID\t" + "\t".join(samples) + "\nx\t1\t2\t3\t4\t5\t6\ny\t6\t5\t4\t3\t2\t1").encode(),
        ImportOptions(kind="taxonomy", unit="counts"),
    )
    md = data.import_bytes(
        pid,
        "people.csv",
        (
            "sample_id,arm\n"
            + "\n".join(f"{s},{'A' if i < 3 else 'B'}" for i, s in enumerate(samples))
        ).encode(),
        ImportOptions(),
    )
    study = StudyConfig(group_column="arm", independent=True)
    p = agent.create_plan(
        pid,
        ChatRequest(
            message="比较A与B",
            mode="comparison",
            dataset_ids=[tax["id"], md["id"]],
            study=study,
            parameters=SkillParams(group_a="A", group_b="B"),
        ),
    )
    assert not p["questions"]
    assert db.get(pid)["study"]["group_column"] is None
    assert p["snapshot"]["study"]["group_column"] == "arm"
    assert client.get(f"/api/v1/projects/{pid}/datasets/{md['id']}/values?column=arm").json()[
        "items"
    ] == [{"value": "A", "count": 3}, {"value": "B", "count": 3}]


def test_generic_overview_is_available_without_biological_schema(project):
    from yanji.skills.analysis import execute
    from yanji.skills.context import Context

    d = data.import_bytes(
        project["id"],
        "survey.json",
        json.dumps(
            [
                {"编号": "001", "测量": 1},
                {"编号": "002", "测量": 3},
                {"编号": "003", "测量": None},
            ]
        ).encode(),
        ImportOptions(kind="table"),
    )
    p = agent.create_plan(
        project["id"],
        ChatRequest(
            message="先了解数据",
            mode="overview",
            dataset_ids=[d["id"]],
            include_report=False,
        ),
    )
    assert [s["skill"] for s in p["steps"]] == ["data_check", "table_overview"]
    step = p["steps"][-1]
    out = execute(
        Context(
            project["id"],
            "overview-test",
            step["id"],
            p["snapshot"],
            step["parameters"],
        ),
        "table_overview",
    )
    assert out["metrics"] == {"rows": 3, "fields": 2}
    assert {a["artifact_type"] for a in out["artifacts"]} == {"table", "png", "svg"}
    assert data.preview(d)["columns"] == ["编号", "测量"]


def test_task_report_not_stale_after_unrelated_upload(client, project, monkeypatch):
    from yanji.reports import create_report

    pid = project["id"]
    d = data.import_bytes(pid, "a.csv", b"sample_id,age\n001,8\n002,9", ImportOptions())
    p = agent.create_plan(
        pid,
        ChatRequest(message="体检", mode="skill", skill_id="data_check", dataset_ids=[d["id"]]),
    )
    run = confirm_run(pid, RunConfirm(plan_id=p["id"]))
    monkeypatch.setattr("yanji.reports.model_json", lambda *a, **kw: {"notes": []})
    report = create_report(pid, run["id"], "体检", [], run["snapshot"])
    data.import_bytes(pid, "b.csv", b"sample_id,age\n003,10\n004,11", ImportOptions())
    assert client.get(f"/api/v1/projects/{pid}/reports/{report['id']}").json()["stale"] is False
    client.delete(f"/api/v1/projects/{pid}/datasets/{d['id']}")
    assert client.get(f"/api/v1/projects/{pid}/reports/{report['id']}").json()["stale"] is True
