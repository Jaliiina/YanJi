"""A generated analysis is accepted by outputs and intent, never exit code alone."""

import json
import os

import pytest

from yanji import adaptive, agent, data, db
from yanji.contracts import AnalysisProgram, ChatRequest, ImportOptions, RunConfirm
from yanji.flask_routes import confirm_run
from yanji.skills.context import Context


@pytest.fixture
def input_table(project):
    return data.import_bytes(
        project["id"],
        "records.tsv",
        b"sample_id\tx\ty\nA\t1\t3\nB\t2\t5\nC\t3\t7\nD\t4\t9\nE\t5\t11",
        ImportOptions(kind="metadata"),
    )


def program(dataset):
    return AnalysisProgram(
        method="对 x/y 进行最小二乘直线拟合，输出实际拟合值。",
        inputs=[dataset["id"]],
        requirements=[{"id": "r1", "description": "用全部5个实际观测拟合并输出预测值"}],
        outputs=[
            {
                "name": "fit",
                "kind": "table",
                "title": "拟合值",
                "columns": ["x", "y", "predicted"],
                "min_rows": 5,
            }
        ],
        code=f"""from scipy.stats import linregress
frame = tables[{dataset["id"]!r}].apply(pd.to_numeric)
fit = linregress(frame.x, frame.y)
frame['predicted'] = fit.intercept + fit.slope * frame.x
emit_table(frame, 'fit')
check('r1', len(frame) == 5 and np.allclose(frame.y, frame.predicted), '实际拟合5个观测')
finish('拟合完成', metrics={{'slope': float(fit.slope)}})
""",
    )


