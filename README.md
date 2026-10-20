# The Future of Work in the Philippines

A local Streamlit research application for analyzing skills required in Philippine AI and analytics job advertisements and their alignment with the Philippine Skills Framework for Analytics and Artificial Intelligence (PSF-AAI).

The app preserves the existing job ingestion, cleaning, NLP extraction, human labeling, TF-IDF classifiers, evaluation, and exports. The research pipeline maps employer skills to a researcher-reviewed PSF-AAI reference.

## Run locally

From this directory in PowerShell:

```powershell
..\.venv\Scripts\python.exe -m streamlit run app.py
```

For a new environment, create a virtual environment and install `requirements.txt`. Python 3.11+ is supported. Ordinary processing is local. To enable pretrained category and PSF-AAI suggestions on **Manual Labeling**, also install `requirements-suggestions.txt`; the model downloads on first use. Suggestions run locally.

The app uses [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3), pinned to a fixed model revision, to rank category descriptions and the active PSF-AAI taxonomy by multilingual semantic similarity. BGE-M3 is an embedding model, not a trained category classifier; its similarity scores are suggestions, not calibrated confidence or research metrics. The first suggestion run downloads roughly 2.3 GB of model files and runs locally on CPU. Install the optional runtime from this folder with `..\.venv\Scripts\python.exe -m pip install -r requirements-suggestions.txt` when using the shared parent environment.

## Shared team workspace with Supabase

The app can use Supabase Auth and a shared Postgres-backed workspace while continuing to keep local CSV backups. Copy `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` into `.streamlit/secrets.toml` for local use, or into the hosting provider's Streamlit secrets when deployed. Do not add secret keys or passwords to Git. The app uses each researcher's Auth session and Row Level Security; it does not need a Supabase secret/service-role key.

Git updates deliver code and the bundled PSF-AAI reference, not ignored job uploads, annotations, `.env` files, or local results. Existing clones must run `git pull origin main`; each teammate must also configure the shared Supabase secrets to see shared job data, or upload the job dataset on their device.

1. For a new Supabase project, apply `supabase/migrations/*.sql` once in filename order. The connected project already has these migrations.
2. Disable public sign-ups, create an Auth account for each teammate, and explicitly add their user ID to `research_members` with role `reviewer` (or `admin` for the coordinator).
3. Add the two app settings above, then restart Streamlit. Teammates sign in with their own accounts.
4. On the device holding the existing local dataset, open **Settings → Shared team workspace → Copy local workspace to shared database** once. This seeds only empty source-data slots; local labels and old model metrics are not automatically certified or promoted.
5. Deploy this repository to a host teammates can reach. The deployed app must receive the same two settings through its private secrets configuration. A local `127.0.0.1` address is reachable only from the computer running Streamlit.

Processed analysis tables and settings are shared as JSONB records. Candidate phrases and reviewed annotations use separate row-based tables; the database enforces one category per normalized phrase and records the authenticated editor. The app writes local CSV/JSON copies as recoverable backups. Re-export and retain backups in the research project folder. The `SUPABASE_JWKS_URL` value is not needed for this Auth flow.

Manual Labeling has a resumable **Run all local suggestions** action that prepares eligible posting CSVs already in `./train` and saves BGE-M3 drafts in batches. It does not crawl websites, create researcher labels, or train a classifier. Review and save each research label yourself.

Manual Labeling can also fetch one page (up to 20 jobs) from the free Himalayas public API. The importer keeps only listings whose location restrictions explicitly include the Philippines, stores their original listing URLs, and deduplicates by the provider's stable job ID. The provider can rate-limit API calls, so automated cycles make at most one request each. To run one bounded feed-and-suggest cycle from the project directory, use `..\\.venv\\Scripts\\python.exe scripts\\feed_and_suggest.py`. It creates source postings and editable BGE-M3 drafts only; researchers must review labels, and draft suggestions never train the research classifier. Credit Himalayas and link each original listing when displaying its data.

