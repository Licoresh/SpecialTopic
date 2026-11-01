"""Synthetic geographic lookup checks; no live research data."""
import pandas as pd
from src.geography import location_tables


def locations(*values):
    return location_tables(pd.DataFrame({"source_id": [str(i) for i in range(len(values))], "location": list(values)}))


def test_exact_aliases_current_regions_and_original_evidence():
    result = locations("CEBU CITY, Philippines", "City of Cebu", "Iligan", "Cagayan de Oro City", "Bacolod City", "Makati, NCR", "Las Pinas")
    evidence = result["location_evidence"]
    assert evidence.locality.tolist() == ["cebu city", "cebu city", "iligan city", "cagayan de oro city", "bacolod city", "makati city", "las piñas city"]
    assert evidence.iloc[4].region == "negros island region"
    assert evidence.iloc[0].original_location == "CEBU CITY, Philippines"
    assert evidence.iloc[0].geographic_source.startswith("https://psa.gov.ph/")
    assert evidence.iloc[0].geographic_reference_date == "2026-10-31"


def test_broad_ambiguous_unknown_and_missing_are_not_guessed():
    evidence = locations("Manila", "Cebu", "Metro Manila", "Davao", "Naga City", "Remote, Philippines", "Atlantis", "", None,
                         "Unknown", "Not available", "-")["location_evidence"]
    assert evidence.locality.eq("").all()
    assert evidence.iloc[0].region == "national capital region"
    assert evidence.iloc[1].region == "central visayas"
    assert evidence.iloc[3].location_status == "needs review"
    assert evidence.iloc[4].location_status == "needs review"  # Naga has multiple city names.
    assert evidence.iloc[5].location_status == "broad or remote location"
    assert evidence.iloc[7:12].location_status.eq("not stated").all()


def test_conflicting_multiple_and_unknown_address_parts_require_review():
    evidence = locations("Cebu City, NCR", "Makati / Pasig", "Cebu City, Atlantis", "Davao City; Cebu City", "Cebu City (Hybrid)")["location_evidence"]
    assert evidence.iloc[:4].locality.eq("").all()
    assert evidence.iloc[0].region == ""
    assert evidence.iloc[1].location_status == "multiple or conflicting locations"
    assert evidence.iloc[4].locality == "cebu city"


def test_unique_ad_counts_missing_in_denominator_and_no_mutation():
    jobs = pd.DataFrame({"source_id": ["a", "a", "b", "c"], "location": ["Cebu City", "Cebu City", "City of Cebu", ""]})
    original = jobs.copy(deep=True)
    result = location_tables(jobs)
    cebu = result["location_hierarchy_counts"].query("locality == 'cebu city'").iloc[0]
    assert cebu.job_ads == 2 and cebu.job_ads_pct == 66.7
    assert len(result["location_evidence"]) == 3
    pd.testing.assert_frame_equal(jobs, original)
    assert location_tables(pd.DataFrame())["location_hierarchy_counts"].empty
