import math

import numpy as np
import pandas as pd
import pytest

from yanji import db
from yanji.agent import snapshot
from yanji.contracts import ImportOptions, SkillParams
from yanji.data import import_bytes
from yanji.skills.analysis import alpha_values, distance_matrix, execute
from yanji.skills.context import Context


def ctx(pid, **params):
    return Context(pid, db.uid(), "s1", snapshot(pid), SkillParams(**params).model_dump())


def test_alpha_known_values():
    result = alpha_values(pd.DataFrame([[0.5, 0.5], [1, 0]], index=["a", "b"]))
    assert result.loc["a", "Shannon"] == pytest.approx(math.log(2))
    assert result.loc["a", "Simpson 1-D"] == pytest.approx(0.5)
    assert result.loc["a", "Pielou"] == pytest.approx(1)
    assert np.isnan(result.loc["b", "Pielou"])


def test_bray_known_values():
    dm = distance_matrix(pd.DataFrame([[1, 0], [0, 1], [0.5, 0.5]], index=["a", "b", "c"]))
    assert dm["a", "b"] == 1 and dm["a", "c"] == 0.5


@pytest.mark.parametrize(
    "skill",
    [
        "data_check",
        "composition",
        "alpha_diversity",
        "beta_diversity",
        "alpha_comparison",
        "community_comparison",
        "differential",
        "functional_overview",
        "functional_differential",
        "pathway_contribution",
    ],
)
def test_example_skills(example, skill):
    out = execute(ctx(example["id"], permutations=99), skill)
    assert out["status"] == "success", out
    assert out["evidence"] and out["artifacts"]
    assert out["summary"]
    if skill == "alpha_comparison":
        rows = out["metrics"]["results"]
        assert all(r["q"] is None or r["q"] >= r["p"] for r in rows)


def test_permutation_repeatable(example):
    a = execute(ctx(example["id"], permutations=99), "community_comparison")
    b = execute(ctx(example["id"], permutations=99), "community_comparison")
    assert a["metrics"] == b["metrics"]


def test_constant_and_zero(project):
    pid = project["id"]
    import_bytes(pid, "tax.tsv", b"ID\tA\tB\tC\nx\t0\t0\t0", ImportOptions(unit="fraction"))
    out = execute(ctx(pid), "alpha_diversity")
    assert out["status"] == "skipped"
    import_bytes(pid, "tax.tsv", b"ID\tA\tB\tC\nx\t1\t1\t1", ImportOptions(unit="fraction"))
    out = execute(ctx(pid), "beta_diversity")
    assert out["status"] == "skipped"


def test_group_preconditions(example):
    db.update(
        example["id"], study={"group_column": "group", "independent": False, "excluded_samples": []}
    )
    out = execute(ctx(example["id"]), "differential")
    assert out["status"] == "skipped"
    assert "独立" in out["summary"]


def test_strat_only_not_functional_total(project):
    pid = project["id"]
    import_bytes(
        pid,
        "pathabundance_relab.tsv",
        b"# Pathway\tA\tB\nPWY: demo|g__X.s__Y\t.1\t.2",
        ImportOptions(),
    )
    assert execute(ctx(pid), "functional_overview")["status"] == "skipped"
    out = execute(ctx(pid), "pathway_contribution")
    assert out["status"] == "success"
    assert any("不是群落" in x for x in out["warnings"])
