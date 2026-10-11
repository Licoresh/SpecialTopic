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

Open **Manual Labeling**. Choose a candidate source, keep **Only show phrases awaiting review** selected, and inspect the evidence and original posting link. Candidate phrases appear in an editable table, 10 per page. New category and PSF-AAI fields start blank. To enable optional pretrained suggestions, install `requirements-suggestions.txt` once from the project folder; the pinned model downloads on first use.

To generate drafts for the local corpus in one run, click **Run all local suggestions** at the top of Manual Labeling. The app scans CSVs already in `./train`, prepares candidates from raw posting CSVs using the explicit-Philippines location rule, and creates BGE-M3 drafts in small saved batches. It skips phrases already reviewed or already suggested. If interrupted, click the button again to resume from saved drafts. The app does not crawl the web or collect new job ads. Keep the app and computer running until the progress bar completes. On first use, BGE-M3 downloads about 2.3 GB and runs locally on CPU.

For each phrase, read the original context and choose a category yourself in the table. Choose **IRRELEVANT** when it is not an in-scope competency. You may leave the PSF-AAI field blank when no exact competency is justified. If AI drafts are available, review the read-only draft columns. Check **Copy category draft** or **Copy PSF-AAI draft** only when you want that suggestion used instead of the manual field for that row. Similarity scores only rank candidate matches and are not calibrated confidence, accuracy, or F1.

The review queue hides obvious connector fragments such as **“with strong”** and **“written and”** by default. Turn off **Hide obvious connector fragments** to inspect them, edit them into a meaningful phrase, or mark them **IRRELEVANT**. The app does not assign a label to hidden phrases.

Enter your researcher ID, then click **Save annotations**. The app saves only the values in the manual fields, with the source ID, reviewer ID and timestamp. Generating or copying a suggestion does not save it; copied values count as researcher-reviewed only after you explicitly submit them. AI drafts remain in their separate file and never enter training by themselves. **Automatically retrain after saving reviewed labels** is off by default. To train manually, open **ML Training** after saving labels and click **Train / Retrain Models** when the dataset passes validation. You can opt into automatic development retraining, but it will only run when every validation check passes.

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

Keep original source files and URLs, reviewer IDs, collection dates, framework review decisions and sampling rules. Distinguish candidate extractions from accepted labels. Do not report metrics from test fixtures, automated suggestions or any model trained on unreviewed data.