For exact phrases already present in the project's competency vocabulary, the displayed category draft uses that deterministic mapping instead of a potentially conflicting embedding result; the page identifies this source and leaves the category similarity score blank. Other category drafts and PSF-AAI matches use BGE-M3 similarity rankings, which are prompts for review rather than calibrated confidence or research metrics.

For the click-by-click workflow, see [USER_GUIDE.md](USER_GUIDE.md).

## Navigation

The app has a separate sign-in screen and 16 workspace pages: Overview; Upload job data; Review data quality; Extract skill phrases; Review and label phrases; Train classifier; Evaluate models; Job market; PSF mapping; Employer–PSF alignment; Unmapped and emerging skills; Reports and downloads; Research readiness; Methodology; Feedback and corrections; Settings. Data preparation and training are administrator responsibilities in shared mode.

## Research workflow

1. Upload Philippine job ads and review automatically suggested column mappings.
2. Review job source evidence for Philippine provenance and AI/analytics relevance, confirm the scope check, deduplicate and clean the records. Extraction remains blocked until this review is recorded. Original fields and source IDs remain available.
3. The bundled TESDA PSF-AAI reference loads by default on a fresh clone and includes source pages, official URL, source hash, competency profiles and Range of Application where available. A reviewed reference saved in the shared workspace takes priority. If the TESDA source edition changes, review the new PDF before replacing the bundled reference.
4. Extract phrases from job titles, descriptions, required/preferred skills and qualifications. Extraction shows source evidence and can run before a classifier exists.
5. On **Manual Labeling**, category and PSF-AAI fields start blank for new phrases in the review table. Researchers may generate AI drafts and explicitly check a row's Copy draft box if they want to use one. Unchecked rows use manual cell values; checking a box uses that draft for the field when saving. Only clicking **Save annotations** records the final choices under the reviewer ID and timestamp. AI drafts stay in `data/processed/pretrained_label_suggestions.csv` and never enter the training table automatically. Automatic retraining is off by default; manually train from **ML Training** after the dataset passes validation.
6. The ML Training page requires at least 30 distinct usable labels, two classes, five examples per class, complete source/reviewer provenance, no conflicting labels and a valid stratified split. These are workflow gates, not proof of adequate statistical validation. The explicit Train / Retrain action compares TF-IDF + Multinomial Naive Bayes with TF-IDF + balanced Logistic Regression; it never trains on refresh.
7. Review model performance and per-class errors, then explicitly rerun extraction to apply the saved classifier.
8. PSF mapping and employer alignment use the active reviewed reference. Review exact/alias/fuzzy evidence, source pages and heuristic scores. Configure thresholds in Settings; they are not official PSF standards.
9. Explore employer skill demand and PSF-AAI alignment, plus job-title/family trends and education/experience requirements. Requirement text matches remain source-linked candidates for researcher verification. Download CSV tables, the workbook, HTML summary and generated written report.

The research scope is Philippine AI- and analytics-related job advertisements compared with the TESDA PSF-AAI reference. This system does not analyze university curricula or claim that job-ad counts represent the entire Philippine labor market.

The pretrained model ranks human-defined categories and PSF-AAI competency descriptions; it does not validate extraction, prove a phrase is a competency, or establish PSF equivalence. Scores are semantic similarities, not calibrated confidence or research metrics. A PSF match does not establish equivalence. Researchers must review the original context and can ignore or explicitly copy each suggestion. The saved label is a researcher decision because only the manual field value submitted by the reviewer is saved.

## Alignment and demand definitions

The alignment unit is a distinct normalized employer phrase across the selected job-ad sample. Scores ≥0.80 are ALIGNED, ≥0.60 and <0.80 PARTIALLY ALIGNED, below 0.60 NOT MAPPED, and unavailable reference evidence is UNCLASSIFIED. These configurable thresholds are researcher heuristics, not official PSF requirements. “Not clearly mapped” does not mean PSF-AAI lacks the skill. Role and proficiency details describe the framework, not applicants.

