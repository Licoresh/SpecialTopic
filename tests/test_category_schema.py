from src.category_schema import category_parent, requirement_type, skill_type, category_path


def test_technical_leaves_share_parent():
    for label in ("AI / Machine Learning", "Data / Analytics", "Technical / Digital"):
        assert category_parent(label) == "Technical / Digital"
        assert requirement_type(label) == "Competency"
        assert skill_type(label) == "Technical"


def test_credentials_and_unknown_labels_are_not_technical_skills():
    assert requirement_type("Education / Qualification") == "Credential requirement"
    assert category_parent("Education / Qualification") == "Not applicable"
    assert skill_type("Education / Qualification") == "Credential requirement"
    assert requirement_type("custom old label") == "Unclassified"
    assert "review needed" in category_path("custom old label")
