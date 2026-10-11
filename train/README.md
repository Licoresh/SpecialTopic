# Research data folder

This folder contains Philippine job-ad sources and researcher-reviewed training labels for the Future of Work in the Philippines study.

## Files

- `labeled_competencies.csv` is the one authoritative editable training table. It starts with the eight required headers and no labels. The app saves reviewed annotations here.
- `raw/philjobnet_ai_data_analytics_jobs_starter.csv` and `raw/candidate_phrases_for_manual_labeling.csv` are a small starter source pack. Verify original URLs and review every phrase; these are not final research observations.
- `postings.csv/postings.csv` is a large supplied posting file. The current import found only two records with an explicit Philippine location. They still need review for AI/analytics relevance and source quality.
- `derived/` contains an import report and blank-label candidate extraction. These are review material, not training labels.
- `docs/` contains source notes and the manual-labeling guide.

The application uses only researcher-reviewed rows with complete source and reviewer provenance for research training. Candidate files and automated suggestions are never treated as labels. Pretrained category and PSF-AAI drafts are stored separately in `data/processed/pretrained_label_suggestions.csv`; review or edit them on Manual Labeling before saving human annotations.

Follow the click-by-click workflow in the project-level [USER_GUIDE.md](../USER_GUIDE.md).
