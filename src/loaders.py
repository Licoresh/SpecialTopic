import csv
from io import BytesIO, StringIO
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
from .validation import validate_mapping
from .config import FIELDS


def _unique_headers(headers):
    """Keep every source column while making blank or repeated labels addressable."""
    names, changes, used = [], [], set()
    for index, header in enumerate(headers, start=1):
        original = "" if header is None else str(header).strip()
        base = original or f"unnamed_column_{index}"
        candidate, suffix = base, 2
        while candidate.casefold() in used:
            candidate = f"{base}__{suffix}"
            suffix += 1
        used.add(candidate.casefold())
        names.append(candidate)
        if candidate != original:
            changes.append({"source_header": original or "(blank)", "imported_as": candidate})
    return names, changes

def load_data(content, filename, sheet=0, encoding="utf-8-sig"):
    if not content:
        raise ValueError("The uploaded file is empty.")
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".csv":
            text = content.decode(encoding)
            reader = csv.reader(StringIO(text))
            header = next(reader, [])
            if not header:
                raise ValueError("CSV header row is empty.")
            headers, header_changes = _unique_headers(header)
            for ordinal, row in enumerate(reader, start=2):
                if row and len(row) != len(header):
                    raise ValueError(f"CSV record {ordinal} has {len(row)} fields but the header has {len(header)}. Check delimiters and quoting.")
            frame = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False,
                                header=0, names=headers)
        elif ext == ".xlsx":
            book = load_workbook(BytesIO(content), read_only=True, data_only=True)
            try:
                ws = book.worksheets[sheet] if isinstance(sheet, int) else book[sheet]
                header = next(ws.values, ())
                if not header:
                    raise ValueError("XLSX header row is empty.")
                headers, header_changes = _unique_headers(header)
            finally:
                book.close()
            frame = pd.read_excel(BytesIO(content), sheet_name=sheet, dtype=str, keep_default_na=False)
            frame.columns = headers
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
    frame.attrs["header_changes"] = header_changes
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
