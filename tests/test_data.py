import pytest

from yanji.contracts import ImportOptions
from yanji.data import (
    DataError,
    import_bytes,
    inspect,
    load_frame,
    mapping_suggestions,
    remap,
)


@pytest.mark.parametrize(
    "raw,match",
    [
        ("ID\tA\tA\nx\t1\t2", "重复"),
        ("ID\tA\nx\t1\nx\t2", "重复"),
        ("ID\tA\nx\t-1", "非负"),
        ("ID\tA\nx\tNA", "非数值"),
        ("ID\tA\nx\tinf", "非负"),
        ("ID\tA\nx\t", "非数值"),
        ("ID\tA\nx\t1\t2", "列"),
        ("ID\tA", "没有数据"),
    ],
)
def test_reject_invalid(raw, match):
    with pytest.raises(DataError, match=match):
        inspect(raw.encode(), "data.tsv", ImportOptions(kind="taxonomy", unit="counts"))


def test_comments_and_rank():
    raw = (
        b"ID\tA\n#metaphlan4\nk__Bacteria\t100\nk__Bacteria|g__X\t100\nk__Bacteria|g__X|s__Y\t100\n"
    )
    f, info = inspect(raw, "taxonomy.tsv", ImportOptions())
    assert f.iloc[-1, 0] == 1
    assert info["summary"]["rank_counts"]["species"] == 1
    assert info["unit"] == "fraction"


def test_stratification_not_merged():
    raw = b"# Pathway\tA\nPWY: example|g__X.s__Y\t0.2\nUNINTEGRATED|g__X.s__Y\t0.1\n"
    f, info = inspect(raw, "pathabundance_relab_stratified.tsv", ImportOptions())
    assert info["summary"]["total_pathways"] == 0
    assert info["summary"]["stratified_rows"] == 2
    assert len(f) == 2


def test_unknown_table_is_preserved_until_classified():
    frame, info = inspect(b"ID\tA\nx\t0.2", "x.tsv", ImportOptions())
    assert info["data_type"] == "table" and frame.columns.tolist() == ["ID", "A"]
    with pytest.raises(DataError, match="单位"):
        inspect(b"ID\tA\nx\t0.2", "x.tsv", ImportOptions(kind="taxonomy"))


def test_non_numeric_extra_column():
    with pytest.raises(DataError, match="非数值"):
        inspect(
            b"ignored,sample,X,Y\nz,S1,1,2\nz,S2,2,3",
            "x.csv",
            ImportOptions(kind="taxonomy", unit="counts", id_column="sample"),
        )


def test_transpose():
    f, info = inspect(
        b"sample\tX\tY\nS1\t1\t2\nS2\t3\t4",
        "x.tsv",
        ImportOptions(kind="taxonomy", unit="counts", transpose=True),
    )
    assert info["samples"] == ["S1", "S2"] and f.shape == (2, 2)


def test_immutable_mapping(project):
    pid = project["id"]
    import_bytes(pid, "tax.tsv", b"ID\tF1\tF2\nx\t1\t2", ImportOptions(unit="counts"))
    func = import_bytes(
        pid,
        "pathabundance_relab.tsv",
        b"# Pathway\tF2_combined\tF1_combined\nPWY|sp\t.2\t.3",
        ImportOptions(),
    )
    suggestion = mapping_suggestions(pid, func)
    assert suggestion["needs_confirmation"]
    assert suggestion["mapping"] == {"F2_combined": "F2", "F1_combined": "F1"}
    newer = remap(func["id"], suggestion["mapping"], [])
    assert load_frame(func).columns.tolist() == ["F2_combined", "F1_combined"]
    assert load_frame(newer).columns.tolist() == ["F2", "F1"]
    assert newer["parent_version"] == func["id"] and newer["revision"] == 2
    with pytest.raises(DataError):
        remap(newer["id"], {"F1": "F2"}, [])


def test_metadata_preserves_string_ids(project):
    d = import_bytes(
        project["id"],
        "meta.tsv",
        b"sample_id\tgroup\n001\tA\n002\tB",
        ImportOptions(kind="metadata"),
    )
    assert load_frame(d).index.tolist() == ["001", "002"]


def test_canonical_table_does_not_suggest_mapping_to_suffixes(project):
    pid = project["id"]
    tax = import_bytes(pid, "tax.tsv", b"ID\tF2450\tF1\nx\t1\t2", ImportOptions(unit="counts"))
    func = import_bytes(
        pid,
        "pathabundance_relab.tsv",
        b"# Pathway\tF2450clean_combined\tF1_combined\nPWY|sp\t.2\t.3",
        ImportOptions(),
    )
    assert not mapping_suggestions(pid, tax)["needs_confirmation"]
    suggestion = mapping_suggestions(pid, func)
    assert suggestion["mapping"]["F2450clean_combined"] == "F2450"
    assert not suggestion["unmatched"]


def test_normalized_data_integrity(project):
    from yanji.config import runtime_root

    d = import_bytes(project["id"], "table.tsv", b"ID\tA\nx\t1", ImportOptions(unit="counts"))
    path = runtime_root() / d["storage"] / "matrix.json.gz"
    path.write_bytes(b"changed")
    with pytest.raises(DataError, match="校验失败"):
        load_frame(d)
