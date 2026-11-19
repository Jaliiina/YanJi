"""Independent numeric checks and real multi-step result reuse for research tools."""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from yanji import agent, data, db, worker
from yanji.contracts import (
    AnalysisPlan,
    ChatRequest,
    ImportOptions,
    RunConfirm,
    SkillParams,
    StudyConfig,
)
from yanji.flask_routes import confirm_run
from yanji.skills.analysis import execute
from yanji.skills.context import Context
from yanji.skills.research import pair_model


@pytest.fixture
def research_data(project):
    rng = np.random.default_rng(123)
    n = 100
    age = rng.normal(30, 4, n)
    sex = rng.integers(0, 2, n)
    x = 0.6 * age + rng.normal(0, 2, n)
    y = 1.7 * x + 2 * age + 3 * sex + rng.normal(0, 0.4, n)
    f = pd.DataFrame(
        {
            "sample_id": [f"S{i:03d}" for i in range(n)],
            "x": x,
            "y": y,
            "age": age,
            "sex": np.where(sex, "M", "F"),
            "group": np.where(np.arange(n) < 50, "Low", "High"),
        }
    )
    d = data.import_bytes(
        project["id"],
        "clinical.tsv",
        f.to_csv(sep="\t", index=False).encode(),
        ImportOptions(kind="metadata"),
    )
    return project["id"], d, f.set_index("sample_id")


def test_hc3_matches_independent_sandwich_and_known_effect(research_data):
    _, _, f = research_data
    p = SkillParams(covariates=["age", "sex"], categorical_covariates=["sex"], standardize=False)
    result = pair_model(f.x, f.y, f, p, "adjusted_regression")
    X = np.column_stack([np.ones(len(f)), f.x, f.age, f.sex.eq("M").astype(float)])
    inv = np.linalg.inv(X.T @ X)
    beta = inv @ X.T @ f.y.values
    resid = f.y.values - X @ beta
    h = np.sum((X @ inv) * X, axis=1)
    cov = inv @ (X.T @ np.diag(resid**2 / (1 - h) ** 2) @ X) @ inv
    se = np.sqrt(cov[1, 1])
    value = 2 * stats.norm.sf(abs(beta[1] / se))
    assert result["effect"] == pytest.approx(beta[1], abs=1e-10)
    assert result["ci_low"] == pytest.approx(beta[1] - stats.norm.ppf(0.975) * se, abs=1e-9)
    assert result["p"] == pytest.approx(value, abs=1e-12)
    assert result["effect"] == pytest.approx(1.7, abs=0.08)


def test_partial_spearman_is_rank_first_and_legacy_is_explicit(research_data):
    _, _, f = research_data
    p = SkillParams(covariates=["age", "sex"], categorical_covariates=["sex"])
    out = pair_model(f.x, f.y, f, p, "partial_correlation")
    ranks = pd.DataFrame(
        {"x": f.x, "y": f.y, "age": f.age, "sex": f.sex.eq("M").astype(float)}
    ).rank()
    inverse = np.linalg.inv(ranks.corr().values)
    expected = -inverse[0, 1] / np.sqrt(inverse[0, 0] * inverse[1, 1])
    assert out["effect"] == pytest.approx(expected, abs=1e-10)
    assert out["metric"] == "partial_spearman_rho"
    old = pair_model(
        f.x,
        f.y,
        f,
        p.model_copy(update={"correlation_method": "residual_spearman"}),
        "partial_correlation",
    )
    assert old["metric"] == "residual_spearman_rho"
    assert abs(old["effect"] - out["effect"]) > 1e-5


def test_regression_exports_whole_family_and_audit(research_data):
    pid, d, _ = research_data
    params = SkillParams(
        metadata_id=d["id"],
        dataset_id=d["id"],
        predictors=["x", "age"],
        outcomes=["y"],
        covariates=["sex"],
        categorical_covariates=["sex"],
        standardize=False,
    )
    ctx = Context(pid, "test", "s1", agent.snapshot(pid), params.model_dump())
    result = execute(ctx, "adjusted_regression")
    assert result["status"] == "success" and result["metrics"]["tested"] == 2
    table = pd.read_csv(ctx.directory / "associations.tsv", sep="\t")
    assert set(table.predictor) == {"x", "age"}
    assert np.allclose(table.q, stats.false_discovery_control(table.p, method="bh"))
    assert (ctx.directory / "analysis_audit.tsv").is_file()
    assert {a["artifact_type"] for a in result["artifacts"]} >= {"png", "svg", "table"}


