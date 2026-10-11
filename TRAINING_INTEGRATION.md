# Research data and model workflow

The production workflow is restricted to researcher-reviewed skills from Philippine job advertisements and the researcher-verified PSF-AAI reference. Do not use synthetic fixtures for research conclusions.

## Current data

`train/postings.csv/postings.csv` contains 123,849 posting records and has no competency labels. Its conservative country screen retained two records explicitly located in the Philippines and produced 602 phrase candidates. The two source records require researcher review for Philippine provenance, AI/analytics relevance and extraction context. The source corpus is mostly outside the Philippine scope and did not enter the analysis dataset.

The original starter pack under `train/raw` contains 25 job-ad summaries and 368 candidate occurrences (253 distinct phrases), with blank labels. They remain source evidence; review the original postings before treating the summaries as research evidence. The editable authoritative label table is `train/labeled_competencies.csv`, with eight required headers and no pre-filled labels.

The official PSF-AAI PDF is saved under `data/reference`. The parser extracted 94 competency-definition blocks (78 FSC and 16 ESC) with official competency codes, definition text, PDF page, URL and file SHA-256. It also created 1,029 literal role-to-competency references across 28 roles. These files remain a draft until researchers verify them against their cited PDF pages and activate the reviewed reference in the app. Aliases and keywords remain empty because the parser does not infer synonyms. The PDF has 315 viewer pages; source-page values use 1-based PDF viewer numbering. The visible printed page can differ by the front-matter offset.

The current annotation file contains 649 saved rows (638 distinct normalized phrases), but that count is not a measure of research readiness. As audited on 2026-10-10, only four distinct source IDs are represented; two postings contribute 597 rows (92%). About 30% of saved phrases start or end with a common connector, and three near-duplicate reviewer ID spellings need reconciliation. The saved data pass the app's basic label checks and have no current category conflicts, but reviewer IDs and timestamps alone do not establish that labels were independently reviewed. The existing saved model scores came from a phrase-level random split: three source IDs overlap between training and holdout, so the Model Evaluation page now withholds those scores. The Research Readiness page reports these issues. No result from this sample should be presented as a validated estimate of classifier accuracy.

## Human review and training

Use **Manual Labeling** to review job-ad phrases, edit phrase extraction, assign a category, optionally select an exact competency from the active PSF-AAI reference, or mark IRRELEVANT. Install `requirements-suggestions.txt` to enable the optional local pretrained category suggestions. A researcher must review and confirm copied suggestions before saving with their reviewer ID. The authoritative table stores source type, source ID, reviewer and UTC timestamp. Only job-ad rows pass final-training provenance validation.

The **ML Training** action remains disabled until there are at least 30 distinct usable phrases, two classes, five examples per class, complete provenance, no conflicting labels and a feasible source-disjoint holdout. The gate is an operational minimum, not evidence that the sample is statistically sufficient. Training compares Multinomial Naive Bayes and balanced Logistic Regression with TF-IDF, holding out entire job-ad sources and using grouped cross-validation where each fold can represent all categories. It fails closed if a source-disjoint holdout cannot retain every category in both partitions. This test sample currently passes that mechanical split check only narrowly; four source IDs are not sufficient coverage for a broad claim. A refresh never starts training. Review the Research Readiness page before interpreting any score.

## Alignment and exports

The analysis unit is a distinct normalized employer phrase in the selected job ads. Exact or alias matches can be ALIGNED. Similarity at or above the configurable partial threshold is PARTIALLY ALIGNED; lower scores are NOT MAPPED; an unavailable active reference yields UNCLASSIFIED. Defaults are heuristic settings, not official PSF criteria. The UI shows source pages, source URL and source hash. A reference proficiency level describes the framework and is not evidence of an applicant's attainment.

Employer demand count is the number of unique ads with the skill. Demand percentage uses all selected job ads as the denominator. Aligned/partially aligned rates use only mapped phrases; unmapped rate uses assessed phrases; unclassified phrases are excluded. Emerging-skill candidates are recurring NOT MAPPED phrases and need human and longitudinal review. “Not clearly mapped” never means that PSF-AAI lacks a skill.

Exports include cleaned jobs, skill candidates, manually reviewed labels, verified PSF-AAI, classifier predictions, occurrence-level PSF mapping, employer–PSF alignment, employer demand, unmapped/emerging candidates, model evaluation and an Excel research workbook. Metadata records filters, settings, counts and rate denominators.

Tests use synthetic fixtures only in temporary test workspaces. They test software behavior; their model metrics are never research results. See `METHODOLOGY.md` for definitions, sample limits and validation requirements.
