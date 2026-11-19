from yanji import agent, db
from yanji.clarify import extract_concepts, is_distribution
from yanji.contracts import ChatRequest, ImportOptions, RunConfirm, SkillParams
from yanji.data import import_bytes
from yanji.flask_routes import confirm_run
from yanji.worker import run_one

LEVELS = [
    "Autism（重度）",
    "Autism（中重度）",
    "Autism（中度）",
    "Autism（轻中度）",
    "Autism（轻度）",
    "Autism（高功能）",
]


def cohort(pid):
    rows = [
        "编号\t性别\t年龄\t诊断",
        "1\t男\t6\tAutism（重度）",
        "2\t女\t7\tAutism（轻度）",
        "3\t男\t8\tAutism（中度）",
        "4\t女\t9\tAutism（中重度）",
        "5\t男\t10\tAutism（高功能）",
        "6\t女\t11\tAutism（轻中度）",
        "7\t男\t12\tAutism（重度）",
        "8\t女\t8\tAutism（轻度）",
    ]
    return import_bytes(pid, "cohort.tsv", "\n".join(rows).encode(), ImportOptions(kind="table"))


def test_distribution_language_is_scoped():
    text = "我想分析年龄、自闭症严重程度、性别的分布"
    assert extract_concepts(text) == ["年龄", "自闭症严重程度", "性别"]
    assert is_distribution(text)
    assert not is_distribution("分析钙与菌群丰度的关系")
    assert not is_distribution("年龄和评分的相关")


def test_distribution_request_asks_then_runs_after_answers(client, project):
    pid = project["id"]
    table = cohort(pid)
    first = agent.create_plan(
        pid,
        ChatRequest(
            message="我想分析年龄、自闭症严重程度、性别的分布",
            dataset_ids=[table["id"]],
            include_report=False,
        ),
    )
    cards = first["clarifications"]
    assert {card["kind"] for card in cards} == {"unit", "bind_field", "encoding"}
    assert not any(card["concept"] == "性别" for card in cards)
    unit = next(card for card in cards if card["kind"] == "unit")
    bind = next(card for card in cards if card["kind"] == "bind_field")
    encoding = next(card for card in cards if card["kind"] == "encoding")
    assert unit["field"] == "年龄" and bind["field"] == "诊断"
    assert bind["concept"] == "自闭症严重程度"
    assert [step["skill"] for step in first["steps"]] == ["data_check"]
    try:
        confirm_run(pid, RunConfirm(plan_id=first["id"]))
    except ValueError as exc:
        assert "单位" in str(exc) or "诊断" in str(exc)
    else:
        raise AssertionError("未回答补充项时不应开始分析")
    answers = [
        {
            "id": unit["id"],
            "dataset_id": unit["dataset_id"],
            "field": "年龄",
            "unit": "岁",
        },
        {
            "id": bind["id"],
            "dataset_id": bind["dataset_id"],
            "field": "诊断",
        },
        {
            "id": encoding["id"],
            "dataset_id": bind["dataset_id"],
            "field": "诊断",
            "encoding": " > ".join(LEVELS),
        },
    ]
    response = client.post(
        f"/api/v1/projects/{pid}/plans/{first['id']}/clarify",
        json={"answers": answers},
    )
    assert response.status_code == 201, response.text
    second = response.json()
    assert not second["questions"] and not second["clarifications"]
    step = next(item for item in second["steps"] if item["skill"] == "field_distribution")
    assert step["parameters"]["fields"] == ["年龄", "诊断", "性别"]
    saved = {field["name"]: field for field in db.get(table["id"])["understanding"]["fields"]}
    assert saved["年龄"]["unit"] == "岁"
    assert saved["诊断"]["meaning"] == "自闭症严重程度"
    assert saved["诊断"]["role"] == "ordinal"
    run = confirm_run(pid, RunConfirm(plan_id=second["id"]))
    run_one(run)
    result = db.get(run["id"])["results"][-1]
    assert result["status"] == "success", result["summary"]
    by_field = {item["field"]: item for item in result["metrics"]["fields"]}
    assert by_field["年龄"]["median"] == 8.5
    assert by_field["诊断"]["levels"] == LEVELS
    assert by_field["诊断"]["counts"][0] == 2
    assert set(by_field["性别"]["levels"]) == {"男", "女"}
    assert {"png", "svg", "chart", "table"} <= {
        artifact["artifact_type"] for artifact in result["artifacts"]
    }


def test_skill_distribution_accepts_categories(project):
    pid = project["id"]
    table = cohort(pid)
    plan = agent.create_plan(
        pid,
        ChatRequest(
            message="字段分布",
            mode="skill",
            skill_id="field_distribution",
            dataset_ids=[table["id"]],
            include_report=False,
            parameters=SkillParams(dataset_id=table["id"], fields=["年龄", "性别", "诊断"]),
        ),
    )
    assert not plan["questions"]
    run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
    run_one(run)
    result = db.get(run["id"])["results"][-1]
    assert result["status"] == "success"
    kinds = {item["field"]: item["kind"] for item in result["metrics"]["fields"]}
    assert kinds == {"年龄": "numeric", "性别": "category", "诊断": "category"}


def test_microbiome_distribution_stays_with_the_model(project, monkeypatch):
    pid = project["id"]
    cohort(pid)
    monkeypatch.setattr(
        agent,
        "model_json",
        lambda _messages: {
            "objective": "组成",
            "summary": "先检查数据",
            "steps": [{"id": "s1", "skill": "data_check", "reason": "检查"}],
            "questions": ["请说明要比较的群落问题"],
        },
    )
    plan = agent.create_plan(
        pid,
        ChatRequest(message="分析物种分布和菌群差异", include_report=False),
    )
    assert [step["skill"] for step in plan["steps"]] == ["data_check"]
    # The model's own question stays, as a free-text card rather than a column form.
    assert [card["kind"] for card in plan["clarifications"]] == ["text"]
    assert plan["questions"] == ["请说明要比较的群落问题"]
