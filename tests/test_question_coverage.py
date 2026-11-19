"""Common research questions must land on a skill that actually scopes the data."""

import numpy as np
import pandas as pd

from yanji import agent, db
from yanji.contracts import ChatRequest, ImportOptions, RunConfirm, SkillParams
from yanji.data import import_bytes
from yanji.flask_routes import confirm_run
from yanji.skills.analysis import execute
from yanji.skills.context import Context
from yanji.worker import run_one


def taxonomy(pid, n=12):
    ids = [f"F{2000 + i}" for i in range(n)]
    rng = np.random.default_rng(0)
    rows = []
    names = []
    for i in range(6):
        names.append(
            f"k__Bacteria|p__Firmicutes|c__Clostridia|o__Eubacteriales|f__Oscillospiraceae|g__Faecalibacterium|s__Species_{i}"
        )
        rows.append(rng.integers(1, 20, n))
    frame = pd.DataFrame(rows, index=names, columns=ids)
    frame.index.name = "clade_name"
    return import_bytes(
        pid,
        "taxonomy.tsv",
        frame.to_csv(sep="\t").encode(),
        ImportOptions(kind="taxonomy", unit="counts"),
    ), ids


def test_named_sample_comparison_only_uses_those_samples(project):
    pid = project["id"]
    _, ids = taxonomy(pid, 12)
    a, b = ids[0], ids[1]
    plan = agent.create_plan(
        pid,
        ChatRequest(
            message=f"分析{a}\t{b}的菌种组成差异",
            include_report=False,
        ),
    )
    step = next(s for s in plan["steps"] if s["skill"] == "sample_comparison")
    assert step["parameters"]["samples"] == [a, b]
    assert plan["summary"]
    run = confirm_run(pid, RunConfirm(plan_id=plan["id"]))
    run_one(run)
    result = db.get(run["id"])["results"][-1]
    assert result["status"] == "success", result["summary"]
    assert result["metrics"]["samples"] == [a, b]
    assert "2 个指定样本" in result["summary"] or "2 个" in result["summary"]


def test_sample_profile_and_core_taxa(project):
    pid = project["id"]
    tax, ids = taxonomy(pid, 10)
    profile = agent.create_plan(
        pid,
        ChatRequest(
            message=f"看看{ids[0]}的菌种组成",
            include_report=False,
        ),
    )
    assert any(s["skill"] == "sample_profile" for s in profile["steps"])
    core = agent.create_plan(
        pid,
        ChatRequest(
            message="核心菌有哪些",
            mode="skill",
            skill_id="core_taxa",
            include_report=False,
            parameters=SkillParams(prevalence=0.5, rank="species"),
        ),
    )
    run = confirm_run(pid, RunConfirm(plan_id=core["id"]))
    run_one(run)
    assert db.get(run["id"])["results"][-1]["status"] == "success"
    ctx = Context(
        pid,
        db.uid(),
        "s1",
        agent.snapshot(pid),
        SkillParams(samples=ids[:3], rank="phylum").model_dump(),
    )
    out = execute(ctx, "sample_profile")
    assert out["status"] == "success"
    assert out["metrics"]["rank"] == "phylum"


def test_composition_with_samples_does_not_use_full_cohort(project):
    pid = project["id"]
    _, ids = taxonomy(pid, 15)
    ctx = Context(
        pid,
        db.uid(),
        "s1",
        agent.snapshot(pid),
        SkillParams(samples=[ids[0], ids[1]], rank="species", top_n=5).model_dump(),
    )
    out = execute(ctx, "composition")
    assert out["status"] == "success"
    assert out["metrics"]["samples"] == 2


def test_multi_group_alpha_uses_kruskal(project):
    pid = project["id"]
    _, ids = taxonomy(pid, 12)
    meta = pd.DataFrame(
        {
            "sample_id": ids,
            "group": ["A"] * 4 + ["B"] * 4 + ["C"] * 4,
        }
    ).set_index("sample_id")
    import_bytes(
        pid,
        "meta.tsv",
        meta.to_csv(sep="\t").encode(),
        ImportOptions(kind="metadata"),
    )
    snap = agent.snapshot(
        pid,
        study={
            "group_column": "group",
            "independent": True,
            "excluded_samples": [],
        },
    )
    ctx = Context(
        pid,
        db.uid(),
        "s1",
        snap,
        SkillParams(group_values=["A", "B", "C"], rank="species").model_dump(),
    )
    out = execute(ctx, "alpha_comparison")
    assert out["status"] == "success"
    assert out["metrics"]["groups"] == ["A", "B", "C"]
    assert any(r.get("test") == "Kruskal-Wallis" for r in out["metrics"]["results"])


def test_fake_full_cohort_contrast_is_rejected(project, monkeypatch):
    pid = project["id"]
    _, ids = taxonomy(pid, 8)
    body = {
        "objective": f"分析{ids[0]}与{ids[1]}的菌种组成差异",
        "summary": "对两个样本做对比",
        "steps": [
            {
                "id": "s1",
                "skill": "composition",
                "reason": "假装对比",
                "parameters": {"title": f"{ids[0]} 与 {ids[1]} 对比"},
            }
        ],
        "questions": [],
    }
    monkeypatch.setattr(agent, "model_json", lambda _m: body)
    import yanji.routing as routing

    # Bypass the fast path so the model plan is checked for missing samples.
    monkeypatch.setattr(routing, "resolve_named_samples", lambda *_a, **_k: None)
    try:
        agent.create_plan(
            pid,
            ChatRequest(
                message=f"分析{ids[0]}与{ids[1]}的菌种组成差异",
                include_report=False,
            ),
        )
        raised = False
    except agent.ModelError as exc:
        raised = "samples" in str(exc) or "样本" in str(exc)
    assert raised
