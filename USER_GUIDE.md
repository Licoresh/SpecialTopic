# Step-by-step user guide

This guide covers the research workflow from job-ad upload through reporting. The app does not invent research labels. Researchers must review and save labels before model training is available.

## 1. Start the app

Open PowerShell in the `future_of_work` project folder and run:

```powershell
..\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local address printed in the terminal. Keep that terminal running while you use the app.

## 2. Prepare a suitable Philippine job-ad sample

Use **Job Data Upload** to upload a CSV or XLSX file. Retain original posting URLs, locations, job titles and source identifiers. Review the automatically suggested column mappings and click **Save mapping**.

The supplied `train/postings.csv/postings.csv` has 123,849 rows, but only two explicitly identify a Philippine location; the two titles are *Experienced Virtual Executive Assistant* and *Social Media Manager*. A Philippine location alone does not establish AI/analytics relevance. Do not treat this file as a representative study sample; screen each source and collect more in-scope Philippine ads.

## 3. Review and clean the jobs

Open **Data Quality**, choose **jobs**, inspect the mapped rows and quality report, and select only confirmed duplicate record IDs for removal. Check the source evidence and tick the confirmation that the ads have Philippine provenance and relate to AI or analytics. Click **Save cleaned dataset**.

If the ads do not meet the study scope, do not confirm them for research analysis.

## 4. Review the PSF-AAI reference

Open **PSF-AAI Framework**. The official TESDA PDF is stored in `data/reference/psf_aai_official.pdf`. Click **Extract framework draft from stored PDF** if a draft is not already present.

Check competency names, descriptions, codes, role links, levels and cited PDF pages against the official source. Enter the framework reviewer ID, tick the source-review confirmation, then click **Activate reviewed PSF-AAI reference**. The extracted draft is not considered verified until a researcher activates it.

## 5. Extract competency candidates

Open **Competency Extraction** and click **Run extraction and classification**. Review the extracted phrases and their job-ad context. The default 300-phrase cap controls broad n-gram candidates per ad; exact vocabulary and PSF-AAI term scans still inspect the full text. Keep the default for a manageable review queue. Raise it in Settings only for a targeted wider review, because the extra candidates may include generic fragments. Extraction can run before a classifier has been trained; any candidate or prediction still needs human review.

## 6. Manually label candidates

Open **Manual Labeling**. Signed-in workspaces automatically use your account for reviewer attribution; no Reviewer ID entry is needed in Manual Labeling or PSF Mapping. Only offline work without an account uses **Reviewer details**. Category and PSF-AAI competencies are edited in the **same table**, with ten occurrence rows per page.

Use **Full-screen review** above the table to expand the complete workspace. **Save annotations** and **Generate AI suggestions for this page** stay in its action bar; source evidence and rationale fields remain available below. Turn the switch off to return without discarding edits. Search with **Find candidate phrase**, or open **Filters** to change the visible phrases. Scroll the table horizontally for the remaining columns; the Phrase column stays pinned.

**Review guide** holds the category rules; **Review settings** holds the automatic-training option. Shared workspaces provide **Team updates** for explicitly refreshing the review snapshot. **Source evidence**, **AI details**, and **How to use AI drafts** open alongside the table. Less frequent preparation actions are under **Sources and batch tools** below the review workspace. Offline file merging is under **Import team annotations**.

1. Find the phrase and check its **Source advertisement**. The same phrase can appear on separate rows for different advertisements.
2. Choose its **Category**. Category decisions apply across occurrences of the normalized phrase.
3. Open the **PSF-AAI competencies** cell beside Category and select one or more options. Select another option to add it, or remove a selected tag. These links apply only to this row's advertisement.
4. For changed links, complete the **Evidence** section below the table: read the source context, provide a distinct rationale for each competency, and confirm the context check.
5. Click **Save annotations** to submit the table and mapping evidence. Required evidence is validated before category writes. Category and mapping storage use separate transactions; if a storage error interrupts the batch, the app reports which parts saved. Refresh before retrying a partial save.

Uncheck **Only show phrases awaiting category review** to revisit categorized phrases or add further PSF-AAI links. Existing occurrence mappings reload as multiple selected values. To update evidence for unchanged selections, check **Update or confirm this occurrence's mapping**. To remove existing links, clear the cell and explain why no mapping is justified. An untouched blank cell makes no mapping decision. Category-only saves preserve existing source-specific legacy PSF references.

The competency options use the active reviewed PSF-AAI reference; names and definitions are unchanged. New selections remain blank until explicitly chosen.

Candidates awaiting extraction can be reviewed if source text is present. Their links enter research analysis only after the matching occurrence is extracted and accepted. If extraction changes the evidence, review the stale links again. Missing source text blocks competency review.

Optional AI drafts remain separate. Use **Generate next 25 local drafts** to prepare a saved batch, or **Generate AI suggestions for this page** for the displayed phrases. Review **AI category draft** and **AI PSF-AAI drafts** beside your manual fields in the same table. New BGE-M3 drafts retain up to three distinct ranked framework candidates per source occurrence, with each similarity score stored separately. These are alternatives to evaluate, not an instruction to choose every candidate. Read **Context check** and **Context note** in the same table. Double-click a context-note cell to read its complete text. These AI columns are read-only. Older single-candidate drafts remain readable; click **Generate AI suggestions for this page** to regenerate them in the new format. The batch resume tool still skips already-suggested rows. Select your own values explicitly. Similarity scores rank candidates; they are not confidence, accuracy, or F1. First use of the optional models downloads about 2.3 GB and runs on CPU; install `requirements-suggestions.txt` if needed.

The review queue hides obvious connector fragments such as **“with strong”** and **“written and”** by default. Turn off **Hide obvious connector fragments** to inspect them, edit them into a meaningful phrase, or mark them **IRRELEVANT**. The app does not assign a label to hidden phrases.

Enter your researcher ID, then click **Save annotations**. The app saves only the values in the manual fields, with the source ID, reviewer ID and timestamp. Generating a suggestion does not save a reviewed decision; values count as researcher-reviewed only after you explicitly submit them. AI drafts remain in their separate file and never enter training by themselves. **Automatically retrain after saving reviewed labels** is off by default. To train manually, open **ML Training** after saving labels and click **Train / Retrain Models** when the dataset passes validation. You can opt into automatic development retraining, but it will only run when every validation check passes.

If the same normalized phrase has conflicting categories, Manual Labeling shows a conflict-resolution table for every conflict in the saved dataset, even when a phrase is not on the current page. Each row shows the phrase, its existing categories, and one category choice. Click **Save annotations** to apply those choices to every saved occurrence. The app refuses to save while any conflict remains, and you can resolve existing conflicts without adding new labels.

### Teammates working on separate computers

Each teammate runs their own copy of the project and uses a unique **Reviewer ID** while labeling. At the end of their work, they click **Download reviewed training data** and send that CSV to the designated project coordinator. The coordinator imports each file using **Import teammate-reviewed CSV/XLSX** on Manual Labeling. Files must include source type, source ID, reviewer ID and timestamp; the merge preserves each teammate's reviewer ID and timestamp. Resolve any conflicts shown in the table, then manually train from **ML Training** with **Train / Retrain Models** when the combined dataset passes validation. Avoid replacing the coordinator's CSV with a teammate's file, because that would discard other annotations.

## 7. Train only when the dataset passes validation

Open **ML Training**. The page reports the usable phrase count, class counts and validation errors. Training becomes available only when the data has at least 30 distinct usable phrases, at least two categories, at least five phrases per category, complete provenance, no conflicting labels and a valid stratified split.

These are minimum software checks, not a guarantee that the research sample is large or representative enough. With source IDs, the app holds out entire job ads and blocks training when every category cannot be represented on both sides. It compares TF-IDF + Multinomial Naive Bayes with TF-IDF + balanced Logistic Regression. Automatic refreshes use the default 20% holdout and are for iterative development; they are not final research evaluation. Freeze a separate human-reviewed sample for final reporting.

## 8. Review model results

Open **Model Evaluation** to inspect eligible holdout metrics, per-class results, confusion matrices, grouped cross-validation and individual predictions. Scores are withheld when the saved split shares job ads between training and test data or holds out fewer than two independent ads. Visit **Research readiness** for source coverage, reviewer-ID, phrase-quality and independent-review checks. These checks guide the team; they do not certify a study as publishable. Review errors and use an independently collected validation sample before making research claims.

## 9. Run the research analysis

After a reviewed classifier is available, rerun **Competency Extraction** to apply it to the selected jobs. Review results, then use:

- **Job Market Analysis** for employer demand and job breakdowns.
- **PSF Mapping** and **Employer–PSF Alignment** to review phrase-to-framework matches and configured thresholds.
- **Unmapped / Emerging Skills** to inspect unmapped phrases. “Emerging” is only a screening flag and needs longitudinal and researcher review.
- **Reports** to download the current research tables, workbook, HTML summary and metadata.

Use **Feedback** to record corrections and usability evaluations. Use **Settings** only when the research team has a documented reason to change thresholds or extraction controls; changing a setting requires rerunning the relevant analysis.

## 10. Keep a clear research record

### Review multiple PSF-AAI links

Use the **PSF-AAI competencies** column in **Manual Labeling**, or on **PSF Mapping**, select a **Skill occurrence** (phrase plus advertisement). Read the source text and choose the applicable **PSF-AAI competencies**. Supply a distinct source-based rationale for each competency, confirm the review checkbox, and select **Save competency links**. Broad wording alone does not justify extra links. To reject all suggestions, clear the selection and explain why no mapping is supported.

Each save replaces only that occurrence's links. Other advertisements retain their decisions. Changed source text or framework references mark saved decisions stale and require another review. If another researcher saves the occurrence first, refresh before reviewing again. The competency-demand table counts unique advertisements even when several phrases from one ad map to that competency. Reports export both the occurrence mapping evidence and the selected review records.

**Shared deployment:** apply `supabase/migrations/20261018090000_occurrence_psf_mappings.sql` to the existing Supabase project before deploying this version. Fresh installations can use the updated `supabase_schema.sql`. The migration adds reviewer-accessible mapping decisions, version checks and an audit history; it does not change existing annotations or memberships. Local-only use stores current decisions in `data/processed/psf_mapping_reviews.csv` and requires no database migration.

Keep original source files and URLs, reviewer IDs, collection dates, framework review decisions and sampling rules. Distinguish candidate extractions from accepted labels. Do not report metrics from test fixtures, automated suggestions or any model trained on unreviewed data.
