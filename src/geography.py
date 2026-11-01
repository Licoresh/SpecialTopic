"""Conservative, offline Philippine location grouping against a dated PSGC subset.

This is an exact-name lookup, not a complete address geocoder. Unrecognized,
conflicting and multiple-locality strings require review rather than guessing.
"""
import re

import pandas as pd

from .cleaning import normalize_text

PSGC_SOURCE = "https://psa.gov.ph/classification/psgc/summary"
PSGC_REFERENCE_DATE = "2026-10-31"

# Region membership checked against PSA's current PSGC summary and city listing.
# Island group is the dashboard's broad geographical grouping, not a PSGC level.
_REGION_GROUPS = {
    "luzon": {
        "national capital region": ("ncr", "metro manila", "manila"),
        "cordillera administrative region": ("car", "cordillera"),
        "ilocos region": ("region i", "region 1"),
        "cagayan valley": ("region ii", "region 2"),
        "central luzon": ("region iii", "region 3"),
        "calabarzon": ("region iv-a", "region 4a", "region iv a"),
        "mimaropa": ("mimaropa region", "region iv-b", "region 4b"),
        "bicol region": ("bicol", "region v", "region 5"),
    },
    "visayas": {
        "western visayas": ("region vi", "region 6"),
        "central visayas": ("region vii", "region 7", "cebu", "cebu province", "bohol"),
        "eastern visayas": ("region viii", "region 8"),
        "negros island region": ("nir", "negros occidental", "negros oriental", "siquijor"),
    },
    "mindanao": {
        "zamboanga peninsula": ("region ix", "region 9"),
        "northern mindanao": ("region x", "region 10"),
        "davao region": ("region xi", "region 11"),
        "soccsksargen": ("region xii", "region 12"),
        "caraga": ("region xiii", "region 13"),
        "bangsamoro autonomous region in muslim mindanao": ("barmm",),
    },
}

# Short names are accepted only where this subset can identify an unambiguous
# locality. Bare Manila/Cebu/Iloilo/Davao remain broad or need review.
_CITY_REGIONS = {
    "national capital region": "manila city|quezon city|makati|taguig|pasig|mandaluyong|marikina|pasay|caloocan|malabon|navotas|valenzuela|las piñas|parañaque|muntinlupa|pateros",
    "cordillera administrative region": "baguio",
    "ilocos region": "laoag|vigan|dagupan|urdaneta",
    "cagayan valley": "tuguegarao",
    "central luzon": "angeles|olongapo|mabalacat|malolos|cabanatuan",
    "calabarzon": "antipolo|bacoor|dasmarinas|cavite city|batangas city|lipa|calamba city|biñan|cabuyao|tagaytay|lucena|imus",
    "mimaropa": "puerto princesa|calapan",
    "bicol region": "legazpi",
    "western visayas": "iloilo city",
    "negros island region": "bacolod|dumaguete",
    "central visayas": "cebu city|mandaue|lapu-lapu|tagbilaran",
    "eastern visayas": "tacloban|ormoc",
    "zamboanga peninsula": "zamboanga city|pagadian|dipolog|dapitan",
    "northern mindanao": "cagayan de oro|iligan|gingoog|ozamiz|oroquieta|malaybalay",
    "davao region": "davao city|tagum|panabo|digos|mati",
    "soccsksargen": "general santos|koronadal|kidapawan",
    "caraga": "butuan|surigao city|tandag",
}
_REGIONS = {}
_CITIES = {}
for _island, _regions in _REGION_GROUPS.items():
    for _region, _aliases in _regions.items():
        for _alias in (_region, *_aliases):
            _REGIONS[_alias] = (_island, _region)
            _REGIONS[f"{_region} ({_alias})"] = (_island, _region)
            _REGIONS[f"{_alias} ({_region})"] = (_island, _region)
for _region, _names in _CITY_REGIONS.items():
    _island = _REGIONS[_region][0]
    for _name in _names.split("|"):
        _base = _name.removesuffix(" city")
        _canonical = _base + ("" if _name == "pateros" else " city")
        for _alias in (_name, _base + " city", "city of " + _base):
            _CITIES[_alias] = (_island, _region, _canonical)
        if _name not in {"manila city", "cebu city", "iloilo city", "davao city", "cavite city", "batangas city", "calamba city", "zamboanga city", "surigao city"}:
            _CITIES[_base] = (_island, _region, _canonical)
# Spelling variants only; no fuzzy matching.
for _alias, _target in {"las pinas": "las piñas", "paranaque": "parañaque", "binan": "biñan", "dasmariñas": "dasmarinas", "lapu lapu": "lapu-lapu"}.items():
    for _suffix in ("", " city"):
        _CITIES[_alias + _suffix] = _CITIES[_target]
_MISSING = {"", "n/a", "na", "none", "not stated", "not specified", "unspecified", "not provided",
            "not available", "unknown", "null", "nil", "no information", "no info", "not applicable", "-", "—"}
_BROAD = {"philippines", "ph", "phl", "remote", "work from home", "wfh", "hybrid", "onsite", "on-site"}
_COLUMNS = ["source_id", "original_location", "normalized_location", "island_group", "region", "locality", "location_status", "geographic_source", "geographic_reference_date"]


def _classify_location(value):
    normalized = normalize_text(value)
    if normalized in _MISSING:
        return normalized, "", "", "", "not stated"
    # Discard work-arrangement annotations, never an unrecognized place name.
    text = re.sub(r"\((?:remote|hybrid|onsite|on-site|work from home)\)", "", normalized).strip()
    parts = [part.strip() for part in re.split(r"[,;/|]", text) if part.strip()]
    places, regions = set(), set()
    for part in parts:
        if part in _BROAD:
            continue
        if part in _CITIES:
            places.add(_CITIES[part])
        elif part in _REGIONS:
            regions.add(_REGIONS[part])
        else:
            return normalized, "", "", "", "needs review"
    regions.update(place[:2] for place in places)
    if len(regions) > 1 or len(places) > 1:
        return normalized, "", "", "", "multiple or conflicting locations"
    if places:
        island, region, city = next(iter(places))
        return city, island, region, city, "locality identified"
    if regions:
        island, region = next(iter(regions))
        return normalized, island, region, "", "region identified; locality not resolved"
    return normalized, "", "", "", "broad or remote location"


def location_tables(jobs):
    """One auditable location row per ad; percentages include unresolved ads."""
    jobs = jobs.drop_duplicates("source_id") if "source_id" in jobs else jobs.copy()
    rows = []
    for index, job in jobs.iterrows():
        raw = job.get("location", "")
        original = "" if raw is None or pd.isna(raw) else str(raw)
        normalized, island, region, locality, status = _classify_location(original)
        rows.append([job.get("source_id", str(index)), original, normalized, island, region, locality, status,
                     PSGC_SOURCE if region else "", PSGC_REFERENCE_DATE if region else ""])
    evidence = pd.DataFrame(rows, columns=_COLUMNS)
    keys = ["island_group", "region", "locality", "location_status"]
    counts = evidence.groupby(keys, dropna=False).source_id.nunique().rename("job_ads").reset_index()
    counts["job_ads_pct"] = (100 * counts.job_ads / len(jobs)).round(1) if len(jobs) else 0.0
    return {"location_evidence": evidence, "location_hierarchy_counts": counts.sort_values(keys, kind="stable").reset_index(drop=True)}
