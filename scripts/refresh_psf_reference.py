"""Rebuild the released role links/context from the bundled official PDF."""
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.psf_source import parse_framework


def main():
    path = ROOT / "data/reference/psf_aai_default.csv"
    current = pd.read_csv(path, dtype=str, keep_default_na=False)
    parsed, links = parse_framework(path.with_name("psf_aai_official.pdf"))
    keys = ["competency_id", "competency_name", "source_hash"]
    if set(map(tuple, current[keys].values)) != set(map(tuple, parsed[keys].values)):
        raise ValueError("Competency identities or PDF edition changed; review before release.")
    indexed = parsed.set_index("competency_name")
    for field in ("job_role", "occupational_family"):
        current[field] = current.competency_name.map(indexed[field])
    for index, row in current.iterrows():
        aliases = dict.fromkeys(term.strip() for term in
                               (row.aliases + ";" + indexed.loc[row.competency_name, "aliases"]).split(";") if term.strip())
        current.at[index, "aliases"] = "; ".join(aliases)
    current.to_csv(path, index=False, encoding="utf-8-sig")
    fields = ["job_role", "occupational_family", "role_description", "role_source_page", "source_page", "source_url", "source_hash"]
    profiles = links.drop_duplicates("job_role")[fields].sort_values("job_role")
    path.with_name("psf_aai_role_profiles.json").write_text(
        json.dumps(profiles.to_dict("records"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Released {len(current)} competencies, {links.job_role.nunique()} roles, {len(links)} role/level links, {links.occupational_family.nunique()} families.")


if __name__ == "__main__":
    main()