def test_missing_covariate_never_silently_dropped_and_collinearity_reported(
    research_data,
):
    pid, d, f = research_data
    request = ChatRequest(
        message="校正不存在的字段",
        mode="skill",
        skill_id="adjusted_regression",
        parameters=SkillParams(
            dataset_id=d["id"],
            predictors=["x"],
            outcomes=["y"],
            covariates=["no_such_field"],
        ),
        study=StudyConfig(independent=True),
        include_report=False,
    )
    plan = agent.create_plan(pid, request)
    assert any("协变量不存在" in q for q in plan["questions"])
    f["same_age"] = f.age
    out = pair_model(
        f.x, f.y, f, SkillParams(covariates=["age", "same_age"]), "adjusted_regression"
    )
    assert out["status"] == "not_estimable" and np.isnan(out["p"])


def test_baseline_missing_is_not_encoded_as_negative(research_data):
    pid, d, f = research_data
    f.loc["S000", "sex"] = None
    f["age"] = f.age.astype(object)
    f.loc["S051", "age"] = "/"
    f.loc["S052", "sex"] = "/"
    changed = data.import_bytes(
        pid,
        "baseline.tsv",
        f.reset_index().to_csv(sep="\t", index=False).encode(),
        ImportOptions(kind="metadata"),
    )
    ctx = Context(
        pid,
        "test",
        "s1",
        agent.snapshot(pid),
        SkillParams(
            dataset_id=changed["id"],
            fields=["age", "sex"],
            baseline_categorical=["sex"],
            group_by="group",
            group_values=["Low", "High"],
        ).model_dump(),
    )
    result = execute(ctx, "baseline_table")
    assert result["status"] == "success"
    table = pd.read_csv(ctx.directory / "baseline.tsv", sep="\t").set_index("variable")
    assert table.loc["sex", "n_Low"] == 49 and table.loc["sex", "n_High"] == 49
    assert table.loc["age", "n_High"] == 49
    assert table.loc["sex", "test"] == "Fisher exact"


def test_two_sheets_join_then_associate_real_worker_and_binding_cache(research_data, monkeypatch):
    pid, d, f = research_data
    right = f[["y"]].rename(columns={"y": "item_score"}).iloc[::-1]
    second = data.import_bytes(
        pid,
        "items.tsv",
        right.reset_index().to_csv(sep="\t", index=False).encode(),
        ImportOptions(kind="metadata"),
    )
    body = {
        "objective": "合并单题并校正年龄和性别做偏相关",
        "summary": "按样本标识连接后使用全部匹配样本。",
        "steps": [
            {
                "id": "s1",
                "skill": "join_tables",
                "parameters": {"dataset_id": d["id"], "right_dataset_id": second["id"]},
            },
            {
                "id": "s2",
                "skill": "partial_correlation",
                "parameters": {
                    "predictors": ["x"],
                    "outcomes": ["item_score"],
                    "covariates": ["age", "sex"],
                    "categorical_covariates": ["sex"],
                },
                "depends_on": ["s1"],
                "inputs": {"data": {"step_id": "s1", "output": "joined"}},
            },
            {
                "id": "s3",
                "skill": "effect_plot",
                "parameters": {},
                "depends_on": ["s2"],
                "inputs": {"data": {"step_id": "s2", "output": "associations"}},
            },
        ],
    }
    monkeypatch.setattr(agent, "model_json", lambda *a, **kw: body)
    plan = agent.create_plan(
        pid,
        ChatRequest(
            message=body["objective"],
            study=StudyConfig(independent=True),
            include_report=False,
            dataset_ids=[d["id"], second["id"]],
        ),
    )
    assert not plan["questions"], plan["questions"]
    run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
    worker.run_one(run)
    completed = db.get(run["id"], "run")
    assert completed["status"] == "completed" and not completed["partial"]
    second_result = completed["results"][1]
    assert second_result["metrics"]["matched_samples"] == 100
    assert second_result["evidence"][0]["upstream_inputs"]["data"]["output"] == "joined"
    # A changed upstream result cannot be consumed from cache or from Context.
    artifact = completed["results"][0]["artifacts"][0]
    from yanji.config import runtime_root

    (runtime_root() / artifact["storage"]).write_text("tampered")
    with pytest.raises(data.DataError, match="已变化"):
        worker.cache_key(plan["snapshot"], plan["steps"][1], completed["results"], pid)