Employer demand count is the number of distinct selected job ads containing a skill. Demand percentage divides this count by all selected job ads, including ads without detections. Alignment and partial alignment percentages use ALIGNED + PARTIALLY ALIGNED phrases as their denominator; unmapped percentage uses all assessed phrases. UNCLASSIFIED phrases are excluded from assessed rates. Counts and formulas are recorded in report metadata.

An emerging-skill candidate has NOT MAPPED status and appears in a configurable minimum number of distinct job ads (default 2). This is a screening flag only; researchers must review context, source quality and longitudinal evidence before claiming novelty.

## Official framework and provenance

The official source is [TESDA's PSF-AAI PDF](https://www.tesda.gov.ph/Uploads/File/Philippine%20Skills%20Framework/ICT/Philippine%20Skills%20Framework%20for%20Analytics%20and%20Artificial%20Intelligence.pdf). The included PDF is `data/reference/psf_aai_official.pdf`; its bundled, structured default is `data/reference/psf_aai_default.csv`. The app uses that reference when no active shared or local table exists. A reviewed reference in Supabase or `data/processed/cleaned_psf_aai.csv` overrides the bundled default. The reference is not job data: Git does not include uploaded ads, labels, results, or `.env` secrets. Teammates must pull the latest commit, configure their own `.env`/Streamlit secrets for the shared Supabase workspace, or upload the study job dataset on their own device.

## Training and model outputs

The authoritative label file is `train/labeled_competencies.csv`, with phrase, normalized_phrase, label, psf_competency, source_type, source_id, reviewer and timestamp. The app does not create example labels. Both fitted pipelines and the selected research classifier, metadata, model comparison, holdout predictions, metrics, per-class report and confusion matrix are written only after valid manual labels and explicit training. The app loads the selected research classifier from `models/competency_classifier.joblib`; the separate artifact under `models/provisional/` is an unevaluated weak-supervision experiment and is not used in the app or reportable research.

For teammates labeling on separate computers, each person downloads their reviewed CSV and sends it to the project coordinator. On the coordinator's copy, import the teammate-reviewed CSV from Manual Labeling; reviewer IDs and timestamps are preserved. Resolve any phrase conflicts in the table, then train the combined dataset once it passes validation. Do not combine these files by overwriting each other.

The supplied `train/postings.csv/postings.csv` has 123,849 records but only two with an explicit Philippine location. Their job titles do not establish AI/analytics relevance. Treat extracted phrases as candidates only, verify original sources and research scope, and collect a suitable Philippine AI/analytics sample before analysis.

Tests use synthetic fixtures only inside temporary test directories; their metrics are not research results. To run tests: `..\.venv\Scripts\python.exe -m pytest -q`.

## Limitations

Sample representativeness depends on source coverage and researcher selection. Parsing and text extraction can miss PDF/table structure; verify every framework definition and role link against the source before activation. Lexical matching may miss synonyms or overmatch context. Source-grouped classifier metrics apply only to the sampled postings and do not measure extraction or taxonomy-mapping accuracy. The Model Evaluation page withholds phrase-level leaked scores and scores based on fewer than two held-out ads; the **Research readiness** page reports dataset coverage and unresolved research checks. Independent validation and reviewer agreement are needed for publication. Local-only mode has no multi-user permissions. Supabase mode enforces team membership, database audit records and optimistic annotation conflicts. See [DEPLOYMENT.md](DEPLOYMENT.md) for the shared-site setup and remaining research checks.


### Optional Ollama context checks

BGE-M3 ranks categories and PSF matches. A local Ollama chat model can additionally check ambiguous category drafts. Install Ollama separately, download a suitable model, and set `FOW_OLLAMA_MODEL` in the environment or `.streamlit/secrets.toml` to its exact installed name before starting Streamlit. The integration calls only localhost port 11434; a hosted app cannot reach Ollama on your personal PC. Checks are cached in memory, have a 90-second response timeout (allows cold model startup), and retain BGE drafts on failure. Context notes are saved with drafts, never as human labels. The 0.65 similarity cutoff is a routing heuristic, not an accuracy threshold. No speed or accuracy improvement has yet been measured for this combination.
