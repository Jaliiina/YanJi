import pytest

from yanji.contracts import ImportOptions
from yanji.data import DataError, inspect


def test_long_matches_wide():
    long = b"sample_id\tfeature_id\tvalue\tunit\nA\tX\t20\tpercent\nB\tX\t40\tpercent\nA\tY\t80\tpercent\nB\tY\t60\tpercent\n"
    matrix, info = inspect(long, "upstream.tsv", ImportOptions(kind="taxonomy"))
    wide, _ = inspect(
        b"ID\tA\tB\nX\t20\t40\nY\t80\t60",
        "wide.tsv",
        ImportOptions(kind="taxonomy", unit="percent"),
    )
    assert matrix.values.tolist() == wide.values.tolist()
    assert info["samples"] == ["A", "B"] and info["unit"] == "fraction"
    assert any(t["operation"] == "canonical_long_to_matrix" for t in info["transformations"])


@pytest.mark.parametrize(
    "text,options,match",
    [
        ("sample_id,feature_id,value\nA,X,1", ImportOptions(), "明确选择"),
        (
            "sample_id,feature_id,value\nA,X,1\nA,X,2",
            ImportOptions(kind="taxonomy", unit="counts"),
            "重复",
        ),
        (
            "sample_id,feature_id,value\nA,X,1\nB,Y,2",
            ImportOptions(kind="taxonomy", unit="counts"),
            "缺少",
        ),
        (
            "sample_id,feature_id,value,unit\nA,X,1,coverage",
            ImportOptions(kind="functional"),
            "覆盖度",
        ),
        (
            "sample_id,feature_id,value,unit\nA,X,1,percent",
            ImportOptions(kind="taxonomy", unit="fraction"),
            "冲突",
        ),
        (
            "sample_id,feature_id,value\nA,X,-1",
            ImportOptions(kind="taxonomy", unit="counts"),
            "非负",
        ),
    ],
)
def test_long_rejects_ambiguous(text, options, match):
    with pytest.raises(DataError, match=match):
        inspect(text.encode(), "long.csv", options)
