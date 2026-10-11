import csv
from io import BytesIO, StringIO
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
from .validation import validate_mapping
from .config import FIELDS

def load_data(content, filename, sheet=0, encoding="utf-8-sig"):
    if not content:
        raise ValueError("The uploaded file is empty.")
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".csv":
            text = content.decode(encoding)
            reader = csv.reader(StringIO(text))
            header = next(reader, [])
            if not header or len(set(header)) != len(header) or any(not x.strip() for x in header):
                raise ValueError("CSV headers must be nonempty and unique.")
            for ordinal, row in enumerate(reader, start=2):
                if row and len(row) != len(header):
                    raise ValueError(f"CSV record {ordinal} has {len(row)} fields but the header has {len(header)}. Check delimiters and quoting.")
            frame = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)
        elif ext == ".xlsx":
            book = load_workbook(BytesIO(content), read_only=True, data_only=True)
            try:
                ws = book.worksheets[sheet] if isinstance(sheet, int) else book[sheet]
                header = next(ws.values, ())
                if not header or None in header or len(set(header)) != len(header):
                    raise ValueError("XLSX headers must be nonempty and unique.")
            finally:
                book.close()
            frame = pd.read_excel(BytesIO(content), sheet_name=sheet, dtype=str, keep_default_na=False)
        else:
            raise ValueError("Use a CSV or XLSX file.")
    except UnicodeDecodeError as exc:
        raise ValueError("Cannot decode this CSV. Select its encoding (UTF-8 or Windows-1252).") from exc
    except (pd.errors.ParserError, pd.errors.EmptyDataError, KeyError, IndexError) as exc:
        raise ValueError(f"Cannot read this table: {exc}") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The file is not a readable CSV/XLSX workbook.") from exc
    if frame.empty:
        raise ValueError("The file contains no data rows.")
    frame.columns = frame.columns.astype(str).str.strip()
    if any(not col for col in frame.columns):
        raise ValueError("Column headers must not be blank.")
    if frame.columns.duplicated().any():
        raise ValueError("Column names become duplicates after trimming spaces.")
    return frame.fillna("")

def map_columns(frame, mapping, kind, dataset_hash):
    validate_mapping(frame, mapping, kind)
    out = pd.DataFrame(index=frame.index)
    for field in FIELDS[kind]:
        out[field] = frame[mapping[field]] if mapping.get(field) else ""
    out["_raw_row"] = range(2, len(out) + 2)
    out["_dataset_hash"] = dataset_hash
    out["source_id"] = [f"{kind}:{dataset_hash[:16]}:{i}" for i in out._raw_row]
    if kind == "psf_aai":
        out["competency_id"] = out.competency_id.where(out.competency_id.ne(""), out.source_id)
    return out