def test_invalid_binding_dependency_and_output_are_rejected(research_data):
    pid, d, _ = research_data
    plan = AnalysisPlan.model_validate(
        {
            "objective": "图",
            "summary": "图",
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
                    "skill": "association_heatmap",
                    "inputs": {"data": {"step_id": "s1", "output": "made_up"}},
                },
            ],
        }
    )
    with pytest.raises(data.DataError, match="依赖"):
        agent.validate_plan(plan, pid, [d])
    plan.steps[1].depends_on = ["s1"]
    with pytest.raises(data.DataError, match="没有声明"):
        agent.validate_plan(plan, pid, [d])


def test_network_retains_sign_q_and_no_pseudo_zero_edges(research_data):
    pid, d, _ = research_data

    def source(step, rows):
        context = Context(pid, "test", step, agent.snapshot(pid), {})
        context.table(pd.DataFrame(rows), "associations", "真实关联")
        return {"step_id": step, "status": "success", "artifacts": context.artifacts}

    left = source(
        "s1",
        [
            {
                "predictor": "bugA",
                "outcome": "pathA",
                "effect": 0.5,
                "metric": "partial_spearman_rho",
                "p": 0.001,
                "q": 0.01,
            },
            {
                "predictor": "bugB",
                "outcome": "pathA",
                "effect": -0.3,
                "metric": "partial_spearman_rho",
                "p": 0.01,
                "q": 0.02,
            },
            {
                "predictor": "zero",
                "outcome": "pathA",
                "effect": 0,
                "metric": "partial_spearman_rho",
                "p": 1,
                "q": 1,
            },
        ],
    )
    right = source(
        "s2",
        [
            {
                "predictor": "pathA",
                "outcome": "score",
                "effect": -0.4,
                "metric": "standardized_beta",
                "p": 0.001,
                "q": 0.02,
            },
            {
                "predictor": "orphan",
                "outcome": "score",
                "effect": 0.3,
                "metric": "standardized_beta",
                "p": 0.01,
                "q": 0.01,
            },
        ],
    )
    ctx = Context(
        pid,
        "test",
        "s3",
        agent.snapshot(pid),
        {},
        [left, right],
        {
            "left": {"step_id": "s1", "output": "associations"},
            "right": {"step_id": "s2", "output": "associations"},
        },
    )
    result = execute(ctx, "association_network")
    assert result["status"] == "success" and result["metrics"]["edges"] == 3
    edges = pd.read_csv(ctx.directory / "network_edges.tsv", sep="\t")
    assert set(edges.effect) == {0.5, -0.3, -0.4} and (edges.weight > 0).all()
    assert not edges.source_label.isin(["zero", "orphan"]).any()
    assert len({n for n in edges.source if n.startswith("1::")}) == 1