def test_plan_generates_code_but_never_executes_before_confirmation(input_table, monkeypatch):
    d = input_table
    source = program(d)
    spec = source.model_dump()
    spec["code"] = ""
    calls = []

    def model(messages, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            return {
                "objective": "拟合直线",
                "summary": "按实际数据拟合并输出预测值。",
                "steps": [{"id": "s1", "skill": "custom_analysis", "program": spec}],
            }
        if len(calls) == 2:
            return {"approved": True}
        return {"code": source.code}

    monkeypatch.setattr(agent, "model_json", model)
    monkeypatch.setattr(adaptive, "run_isolated", lambda *args: pytest.fail("确认前不能执行"))
    row = agent.create_plan(
        d["project_id"],
        ChatRequest(message="给x和y拟合直线，输出预测值。", include_report=False),
    )
    assert len(calls) == 3 and not row["questions"]
    assert row["steps"][0]["program"]["code"] == source.code
    assert not db.list_records("run", d["project_id"])
    assert confirm_run(d["project_id"], RunConfirm(plan_id=row["id"]))["status"] == "queued"


@pytest.mark.parametrize(
    "code",
    [
        "import os",
        "from pathlib import Path",
        "open('file')",
        "eval('1')",
        "x.__class__",
        "check('r1', True, 'done')",
    ],
)
def test_unsafe_or_fake_checks_are_rejected(code):
    with pytest.raises(adaptive.ProgramFailure):
        adaptive.validate_code(code)


def test_no_unisolated_fallback(input_table, monkeypatch, tmp_path):
    monkeypatch.setattr(adaptive, "available", lambda: False)
    monkeypatch.setattr(
        adaptive.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("不得退回裸执行"),
    )
    with pytest.raises(adaptive.ProgramFailure, match="隔离"):
        adaptive.run_isolated(program(input_table), [input_table], tmp_path / "job")


def test_output_contract_missing_columns_cannot_succeed(input_table, tmp_path):
    job = tmp_path / "job"
    (job / "output").mkdir(parents=True)
    (job / "output" / "fit.tsv").write_text("ID\tx\nA\t1\n")
    result = {
        "outputs": {"fit": {"files": ["fit.tsv"]}},
        "checks": {"r1": {"passed": True}},
    }
    with pytest.raises(adaptive.ProgramFailure, match="列和行"):
        adaptive.validate_outputs(program(input_table), job, result)
    result["checks"] = {}
    with pytest.raises(adaptive.ProgramFailure, match="全部要求"):
        adaptive.validate_outputs(program(input_table), job, result)


def test_semantic_review_rejects_replaced_objective(input_table, monkeypatch):
    captured = []

    def model(messages, **kwargs):
        captured.append(json.loads(messages[-1]["content"]))
        return {
            "approved": False,
            "requirements": [{"id": "r1", "passed": False, "reason": "只做了均值"}],
            "feedback": "需要拟合而非均值",
        }

    monkeypatch.setattr(agent, "model_json", model)
    with pytest.raises(adaptive.ProgramFailure, match="拟合而非均值"):
        adaptive.review(
            program(input_table),
            "拟合直线",
            {
                "summary": "均值已算",
                "outputs": {},
                "checks": {},
                "metrics": {"raw_records": [1, 2, 3]},
            },
        )
    assert "raw_records" not in captured[0]["metrics"]
    assert "code" in captured[0]


def test_bounded_repair_keeps_frozen_method(input_table, monkeypatch):
    d = input_table
    p = program(d)
    ctx = Context(d["project_id"], "test", "s1", agent.snapshot(d["project_id"]), {})
    attempts = []

    def run(p, datasets, job, *args):
        attempts.append(p)
        if len(attempts) == 1:
            raise adaptive.ProgramFailure("字段转换错误")
        (job / "output").mkdir(parents=True)
        (job / "output" / "fit.tsv").write_text("ID\tx\ty\tpredicted\nA\t1\t3\t3\n")
        return {
            "summary": "拟合完成",
            "metrics": {"slope": 2},
            "checks": {"r1": {"passed": True}},
            "outputs": {"fit": {"files": ["fit.tsv"]}},
        }

    monkeypatch.setattr(adaptive, "run_isolated", run)

    def generate(p, datasets, objective, feedback, preparation=()):
        assert p.method == program(d).method and "转换" in feedback
        return p.model_copy(update={"code": p.code + "\nrepair_marker = 1"})

    monkeypatch.setattr(adaptive, "generate", generate)
    monkeypatch.setattr(
        adaptive,
        "review",
        lambda *a: {"approved": True, "requirements": [{"id": "r1", "passed": True}]},
    )
    result = adaptive.execute(ctx, p.model_dump(), "拟合直线")
    assert result["status"] == "success" and result["metrics"]["attempts"] == 2
    assert {a["artifact_type"] for a in result["artifacts"]} == {
        "table",
        "code",
        "audit",
    }
    assert len(json.loads((ctx.directory / "acceptance.json").read_text())["attempts"]) == 2


def test_all_failed_attempts_are_not_marked_success(input_table, monkeypatch):
    d = input_table
    p = program(d)
    ctx = Context(d["project_id"], "test", "s1", agent.snapshot(d["project_id"]), {})
    tries = []

    def run(*args):
        tries.append(1)
        raise adaptive.ProgramFailure("数据条件不满足")

    monkeypatch.setattr(adaptive, "run_isolated", run)
    monkeypatch.setattr(adaptive, "generate", lambda p, *args: p)
    with pytest.raises(adaptive.ProgramFailure, match="未标记成功"):
        adaptive.execute(ctx, p.model_dump(), "拟合直线")
    assert len(tries) == 1 and not ctx.artifacts
    assert "repair_unchanged" in (ctx.directory / "attempts.json").read_text()


@pytest.mark.skipif(os.environ.get("YANJI_TEST_OS_SANDBOX") != "1", reason="显式启用OS隔离集成验收")
def test_real_os_computation_and_outside_read_denied(input_table, tmp_path):
    p = program(input_table)
    computed = adaptive.run_isolated(p, [input_table], tmp_path / "valid")
    assert computed["metrics"]["slope"] == 2
    sentinel = tmp_path / "outside.tsv"
    sentinel.write_text("secret\nnot-allowed\n")
    evil = p.model_copy(update={"code": f"pd.read_csv({str(sentinel)!r})\n" + p.code})
    with pytest.raises(adaptive.ProgramFailure, match="Permission|Operation not permitted"):
        adaptive.run_isolated(evil, [input_table], tmp_path / "denied")
    network = p.model_copy(update={"code": "pd.read_csv('http://127.0.0.1:9/')\n" + p.code})
    with pytest.raises(adaptive.ProgramFailure, match="Permission|Operation not permitted"):
        adaptive.run_isolated(network, [input_table], tmp_path / "network_denied")


def test_deepseek_codegen_disables_thinking_and_truncation_is_explicit(monkeypatch):
    import httpx

    original = httpx.Client
    payloads = []

    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"code_lines":["x=1"]}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {},
            },
        )

    monkeypatch.setattr(
        agent,
        "model_config",
        lambda: {
            "api_key": "test-key",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-flash",
        },
    )
    monkeypatch.setattr(
        agent.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler)),
    )
    assert agent.model_json([{"role": "user", "content": "json"}], thinking=False)[
        "code_lines"
    ] == ["x=1"]
    assert payloads[0]["thinking"] == {"type": "disabled"}

    def truncated(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
                "usage": {},
            },
        )

    monkeypatch.setattr(
        agent.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(truncated)),
    )
    with pytest.raises(agent.ModelError, match="截断"):
        agent.model_json([{"role": "user", "content": "json"}], thinking=False)


