"""Research category hierarchy. Stable leaf codes preserve existing annotations."""
CATEGORY_PATHS = {
    "AI / Machine Learning": "Competency > Technical / Digital > AI / Machine Learning",
    "Data / Analytics": "Competency > Technical / Digital > Data / Analytics",
    "Technical / Digital": "Competency > Technical / Digital > General programming and digital tools",
    "Business / Domain": "Competency > Domain knowledge > Business / Domain",
    "Soft / Enabling": "Competency > Enabling capabilities > Communication and personal effectiveness",
    "Leadership / Management": "Competency > Enabling capabilities > Leadership / Management",
    "Education / Qualification": "Credential requirement > Education / Qualification",
    "IRRELEVANT": "Excluded > IRRELEVANT",
}

def category_path(label):
    return CATEGORY_PATHS.get(label, "Legacy category (review needed) > " + str(label))

def requirement_type(label):
    if label == "Education / Qualification":
        return "Credential requirement"
    if label == "IRRELEVANT":
        return "Excluded"
    return "Competency" if label in CATEGORY_PATHS else "Unclassified"

def category_parent(label):
    if label in ("AI / Machine Learning", "Data / Analytics", "Technical / Digital"):
        return "Technical / Digital"
    if label in ("Soft / Enabling", "Leadership / Management"):
        return "Enabling capabilities"
    if label == "Business / Domain":
        return "Domain knowledge"
    return "Not applicable"

def skill_type(label):
    parent = category_parent(label)
    return {"Technical / Digital": "Technical", "Enabling capabilities": "Soft / Enabling"}.get(parent, requirement_type(label) if requirement_type(label) != "Competency" else "Domain knowledge")