def test_clr_before_candidate_selection_and_true_functional_guard(research_data):
    pid, meta, f = research_data
    rng = np.random.default_rng(5)
    matrix = pd.DataFrame(
        rng.dirichlet([1, 2, 3], len(f)).T,
        index=["taxA", "taxB", "taxC"],
        columns=f.index,
    )
    tax = data.import_bytes(
        pid,
        "tax.tsv",
        matrix.to_csv(sep="\t", index_label="feature").encode(),
        ImportOptions(kind="taxonomy", unit="fraction"),
    )
    producer = Context(pid, "test", "s1", agent.snapshot(pid), {})
    producer.table(pd.DataFrame({"feature": ["taxA"], "q": [0.01]}), "differential", "候选")
    params = SkillParams(
        metadata_id=meta["id"],
        dataset_id=tax["id"],
        outcomes=["y"],
        transform="clr",
        standardize=False,
    )
    ctx = Context(
        pid,
        "test",
        "s2",
        agent.snapshot(pid),
        params.model_dump(),
        [{"step_id": "s1", "status": "success", "artifacts": producer.artifacts}],
        {"candidates": {"step_id": "s1", "output": "differential"}},
    )
    output = execute(ctx, "adjusted_regression")
    assert output["status"] == "success" and output["metrics"]["tested"] == 1
    table = pd.read_csv(ctx.directory / "associations.tsv", sep="\t")
    assert table.predictor.tolist() == ["taxA"]
    func = pd.DataFrame(
        [[0.1] * len(f), [0.2] * len(f)],
        index=["PWY-X|speciesA", "PWY-X|speciesB"],
        columns=f.index,
    )
    fd = data.import_bytes(
        pid,
        "pathways.tsv",
        func.to_csv(sep="\t", index_label="Pathway").encode(),
        ImportOptions(kind="functional", unit="fraction"),
    )
    bad = Context(
        pid,
        "test",
        "s3",
        agent.snapshot(pid),
        SkillParams(metadata_id=meta["id"], dataset_id=fd["id"], outcomes=["y"]).model_dump(),
    )
    blocked = execute(bad, "adjusted_regression")
    assert blocked["status"] == "skipped" and "群落总" in blocked["summary"]


def test_forest_rejects_fabricated_or_missing_ci(research_data):
    pid, _, _ = research_data
    frame = pd.DataFrame(
        {
            "predictor": ["x"],
            "outcome": ["y"],
            "effect": [0.5],
            "metric": ["beta"],
            "p": [0.01],
            "q": [0.02],
        }
    )
    d = data.import_bytes(
        pid,
        "effects.csv",
        frame.to_csv(index=False).encode(),
        ImportOptions(kind="table"),
    )
    ctx = Context(
        pid,
        "test",
        "s1",
        agent.snapshot(pid),
        SkillParams(dataset_id=d["id"]).model_dump(),
    )
    assert execute(ctx, "effect_plot")["status"] == "skipped"
    ctx2 = Context(
        pid,
        "test",
        "s2",
        agent.snapshot(pid),
        SkillParams(dataset_id=d["id"], effect_style="lollipop").model_dump(),
    )
    assert execute(ctx2, "effect_plot")["status"] == "success"


def test_candidate_index_and_unadjusted_baseline_are_explicit(research_data):
    from yanji.skills.research import analysis_frames

    pid, d, f = research_data
    ctx = Context(
        pid,
        "candidate",
        "s1",
        agent.snapshot(pid),
        {"dataset_id": d["id"], "predictors": ["x", "age"], "outcomes": ["y"]},
    )
    ctx.inputs["candidates"] = pd.DataFrame({"q": [0.01]}, index=pd.Index(["x"], name="feature"))
    assert list(analysis_frames(ctx)[0].columns) == ["x"]
    p = agent.create_plan(
        pid,
        ChatRequest(
            mode="skill",
            skill_id="baseline_table",
            message="基线表",
            parameters=SkillParams(
                dataset_id=d["id"], fields=["age"], group_by="group", covariates=["sex"]
            ),
            study=StudyConfig(independent=True),
            include_report=False,
        ),
    )
    assert p["questions"] and any("未校正" in q for q in p["questions"])


def test_no_estimable_model_cannot_be_marked_complete(research_data):
    pid, d, f = research_data
    ctx = Context(
        pid,
        "constant",
        "s1",
        agent.snapshot(pid),
        {
            "dataset_id": d["id"],
            "predictors": ["x"],
            "outcomes": ["y"],
            "covariates": ["age"],
        },
    )
    from yanji.skills import research

    f["x"] = 1
    ctx.inputs["data"] = f
    ctx.params.dataset_id = None
    with pytest.raises(data.DataError, match="全部模型均不可估计"):
        research.associations(ctx, "adjusted_regression")
    assert (ctx.directory / "analysis_audit.tsv").is_file()