@pytest.mark.skipif(os.environ.get("YANJI_TEST_OS_SANDBOX") != "1", reason="显式启用OS隔离集成验收")
def test_real_isolated_program_consumes_explicit_upstream_results(input_table, tmp_path):
    import pandas as pd

    if not adaptive.available():
        pytest.skip("需要操作系统隔离执行环境")
    p = program(input_table)
    p.code = """frame = results['selected'].apply(pd.to_numeric)
frame['predicted'] = 2 * frame.x + 1
emit_table(frame, 'fit')
check('r1', len(frame) == 5 and np.allclose(frame.y, frame.predicted), '只使用已绑定上游结果')
finish('使用上游结果完成', metrics={'rows':len(frame)})
"""
    upstream = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [3, 5, 7, 9, 11]})
    computed = adaptive.run_isolated(
        p, [input_table], tmp_path / "with_upstream", upstream={"selected": upstream}
    )
    assert computed["metrics"]["rows"] == 5
    assert computed["checks"]["r1"]["passed"]


@pytest.mark.skipif(os.environ.get("YANJI_TEST_OS_SANDBOX") != "1", reason="显式启用OS隔离集成验收")
def test_multiple_checks_are_conjunctive_and_failed_check_cannot_be_overwritten(
    input_table, tmp_path
):
    p = program(input_table)
    p.code = p.code.replace(
        "finish('拟合完成'",
        "check('r1', len(frame) > 0, '再次检查相同要求')\nfinish('拟合完成'",
    )
    result = adaptive.run_isolated(p, [input_table], tmp_path / "many_checks")
    assert len(result["checks"]["r1"]["observations"]) == 2
    evil = p.model_copy(
        update={
            "code": p.code.replace(
                "check('r1', len(frame) > 0, '再次检查相同要求')",
                "try:\n    check('r1', len(frame) == 0, '真实失败')\nexcept ValueError:\n    pass\ncheck('r1', len(frame) > 0, '不能覆盖失败')",
            )
        }
    )
    with pytest.raises(adaptive.ProgramFailure, match="存在未通过"):
        adaptive.run_isolated(evil, [input_table], tmp_path / "cannot_overwrite")


def test_retry_resumes_repaired_program_and_keeps_history(input_table, monkeypatch):
    d = input_table
    p = program(d)
    ctx = Context(d["project_id"], "recover", "s1", agent.snapshot(d["project_id"]), {})
    attempted = []

    def run(p, *args):
        attempted.append(p.code)
        raise adaptive.ProgramFailure("可修复的错误")

    monkeypatch.setattr(adaptive, "run_isolated", run)
    monkeypatch.setattr(
        adaptive,
        "generate",
        lambda p, *args: p.model_copy(update={"code": p.code + "\nrepair_marker = 1"}),
    )
    with pytest.raises(adaptive.ProgramFailure):
        adaptive.execute(ctx, p.model_dump(), "原目标")
    state = json.loads((ctx.directory / "repair_state.json").read_text())
    assert state["code"] != p.code
    # A retry must start with the last actual repair, not the original broken code.
    monkeypatch.setattr(adaptive, "generate", lambda p, *args: p)
    with pytest.raises(adaptive.ProgramFailure):
        adaptive.execute(ctx, p.model_dump(), "原目标")
    assert attempted[-1] == state["code"]
    state2 = json.loads((ctx.directory / "repair_state.json").read_text())
    assert state2["cycle"] == 2 and len(state2["attempts"]) > len(state["attempts"])


