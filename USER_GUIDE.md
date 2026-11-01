# Step-by-step user guide

This guide covers the research workflow from job-ad upload through reporting. The app does not invent research labels. Researchers must review and save labels before model training is available.

Manual Review defaults to **Unique phrases**, showing each normalized phrase once. **Source ads** counts its advertisements within the current filters. Each row uses one representative advertisement for evidence and PSF-AAI decisions. Select **All advertisement occurrences** and search for a phrase to review its other contexts; turn off **Only show phrases awaiting category review** to include categorized phrases. Category saves still apply across the phrase's occurrences. PSF-AAI links apply only to the displayed advertisement. Grouping changes the review display, not research frequencies or exports; related but distinct phrases remain separate.

## 1. Start the app

Open PowerShell in the `future_of_work` project folder and run:

```powershell
..\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local address printed in the terminal. Keep that terminal running while you use the app.

Version 2.0.55 reuses unchanged data and prepared review queues during a session. The first shared-data load and first AI model load can still take longer. In Manual Review, source evidence follows the ten displayed occurrences; open **Sources and batch tools** only when needed. Other large tables use 100-row pages. **Reports and downloads** exports the complete selected results and prepares files only when you download them. Use **Team updates → Refresh shared review table** to fetch teammates' changes before starting a new batch; save your edits first.

Both AI draft columns stay visible on every review page. Choose **Generate missing AI drafts** for the displayed ten rows. It skips complete drafts and updates the table as batches finish, keeping your manual category and competency selections. When all rows have complete drafts, **Regenerate page drafts** explicitly replaces their suggestions. Drafts remain local to the host that generated them; they are not researcher-approved labels. BGE-M3 drafts appear before optional Ollama context checks, which do not alter manual decisions or PSF rankings.

Extraction, classifier training, and AI suggestions run in the background. A status panel shows progress on every workspace page; navigation and manual review remain available. One heavy job runs per app process, and the shared training lease still prevents competing model publications. **Stop processing** takes effect between processing steps; it is disabled once result publication starts. Save your edits before pressing **Refresh view** after completion.

From v2.0.57, opening **Extract skill phrases** does not download the saved extraction archive. Choose **Load saved results** to fetch it in the background, then **Refresh view** when ready. The same panel reports connection errors and lets you stop between loading steps. Loaded results remain available while you browse their 100-row pages; **Refresh saved results** fetches a newer snapshot. This changes loading only, not the saved research records or export scope.

From v2.0.66, compatible interface updates do not require extracting again. After **Load saved results**, open the Results pages normally. Results saved with v2.0.60–2.0.65 can also be reused when all research inputs still match. Changes to source data, the framework, labels, settings, selected model or extraction pipeline still require a new extraction. Loading never changes the original run's timestamp or research metadata.

From v2.0.58, the progress bar shows processing stages, advertisement/text counts, saving batches and elapsed time. Stage percentages are not a time estimate. Temporary Supabase connection resets and gateway failures are retried up to three attempts for reads and repeat-safe snapshot writes; the panel indicates retries. Authentication/permission failures and review-save operations are not automatically replayed. If the connection remains unavailable, the job reports failure instead of claiming completion. Existing extraction snapshots remain published until all replacement chunks are saved; keep the server and internet connection running until completion.

From v2.0.59, a connection or file-write failure after computation offers **Retry saving extraction**. It reuses the finished computation after rechecking study inputs, reviewed labels, cleaning metadata, settings and model identity. Changed inputs require a new extraction. The retry copy exists only in the current session: restarting the server, signing out, dismissing the job, or starting another job discards it. Failed result refreshes keep the last displayed table. Invalid server responses show an error rather than being interpreted as empty data.

Keep the local/Docker server running. Jobs are in memory: restarting the server interrupts them, and refreshing the entire browser can lose the progress panel. Completed AI batches stay saved; retry to continue local batches. A worker whose sign-in expires stops before its next authenticated operation; sign in again and retry. First model loading and inference still depend on your hardware. A new extraction can publish the smaller shared review index and source-partition metadata when needed; it is optional for reading a compatible saved run. Existing snapshots remain readable, and exports retain all selected research records and evidence.

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

These are minimum software checks, not a guarantee that the research sample is large or representative enough. With source IDs, the app holds out entire job ads and blocks training when every category cannot be represented on both sides. It compares TF-IDF + Multinomial Naive Bayes with TF-IDF + balanced Logistic Regression. The winner is chosen using training-only cross-validation (mean macro F1, mean weighted F1, then macro-F1 stability), before holdout scoring. If valid cross-validation is unavailable, review more distinct ads across every category; the run stops and preserves saved models instead of choosing by test scores. Automatic refreshes use the default 20% holdout and are for iterative development; they are not final research evaluation. Freeze a separate human-reviewed sample for final reporting.

## 8. Review model results

Open **Model Evaluation** to inspect eligible holdout metrics, per-class results, confusion matrices, grouped cross-validation and individual predictions. Holdout diagnostics are retained for both candidates, but do not select the winner. Earlier saved runs are marked as internal comparisons until retrained; their scores and models are not silently rewritten. Scores are withheld when the saved split shares job ads between training and test data or holds out fewer than two independent ads. Visit **Research readiness** for source coverage, reviewer-ID, phrase-quality and independent-review checks. These checks guide the team; they do not certify a study as publishable. Review errors and use an independently collected validation sample before making research claims.

## 9. Run the research analysis

After a reviewed classifier is available, rerun **Competency Extraction** to apply it to the selected jobs. Review results, then use:

- **Job Market Analysis** for employer demand and job breakdowns.
- **PSF Mapping** and **Employer–PSF Alignment** to review phrase-to-framework matches and configured thresholds.
- **Unmapped / Emerging Skills** to inspect unmapped phrases. “Emerging” is only a screening flag and needs longitudinal and researcher review.
- **Reports** to download the current research tables, workbook, HTML summary and metadata.

Use **Feedback** to record corrections and usability evaluations. Use **Settings** only when the research team has a documented reason to change thresholds or extraction controls; changing a setting requires rerunning the relevant analysis.

Count charts use whole-number tick intervals, including horizontal distributions, posting totals and heatmap count scales. Percentages and model scores retain decimals. Hover a bar to read its full label and count; the card stays visible while you move onto it inside the chart. Hover another bar to update it, or leave the chart to clear it. These interactions run locally in the browser.

## 10. Keep a clear research record

### Review multiple PSF-AAI links

Use the **PSF-AAI competencies** column in **Manual Labeling**, or on **PSF Mapping**, select a **Skill occurrence** (phrase plus advertisement). Read the source text and choose the applicable **PSF-AAI competencies**. Supply a distinct source-based rationale for each competency, confirm the review checkbox, and select **Save competency links**. Broad wording alone does not justify extra links. To reject all suggestions, clear the selection and explain why no mapping is supported.

Each save replaces only that occurrence's links. Other advertisements retain their decisions. Changed source text or framework references mark saved decisions stale and require another review. If another researcher saves the occurrence first, refresh before reviewing again. The competency-demand table counts unique advertisements even when several phrases from one ad map to that competency. Reports export both the occurrence mapping evidence and the selected review records.

**Shared deployment:** apply `supabase/migrations/20261018090000_occurrence_psf_mappings.sql` to the existing Supabase project before deploying this version. Fresh installations can use the updated `supabase_schema.sql`. The migration adds reviewer-accessible mapping decisions, version checks and an audit history; it does not change existing annotations or memberships. Local-only use stores current decisions in `data/processed/psf_mapping_reviews.csv` and requires no database migration.

Keep original source files and URLs, reviewer IDs, collection dates, framework review decisions and sampling rules. Distinguish candidate extractions from accepted labels. Do not report metrics from test fixtures, automated suggestions or any model trained on unreviewed data.


## Reading the job-market results

The Job market page starts with the selected-ad count and workflow. Use Skills for demand rankings, Roles and locations for title, family and location comparisons, Qualifications for stated/missing requirements and experience summaries, and PSF-AAI demand for reviewed reference links. Chart order defaults to descending demand and can switch to alphabetical lookup; Items per chart limits the picture only. Numbers count distinct advertisements, not repeated phrase mentions. A source ad can request multiple skills, so skill counts need not sum to the number of ads. “Not mentioned” placeholders, experience/year-only phrases, occupational labels, vague-only descriptors, unfinished list wording (such as “etc.” or “and others”), incomplete fragments such as “data” or “base” (lemmatized from “based”), exact “access to benefit(s)” wording, irrelevant labels and other non-skill text stay out of the skill charts. The chart-only audit retains their source evidence and exclusion reason; specific terms such as Python and SQL remain chartable when nearby wording is excluded. Legal boilerplate (“protected by applicable law”), generic duty wording (“activities and work”) and outcome/KPI wording (“adoption of insights”) are withheld from skill charts. Display variants of “datum” become “data”; Scrum and Agile Scrum method variants share one “agile scrum” label, while standalone “agile” remains separate. These chart rules do not edit saved labels or PSF-AAI decisions. Related phrases such as “ability to learn” and “learn and apply” are not automatically merged; review their source context before using a shared label.

The same eligible skill rows power every skill graph: overall rankings, competency-category charts, occupational-family heatmaps, selected-title and location views, and unmapped/emerging charts. Exact empty/unknown title placeholders are omitted from title graphs but remain in source evidence; clear requisition codes are removed from display labels. Regions and cities appear only when the exact location is resolved; broad, unknown or conflicting locations stay in the evidence and denominator, not as guessed places. Education levels, experience summaries and posting-date coverage use their own structured parsing rules. Official PSF-AAI labels and model-evaluation classes follow their reference and validation rules; they are not screened as job-ad skill phrases.

Roles and locations opens with the most common job-title ranking. The alphabetical title view is for lookup; the related-role grouping uses a source family or documented title rule. The skill heatmap shows the top 15 skills across selected occupational families. Color is the percentage of advertisements in that family; hover shows the exact count and family size. Ads without chartable skills remain in each family denominator. Choose an occupational family and title to see the top ten skills and their share of that selected group. Open **View all skills for this selection** for the searchable full table. Groups with fewer than ten ads are flagged as small and descriptive. These counts describe the selected postings, not the entire occupation or Philippine labor market.

Location charts show regional counts first. Choose a region to inspect its cities and municipalities. Exact-location counts may not cover ads with only a region, broad or remote locations, or unresolved text; those are reported separately. These are raw advertisement counts, not employment rates adjusted for population or labor force. Posting-month trends use chronological months and report missing dates and the observation range.

In PSF-AAI demand, the role ranking is separate from the role-by-competency heatmap. Heatmap counts use distinct advertisements; color is the share within each role, and hover shows the role denominator. One ad can map to several competencies and roles, so percentages can overlap and must not be added to estimate unique ads. Displayed links are existing researcher-reviewed decisions, not automatic confirmations.

Open Phrases needing clarification to inspect labels withheld from skill charts. Formatting duplicates are consolidated for display, but synonyms are not automatically merged. Original phrases, source IDs, saved labels and PSF-AAI decisions are retained. Correct ambiguous wording in Review and label phrases; a display screen is not a substitute for reviewing context. Category needs review identifies unresolved analytical categorization rather than a new skill type.

Missing requirements are reported as text, not zero years. Education uses a horizontal chart ordered from lower to higher credential level; unspecified values stay below it as a count and percentage. Not specified does not mean not required. Experience-year frequency tables use explicit source fields and retain original wording. A median and observed range appear only when at least two advertisements provide exact single-value year requirements; ranges and open-ended wording are excluded from these statistics, not forced to a number. Open **Requirement fields and parsing evidence** to inspect missing or ambiguous entries; description matches remain unverified candidates. Reports exports include chart_skill_demand, source-linked phrase and family audits, role-by-competency counts, requirement coverage and experience parsing evidence. Full original result tables remain available alongside chart summaries. Display preferences do not narrow the complete exported tables.


### Lowercase data and job-title grouping

Review data quality now previews lowercase cleaned values first. Expand Original source evidence to see the untouched source wording. Results apply the lowercase analysis view to existing uploads as well; normalized_jobs exports contain the cleaned values. Case-sensitive IDs, dates and link paths are preserved, as are official PSF-AAI source records. No source file or saved researcher annotation is overwritten by a display change.

In Roles and locations, Most common job titles consolidates clear seniority and branch/specialty variants when one recognized occupation is stated (for example, Junior Business Analyst - Banking Branch counts as business analyst). Clear leading requisition codes are omitted from analysis labels, while original titles remain in evidence. Source job families do not override this title-based chart. Composite or unrecognized titles stay distinct. Related role groups uses source-provided families; Specific titles (alphabetical) preserves normalized title wording for lookup. Inspect the common-title and role-group evidence tables to see each original title and grouping basis. Counts remain distinct advertisements; charts never merge job records.

Chart order and Items per chart also appear in PSF Mapping, Employer–PSF Alignment and Unmapped results. Specific titles are alphabetized only in their explicit lookup view; the common-title ranking follows the chosen demand order. The visual pipeline is available before results and in Methodology. The written report download follows Context, Approach and Results.


## Revision workflow and focused exploration (v2.0.77)

Open Complete processing workflow before reading the results. It documents collection, screening, confirmed duplicate removal, cleaning, extraction, classification, PSF mapping, aggregation, visualization and interpretation.

In Review data quality, open Screen advertisements and document exclusions to exclude out-of-scope or insufficient ads. Give a reason for every exclusion, confirm provenance and save. Original uploads remain archived. Duplicate candidates include identical title, employer, location and full description even when URLs or collection dates differ; inspect and confirm removals. Similar titles alone never remove an ad.

Results builds charts only for the selected section. In Roles and locations, choose an occupational family, then an alphabetically listed title. Island group, region and city selectors narrow that selection; Reset exploration filters restores All. Broad, remote, conflicting and unknown places stay identified separately. The offline location lookup is a curated PSA PSGC subset, verified 31 October 2026; unfamiliar addresses require researcher review. Source wording and the geographical source/date are exportable.

Qualifications shows unambiguous education levels from lowest to highest, with missing education reported separately. Alternative or multiple degrees remain in the evidence table. Experience bands contain only bounded numerical requirements wholly inside one band; minimum-only, spanning, month-only or descriptive wording remains reviewable. Original requirements are retained.

Skills use distinct-ad counts and explicit Power BI/Excel spelling aliases; Python, R and other distinct tools remain separate. PSF-AAI competencies default to the active framework row order. The role heatmap counts distinct ads per linked reference role and source family; select manageable role/family sets. One ad may support several roles, so cells are not additive. Heatmap roles describe competency reference links, not inferred equivalence between job titles.

### Repeatable local timing assessment

Run from the project folder:

```powershell
..\.venv\Scripts\python.exe scripts/benchmark_analysis.py --jobs data/processed/mapped_jobs.csv --taxonomy data/processed/cleaned_psf_aai.csv --sizes 20 100 250 500 --output-dir benchmark-results
```

The script retains all input rows, reports potential duplicates separately, measures copies and writes timing files only. It never publishes labels, changes the active dataset or trains a model. It reports text volume, stage times, candidate limits and skipped classifier inference. Initial runs include initialization; later samples reuse caches. Database transfer, sign-in and browser rendering need separate measurements on the school devices/network. Keep benchmark outputs local; do not interpret them as research model quality.


## Shared interface design (v2.0.78)

All workspace pages and sign-in states share the same theme, heading treatment, outlined cards, control styling and focus indicators. The reference design is adapted into one visible card layer per section. Workflow steps and metric cards use equal heights within their rows. Standard controls use44px minimum heights; shared spacing tokens govern gaps and card padding. Decorative local SVG artwork appears on wide page headers and is hidden on narrower screens. It does not represent research findings or cause a model or image download.

Interactive icons use Material Symbols. Primary actions use emerald; informational cues use blue, review cues amber, errors red and framework accents violet. Numbered workflow phases use a consistent phase palette. Chart highlights and alignment statuses use the same theme settings. These rules are recorded in AGENTS.md for future changes. Research tables, filters, saved labels and exported findings keep their existing behavior.