def test_result_schema_and_plot_columns_are_checked_before_approval(research_data):
    from yanji.result_inputs import describe_bindings

    pid, d, _ = research_data
    plan = AnalysisPlan.model_validate(
        {
            "objective": "分析后画图",
            "summary": "先分析再绘图",
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
                    "skill": "effect_plot",
                    "depends_on": ["s1"],
                    "inputs": {"data": {"step_id": "s1", "output": "associations"}},
                },
            ],
        }
    )
    columns = describe_bindings(plan.steps[1], plan, [d])["data"]["columns"]
    assert {"effect", "ci_low", "ci_high", "q"} <= set(columns)
    bad = agent.create_plan(
        pid,
        ChatRequest(
            mode="skill",
            skill_id="effect_plot",
            message="画森林图",
            parameters=SkillParams(
                dataset_id=d["id"], result_predictor="absent", effect_metric="beta"
            ),
            include_report=False,
        ),
    )
    assert bad["questions"] and any("字段" in q for q in bad["questions"])
    plan.steps[1].inputs = {"wrong": plan.steps[1].inputs["data"]}
    from yanji.skills.research import validate_parameters

    with pytest.raises(data.DataError, match="别名"):
        validate_parameters(plan.steps[1], [d], {})


def test_empty_network_is_a_valid_null_finding(research_data):
    pid, _, _ = research_data
    left = Context(pid, "empty-network", "s1", agent.snapshot(pid), {})
    left.table(
        pd.DataFrame(
            [
                {
                    "predictor": "bug",
                    "outcome": "path",
                    "effect": 0.01,
                    "q": 0.9,
                    "p": 0.5,
                    "metric": "rho",
                }
            ]
        ),
        "associations",
        "有效但不显著",
    )
    right = Context(pid, "empty-network", "s2", agent.snapshot(pid), {})
    right.table(
        pd.DataFrame(
            [
                {
                    "predictor": "path",
                    "outcome": "score",
                    "effect": 0.02,
                    "q": 0.9,
                    "p": 0.5,
                    "metric": "rho",
                }
            ]
        ),
        "associations",
        "有效但不显著",
    )
    completed = [
        {"step_id": "s1", "status": "success", "artifacts": left.artifacts},
        {"step_id": "s2", "status": "success", "artifacts": right.artifacts},
    ]
    ctx = Context(
        pid,
        "empty-network",
        "s3",
        agent.snapshot(pid),
        {},
        completed,
        {
            "left": {"step_id": "s1", "output": "associations"},
            "right": {"step_id": "s2", "output": "associations"},
        },
    )
    result = execute(ctx, "association_network")
    assert result["status"] == "success" and result["metrics"] == {
        "edges": 0,
        "nodes": 0,
    }
    assert pd.read_csv(ctx.directory / "network_edges.tsv", sep="\t").empty
    assert any(e["values"].get("no_findings") for e in result["evidence"])


def test_legacy_association_publishes_reusable_canonical_result(example):
    pid = example["id"]
    taxonomy = next(d for d in data.active(pid) if d["data_type"] == "taxonomy")
    metadata = data.import_bytes(
        pid,
        "continuous.tsv",
        pd.DataFrame(
            {
                "sample_id": taxonomy["samples"],
                "value": np.arange(len(taxonomy["samples"])),
            }
        )
        .to_csv(sep="\t", index=False)
        .encode(),
        ImportOptions(kind="metadata"),
    )
    snap = agent.snapshot(pid, [taxonomy["id"], metadata["id"]])
    source = Context(pid, "legacy-bridge", "s1", snap, {"variable": "value"})
    result = execute(source, "taxa_association")
    result["step_id"] = "s1"
    assert result["status"] == "success"
    table = pd.read_csv(source.directory / "associations.tsv", sep="\t")
    assert {
        "feature",
        "predictor",
        "outcome",
        "effect",
        "metric",
        "rho",
        "p",
        "q",
    } <= set(table.columns)
    assert np.allclose(table.effect, table.rho, equal_nan=True)
    plot = Context(
        pid,
        "legacy-bridge",
        "s2",
        snap,
        {"effect_style": "lollipop", "significance": "all"},
        [result],
        {"data": {"step_id": "s1", "output": "associations"}},
    )
    assert execute(plot, "effect_plot")["status"] == "success"
