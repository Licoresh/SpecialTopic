from io import BytesIO
import html
import json
import re
import pandas as pd

def safe_table(frame):
    # Prevent spreadsheet applications from executing researcher text as formulas.
    out = frame.copy()
    for col in out.select_dtypes(include=["object", "string"]):
        out[col] = out[col].map(lambda x: "'" + x if isinstance(x, str) and x.lstrip().startswith(("=", "+", "-", "@")) else x)
    return out

def export_csv(frame):
    return safe_table(frame).to_csv(index=False).encode("utf-8-sig")

def export_excel(tables, metadata):
    buffer = BytesIO()
    overflow = []
    controls = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in tables.items():
            safe = safe_table(frame).reset_index(drop=True)
            for column in safe.select_dtypes(include=["object", "string"]):
                for row, value in safe[column].items():
                    if not isinstance(value, str):
                        continue
                    value = controls.sub(lambda match: "\\u" + format(ord(match.group()), "04x"), value)
                    if len(value) > 32000:
                        for part, start in enumerate(range(0, len(value), 30000), 1):
                            overflow.append({"table": name, "excel_row": row+2, "column": column, "part": part, "text": value[start:start+30000]})
                        value = "Full text preserved in long_text sheet; match table, excel_row and column, then concatenate ordered parts."
                    safe.at[row, column] = value
            safe.to_excel(writer, sheet_name=name[:31], index=False)
        metadata_rows = []
        for key, value in metadata.items():
            serialized = json.dumps(value, default=str)
            for part, start in enumerate(range(0, len(serialized), 30000), 1):
                metadata_rows.append({"key": key, "part": part, "value": serialized[start:start+30000]})
        safe_table(pd.DataFrame(metadata_rows)).to_excel(writer, sheet_name="analysis_metadata", index=False)
        if overflow:
            safe_table(pd.DataFrame(overflow)).to_excel(writer, sheet_name="long_text", index=False)
    return buffer.getvalue()

def export_html(tables, metadata):
    chunks = ["<!doctype html><html><head><meta charset='utf-8'><title>Research results</title><style>body{font:15px system-ui;max-width:1200px;margin:40px auto}table{border-collapse:collapse}td,th{padding:7px;border:1px solid #ddd}</style></head><body><h1>The Future of Work in the Philippines</h1>",
              "<p>Observed evidence within the selected sample. Not clearly mapped to PSF-AAI does not establish that a skill is absent from the framework. No causal claims are made.</p>",
              "<h2>Analysis metadata</h2><pre>" + html.escape(json.dumps(metadata, indent=2, default=str)) + "</pre>"]
    for name, frame in tables.items():
        chunks.append("<h2>" + html.escape(name) + "</h2>" + frame.head(200).to_html(index=False, escape=True))
        if len(frame) > 200:
            chunks.append("<p>Preview limited to 200 rows; full tables are in the CSV/Excel exports.</p>")
    return ("".join(chunks) + "</body></html>").encode()


def export_research_report(tables, metadata):
    """Create a reproducible, evidence-led Markdown report from current tables."""
    def markdown_table(frame):
        columns = [str(column) for column in frame.columns]
        def cell(value):
            return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
        rows = ["| " + " | ".join(cell(column) for column in columns) + " |",
                "| " + " | ".join("---" for _ in columns) + " |"]
        rows.extend("| " + " | ".join(cell(value) for value in row) + " |"
                    for row in frame.itertuples(index=False, name=None))
        return "\n".join(rows)
    lines = [
        "# The Future of Work in the Philippines",
        "## Philippine AI and analytics job advertisements and TESDA PSF-AAI",
        "",
        "**Report status:** descriptive draft generated from the currently selected records. Researcher review is required before citing findings.",
        "",
        "## Study focus",
        "This analysis describes skills stated in Philippine AI- and analytics-related job advertisements and compares observed employer terminology with the TESDA Philippine Skills Framework for Analytics and Artificial Intelligence (PSF-AAI). It does not analyze curricula or infer worker proficiency.",
        "",
        "## Dataset and method",
        f"- Selected job advertisements: {metadata.get('dataset_counts', {}).get('jobs', 'Not recorded')}",
        f"- PSF-AAI competencies in the active reference: {metadata.get('dataset_counts', {}).get('psf_competencies', 'Not recorded')}",
        f"- Generated: {metadata.get('timestamp', 'Not recorded')}",
        "- Skill demand counts distinct job advertisements containing each normalized phrase; repeated mentions within one advertisement count once.",
        "- PSF alignment is a heuristic comparison against the active reference. Similarity thresholds are configurable research settings, not official TESDA standards.",
        "- Requirement phrases found by text patterns are evidence candidates. Researchers must inspect the cited source context before treating them as requirements.",
        "",
        "## Findings",
        "The tables below report observed counts in the selected sample. They do not estimate the full Philippine labor market.",
        "",
    ]
    preferred = [
        ("employer_skill_demand", "Most frequently observed employer skills"),
        ("job_title_counts", "Job titles"),
        ("job_family_counts", "Source-provided occupational families"),
        ("education_requirement_counts", "Education requirements stated in source fields"),
        ("experience_requirement_counts", "Experience requirements stated in source fields"),
        ("employer_psf_alignment", "Employer skill comparison with PSF-AAI"),
        ("alignment_results", "Phrase-level PSF-AAI alignment results"),
        ("unmapped_skills", "Frequently observed phrases not clearly mapped"),
    ]
    for key, heading in preferred:
        frame = tables.get(key)
        if frame is not None and not frame.empty:
            lines.extend([f"### {heading}", "", markdown_table(frame.head(100)), ""])
    evidence = tables.get("requirement_evidence")
    if evidence is not None and not evidence.empty:
        lines.extend([
            "### Requirement evidence for researcher verification", "",
            "This appendix preserves the ad ID, source field, source URL and text context. Pattern-detected text is explicitly marked as a candidate rather than a confirmed requirement.", "",
            markdown_table(evidence.head(250)), "",
        ])
    lines.extend(["## Limitations", ""])
    limitations = metadata.get("limitations", "")
    lines.append(str(limitations) if limitations else "Interpret results within the sampling frame and source coverage documented by the research team.")
    lines.extend([
        "- Job advertisements are a selected sample; counts describe this sample and are not workforce prevalence estimates.",
        "- Missing or ambiguous source fields are not inferred. Relative or missing dates limit time-trend analysis.",
        "- A phrase not mapped to the active PSF-AAI reference is not proof the framework lacks that competency.",
        "- Confirm job relevance, Philippine provenance, duplicate handling, and the active PSF-AAI reference before reporting results.",
        "- This generated report contains descriptive evidence, not causal conclusions or validated model-performance claims.",
        "",
    ])
    return ("\n".join(lines)).encode("utf-8")
