import pandas as pd

def filter_frame(frame, filters):
    mask = pd.Series(True, index=frame.index)
    for field, values in filters.items():
        if field == "normalized_phrase_contains":
            query = str(values or "").strip()
            if query and "normalized_phrase" in frame:
                mask &= frame.normalized_phrase.astype(str).str.contains(query, case=False, regex=False, na=False)
            continue
        if field in frame and values:
            mask &= frame[field].astype(str).isin([str(v) for v in values])
    return frame.loc[mask]

def accepted_skills(frame):
    if frame.empty:
        return frame
    return frame[frame.accepted.astype(str).str.casefold().eq("true") & frame.competency_category.ne("IRRELEVANT")].drop_duplicates(["source_type", "source_id", "normalized_phrase"])

def counts(frame, column, name="count"):
    if column not in frame or frame.empty:
        return pd.DataFrame(columns=[column, name])
    return frame[column].replace("", pd.NA).dropna().value_counts().rename_axis(column).reset_index(name=name)

def demand_matrix(skills, jobs, group):
    if skills.empty or jobs.empty or group not in jobs:
        return pd.DataFrame()
    joined = skills.merge(jobs[["source_id", group]], on="source_id")
    joined = joined[joined[group].ne("")]
    return joined.groupby(["normalized_phrase", group]).source_id.nunique().unstack(fill_value=0)