def test_stale_runtime_does_not_resume_old_program(input_table, monkeypatch):
    d = input_table
    p = program(d)
    ctx = Context(d["project_id"], "stale-runtime", "s1", agent.snapshot(d["project_id"]), {})
    seen = []

    def run(program, *args):
        seen.append(program.code)
        raise adaptive.ProgramFailure("停住")

    monkeypatch.setattr(adaptive, "run_isolated", run)
    monkeypatch.setattr(
        adaptive,
        "generate",
        lambda program, *args: program.model_copy(
            update={"code": program.code + "\nrepair_marker = 1"}
        ),
    )
    with pytest.raises(adaptive.ProgramFailure):
        adaptive.execute(ctx, p.model_dump(), "原目标")
    state = json.loads((ctx.directory / "repair_state.json").read_text())
    state["runtime_version"] = "0.0.0"
    state["code"] = p.code + "\nstale = True"
    (ctx.directory / "repair_state.json").write_text(json.dumps(state))
    monkeypatch.setattr(adaptive, "generate", lambda program, *args: program)
    with pytest.raises(adaptive.ProgramFailure):
        adaptive.execute(ctx, p.model_dump(), "原目标")
    assert "stale = True" not in seen[-1]
    assert json.loads((ctx.directory / "repair_state.json").read_text())["runtime_version"] == (
        adaptive.VERSION
    )


def test_custom_analysis_cache_uses_runtime_version():
    from yanji.skills.registry import CATALOG

    assert CATALOG["custom_analysis"].version == adaptive.VERSION


