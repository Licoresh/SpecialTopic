from io import BytesIO
import pandas as pd
import pytest
from src.loaders import load_data, map_columns
from src.storage import archive_raw

def test_csv_xlsx_and_column_mapping():
    raw = pd.DataFrame({"Position": ["Analyst"], "Details": ["C++ and SQL"]})
    for ext in ("csv", "xlsx"):
        if ext == "csv":
            content = raw.to_csv(index=False).encode()
        else:
            buffer = BytesIO()
            raw.to_excel(buffer, index=False)
            content = buffer.getvalue()
        loaded = load_data(content, "test."+ext)
        mapped = map_columns(loaded, {"job_title": "Position", "job_description": "Details"}, "jobs", "testhash")
        assert mapped.job_description.iloc[0] == "C++ and SQL"
        assert mapped.source_id.iloc[0] == "jobs:testhash:2"

@pytest.mark.parametrize("content,name", [(b"", "a.csv"), (b"a\n", "a.csv"), (b"bad", "a.xlsx"), (b"a\n1", "a.txt"), (b"a,b\n1,2,3", "a.csv")])
def test_invalid_files(content, name):
    with pytest.raises(ValueError):
        load_data(content, name)


def test_duplicate_and_blank_csv_headers_are_kept_as_unique_columns():
    loaded = load_data(b"job_title,source_name,source_name,\nAnalyst,first,second,extra\n", "ads.csv")

    assert loaded.columns.tolist() == ["job_title", "source_name", "source_name__2", "unnamed_column_4"]
    assert loaded.iloc[0].tolist() == ["Analyst", "first", "second", "extra"]
    assert loaded.attrs["header_changes"] == [
        {"source_header": "source_name", "imported_as": "source_name__2"},
        {"source_header": "(blank)", "imported_as": "unnamed_column_4"},
    ]

def test_encoding_and_mapping_errors():
    content = "text\ncafé".encode("cp1252")
    with pytest.raises(ValueError, match="encoding"):
        load_data(content, "a.csv")
    assert load_data(content, "a.csv", encoding="cp1252").iloc[0,0] == "café"
    raw = pd.DataFrame({"x":["word"]})
    with pytest.raises(ValueError):
        map_columns(raw, {"job_title":"x", "job_description":"x"}, "jobs", "a")
    with pytest.raises(ValueError):
        map_columns(raw, {}, "jobs", "a")

def test_raw_bytes_immutable(workspace):
    content = b"text\nPython"
    archive_raw(content, "jobs.csv", "jobs")
    archive_raw(b"text\nSQL", "jobs.csv", "jobs")
    files = list((workspace/"data/raw").glob("*.csv"))
    assert len(files) == 2
    assert content in [f.read_bytes() for f in files]