def test_result_only_program_is_generated_without_raw_file_binding(input_table, monkeypatch):
    d = input_table
    spec = program(d).model_dump()
    spec["inputs"] = []
    spec["code"] = ""
    body = {
        "objective": "汇总回归结果",
        "summary": "先计算再汇总真实结果",
        "steps": [
            {
                "id": "s1",
                "skill": "adjusted_regression",
                "parameters": {
                    "dataset_id": d["id"],
                    "predictors": ["x"],
                    "outcomes": ["y"],
                },
            },
            {
                "id": "s2",
                "skill": "custom_analysis",
                "depends_on": ["s1"],
                "inputs": {"data": {"step_id": "s1", "output": "associations"}},
                "program": spec,
            },
        ],
    }
    calls = []

    def model(messages, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            return body
        if len(calls) == 2:
            return {"approved": True}
        payload = json.loads(messages[-1]["content"])
        assert (
            payload["inputs"] == [] and "effect" in payload["upstream_results"]["data"]["columns"]
        )
        return {
            "code": "frame = results['data'].copy()\nemit_table(frame, 'fit')\ncheck('r1', len(frame) > 0, '使用真实上游表')\nfinish('汇总完成')"
        }

    monkeypatch.setattr(agent, "model_json", model)
    plan = agent.create_plan(
        d["project_id"],
        ChatRequest(
            message="请对x/y做回归并汇总上游结果",
            study={"independent": True},
            include_report=False,
        ),
    )
    assert not plan["questions"] and plan["steps"][1]["program"]["inputs"] == []
    assert not db.list_records("run", d["project_id"])


def test_execution_rewrites_sample_suffix_before_the_program():
    import pandas as pd

    species = pd.DataFrame({"sample_id": ["F1945", "F2026"], "abundance": [0.1, 0.2]})
    pathways = pd.DataFrame(
        {"sample_id": ["F1945_combined", "F2026_combined"], "proxy_abundance": [1, 2]}
    )
    audit = adaptive.harmonize_job_frames([], {}, {"species": species, "pathways": pathways})
    assert set(species["sample_id"]) == {"F1945", "F2026"}
    assert set(pathways["sample_id"]) == {"F1945", "F2026"}
    assert sum(item["changed"] for item in audit) == 2
    same = pd.DataFrame({"sample_id": ["A", "B"]})
    other = pd.DataFrame({"sample_id": ["A", "B"]})
    assert adaptive.harmonize_job_frames([], {}, {"left": same, "right": other}) == []


def test_failure_reason_is_one_sentence():
    text = adaptive.explain_failure(
        'Traceback (most recent call last):\n  File "analysis.py", line 33\n'
        "ValueError: 研究要求未满足：r2 交集样本数=0, species 独有=191, pathways 独有=191"
    )
    assert "主键" in text
    assert "Traceback" not in text
    assert "截断" in adaptive.explain_failure(
        "修复未产生实际代码变化。原错误：模型输出被长度限制截断"
    ) or "没有改动" in adaptive.explain_failure(
        "修复未产生实际代码变化。原错误：模型输出被长度限制截断"
    )


def test_named_sample_inside_a_larger_question_stays_with_the_planner():
    from yanji.routing import resolve_named_samples

    datasets = [{"data_type": "taxonomy", "samples": ["F2029", "F2034"]}]
    assert resolve_named_samples("分析F2029与通路、钙含量的关系", datasets, False) is None
    plan = resolve_named_samples("比较F2029和F2034的菌种组成", datasets, False)
    assert plan.steps[1].skill == "sample_comparison"


def test_repeated_sample_rows_with_suffix_still_align():
    import pandas as pd

    species = pd.DataFrame(
        {
            "sample_id": ["F1945", "F1945", "F2026"],
            "species": ["a", "b", "a"],
        }
    )
    pathways = pd.DataFrame(
        {
            "sample_id": ["F1945_combined", "F2026_combined", "F2026_combined"],
            "pathway": ["p", "p", "q"],
        }
    )
    row = adaptive.observe_frames({"species": species, "pathways": pathways})["alignments"][0]
    assert row["exact_overlap"] == 0
    assert row["normalized_overlap"] == 2
    assert row["usable"] is True
    assert {item["key"] for item in row["examples"]} == {"F1945", "F2026"}


def test_exact_sample_ids_are_left_unchanged():
    import pandas as pd

    observed = adaptive.observe_frames(
        {
            "left": pd.DataFrame({"sample_id": ["A", "B"]}),
            "right": pd.DataFrame({"sample_id": ["A", "B"]}),
        }
    )
    assert observed["alignments"][0]["usable"] is False
    assert observed["alignments"][0]["exact_overlap"] == 2


def test_codegen_is_told_when_sample_keys_match(input_table, monkeypatch):
    import pandas as pd

    seen = {}

    def model(messages, **kwargs):
        seen["system"] = messages[0]["content"]
        seen["body"] = json.loads(messages[1]["content"])
        return {"code": "x = 1\n"}

    monkeypatch.setattr(agent, "model_json", model)
    adaptive.generate(
        program(input_table).model_copy(update={"code": ""}),
        [input_table],
        "对照热图",
        frames={
            "species": pd.DataFrame({"sample_id": ["F1945", "F2026"]}),
            "pathways": pd.DataFrame({"sample_id": ["F1945_combined", "F2026_combined"]}),
        },
    )
    row = seen["body"]["observed_alignment"]["upstream_tables"]["alignments"][0]
    assert row["usable"] is True and row["exact_overlap"] == 0
    assert "usable 为 true" in seen["system"]


def test_truncated_plan_is_asked_to_shorten(project, input_table, monkeypatch):
    calls = []

    def model(messages, **kwargs):
        calls.append(messages[-1]["content"])
        if len(calls) == 1:
            raise agent.ModelError("模型输出被长度限制截断，请精简分析程序与注释后重新生成。")
        return {
            "objective": "做一张热图",
            "summary": "先确认表格可以读取。",
            "steps": [{"id": "s1", "skill": "data_check", "reason": "确认所选表格可以读取。"}],
        }

    monkeypatch.setattr(agent, "model_json", model)
    plan = agent.create_plan(
        project["id"],
        ChatRequest(
            message="做一张热图",
            mode="agent",
            dataset_ids=[input_table["id"]],
            include_report=False,
        ),
    )
    assert plan["steps"][0]["skill"] == "data_check"
    assert len(calls) == 2
    assert "更短" in calls[1]
    assert "sample_alignment" in calls[0]


def test_cut_off_review_keeps_a_checked_result(input_table, monkeypatch):
    d = input_table
    p = program(d)
    ctx = Context(d["project_id"], "review-cut", "s1", agent.snapshot(d["project_id"]), {})

    def run(program, datasets, job, *args):
        (job / "output").mkdir(parents=True)
        (job / "output" / "fit.tsv").write_text("ID\tx\ty\tpredicted\nA\t1\t3\t3\n")
        return {
            "summary": "拟合完成，没有额外显著项。",
            "metrics": {"slope": 2, "n_links": 0},
            "warnings": [],
            "checks": {"r1": {"passed": True, "detail": "5个观测", "observations": []}},
            "outputs": {"fit": {"files": ["fit.tsv"]}},
        }

    def unavailable(*args, **kwargs):
        raise agent.ModelError("模型输出被长度限制截断，请精简分析程序与注释后重新生成。")

    monkeypatch.setattr(adaptive, "run_isolated", run)
    monkeypatch.setattr(adaptive, "review", unavailable)
    result = adaptive.execute(ctx, p.model_dump(), "拟合直线")
    assert result["status"] == "success"
    assert result["metrics"]["n_links"] == 0
    assert any("模型审核没有完成" in item for item in result["warnings"])
    assert not any("模型目标审核" in item for item in result["warnings"])
