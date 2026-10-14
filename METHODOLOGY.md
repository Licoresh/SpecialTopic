# Methodology: Philippine employer skills and PSF-AAI

## Research question and scope

To what extent do skills and competencies required in Philippine AI- and analytics-related job advertisements align with the Philippine Skills Framework for Analytics and Artificial Intelligence (PSF-AAI)? The analysis covers Philippine job ads and a researcher-verified PSF-AAI reference.

## Data and units

The primary observational unit is a unique job advertisement identified by its source record ID. Researcher screening must establish Philippine provenance and AI/analytics relevance; a Philippine location alone is insufficient. The app records an explicit scope review before extraction from uploaded job data. Keep source URL, collection details and raw file hash. Confirm duplicates before cleaning, and report source coverage and sampling dates. The skill-demand unit is a distinct job ad mentioning a normalized skill phrase; repeated mentions in one ad count once.

The PSF-AAI reference stores competency name and description, functional/enabling category, official competency codes, framework career-role links and listed levels, source PDF page and URL, source hash, reviewer, review status and timestamp. PDF extraction produces a reviewable draft. It is not an authoritative active taxonomy until a researcher checks definitions, codes, roles and levels against their cited pages. Aliases and keywords are not inferred from prose.

This study does not collect or compare university curricula. Its comparison is employer-stated job-ad skills against the researcher-verified TESDA PSF-AAI reference.

## Job text preparation and phrase discovery

Map source columns to the app's job schema; preserve raw bytes and source fields. Cleaning normalizes HTML, Unicode and whitespace while retaining technical terms such as C++, C#, .NET, R, SQL and Power BI. Empty fields stay empty. A reviewer confirms duplicate removals.

The existing NLP pipeline combines exact framework terms and researcher-supplied aliases/keywords with general discovery vocabulary and spaCy lookup lemmatization over candidate n-grams. Every candidate retains its original phrase, normalized phrase, job ID and source context. Candidate limits are recorded. General vocabulary and model predictions are discovery evidence, not human labels or PSF matches. Researchers inspect context, edit phrases and may label a candidate IRRELEVANT.

## Manual labels and supervised classification

### Analytical category hierarchy

Each normalized phrase receives one researcher-reviewed leaf category. These are study-defined analytical categories, distinct from the official PSF-AAI reference categories. Technical / Digital is the parent of AI / Machine Learning, Data / Analytics, and general programming and digital tools. Enabling capabilities contains communication and personal effectiveness (stored as Soft / Enabling) and Leadership / Management. Business / Domain represents domain knowledge. Education / Qualification is a credential requirement, not a competency. IRRELEVANT identifies excluded material. The legacy stored value Technical / Digital denotes the general programming and digital-tools leaf; the interface displays its full hierarchy.

Researchers select the most specific applicable leaf using source context and the decision rules in CATEGORY_CODEBOOK.md. Parent categories and requirement types are derived from the leaf. Parent and child totals must not be added together; job-level parent counts require deduplication within the parent. Credentials should be reported separately from competency frequencies. Existing labels are not automatically re-reviewed by changing the codebook.

### AI-assisted drafts and context checks

The pinned BAAI/bge-m3 embedding model (revision 5617a9f61b028005a4858fdac845db406aefb181) ranks the study's category descriptions and competencies in the active PSF-AAI taxonomy using a phrase and nearby source context. Exact project-vocabulary rules take priority for known phrases. Blank and symbol-only phrases are excluded from review display and cannot receive competency suggestions. BGE-M3 similarities are rankings, not calibrated probabilities or accuracy measures.

An optional local Ollama chat model checks ambiguous category drafts. The current local configuration uses qwen2.5:1.5b. It is invoked for BGE-based category drafts with similarity below 0.65 or an incomplete-phrase flag; exact vocabulary rules skip this step. The threshold is an operational routing heuristic, not an empirically established correctness threshold. Ollama judges whether the phrase and its context support the proposed category. It does not change the PSF-AAI taxonomy, mapping algorithm, or saved researcher labels.

The review table records a context-check status and explanatory note. Supported means AI-supported, not researcher-verified. Needs researcher review flags uncertain or unsupported wording. Not requested, Disabled, Not checked, and Unavailable distinguish skipped, unconfigured, older, and failed checks. An unavailable checker retains the BGE draft without claiming verification. Draft records retain the BGE model/revision, similarity evidence, context-model name, check result, reason, source identity, and generation timestamp. The Ollama model name is recorded, but its artifact digest is not currently captured; archive the installed model details separately for reproducibility.

Candidate embeddings are reused for category and PSF ranking. Context checks are cached in memory; bounded batches retain completed drafts. These are operational performance measures, not evidence of improved research accuracy. Neither BGE-M3 nor the Ollama model is fine-tuned when researchers save annotations. The combined workflow requires evaluation against independently reviewed examples before claims of improved classification quality.

### Researcher review and training observations

Manual category and PSF-AAI fields begin blank for new phrases. AI drafts are read-only guidance alongside the manual fields. Researchers select values in the manual columns and explicitly save; no Copy controls or automatic draft-to-label transfer are provided. Saved annotations record the reviewer and timestamp, but the app cannot establish that a reviewer actually checked the evidence or that the decision is correct. PSF assignment is optional and remains a separate field.

Only reviewed Philippine job-ad phrases passing provenance and conflict validation qualify for research training. A normalized phrase has one category across occurrences; researchers must resolve disagreements and refine ambiguous phrases using source context. AI drafts alone and synthetic software fixtures do not qualify as research training observations.

The explicit training action compares TF-IDF pipelines with Multinomial Naive Bayes and balanced Logistic Regression. Training prefers `normalized_phrase`, falling back to `phrase`. When source IDs are present, the holdout and cross-validation split by job-ad source ID so wording from one ad cannot appear in both training and evaluation. Training is blocked if a source-disjoint holdout cannot retain every category in both partitions. If source IDs are unavailable in a non-production software fixture, the fallback phrase-level split is explicitly identified and must not be treated as research evaluation. Model selection prioritizes macro F1, then weighted F1, per-class performance and CV stability. Artifacts include fitted pipelines and data/configuration hashes. A grouped holdout is only an internal estimate for the sampled postings; it does not validate extraction, PSF mapping, label quality, representativeness, or performance on a separately collected sample.

Operational gates require at least 30 distinct usable phrases, two classes, five phrases per class, no conflicting phrase labels, complete provenance and a feasible source-disjoint split. These are safeguards, not a claim of statistical adequacy. The Research Readiness page additionally flags source concentration, reviewer-ID variants, short phrase fragments and phrase-level evaluation leakage. It cannot establish annotation quality or a representative sampling frame. Researchers should seek independent labels, adjudicate disagreement, document inter-rater agreement, and evaluate on a genuinely independent sample. A separate `models/provisional/` artifact is reserved for weak-supervision experiments and is never used by the production classifier or reported as a research model.

## Employer-to-PSF mapping and alignment

Map each distinct employer phrase to the active PSF-AAI reference using exact names, researcher-provided aliases/keywords, optional local semantic evidence or fuzzy similarity. Mapping records include the employer phrase and normalized form, target competency, career role, reference category and listed level, source page/URL/hash, match method, similarity and confidence fields. Similarity is a heuristic, not a calibrated correctness probability. A listed reference level does not imply applicant proficiency.

Default thresholds are configurable: score ≥0.80 ALIGNED; ≥0.60 and <0.80 PARTIALLY ALIGNED; <0.60 NOT MAPPED. Without a verified reference, status is UNCLASSIFIED. These thresholds are analysis settings, not PSF standards. “Not clearly mapped to PSF-AAI” describes the selected taxonomy and method; it does not establish that the framework lacks the skill. Researchers should inspect context and adjudicate consequential mapping decisions.

## Demand and rates

For skill *s*, employer demand count is the number of distinct selected job ads containing *s*. Demand percentage is that count divided by all selected job ads, including those with no skill detections, multiplied by 100. The UI supports demand summaries by job title, location, category, PSF job role and posting date when available.

Job-market analysis also summarizes source-provided job titles and occupational-family labels, plus explicit education and experience fields. Counts are unique ads and percentages use the selected ads as the denominator. Missing requirement fields are reported as “Not stated.” Pattern matches in qualifications, descriptions or skills text are kept as source-linked evidence candidates with surrounding text; they are not silently promoted to structured job requirements and require researcher verification.

Phrase-level aligned and partially aligned rates divide the corresponding status count by all phrases in ALIGNED or PARTIALLY ALIGNED status. The unmapped rate divides NOT MAPPED phrases by all assessed phrases (ALIGNED, PARTIALLY ALIGNED and NOT MAPPED). UNCLASSIFIED is excluded; if its denominator is empty, the rate is unavailable rather than zero. Rates are calculated before the status-display filter and metadata records their denominators.

Unmapped skills are phrases below the mapping threshold. “Emerging skill candidates” are unmapped phrases present in at least the configured number of distinct job ads (default two). This does not establish novelty or absence from PSF-AAI; that requires human review, source context and longitudinal evidence.

## Outputs and limitations

Training sources and the analytical sample serve separate purposes. Reviewed training examples may come from additional eligible job-ad sources. Findings and research exports use only the active cleaned job upload and selected filters, for example the study's selected 500-ad sample. Extraction records and exported annotations are restricted to selected job source IDs; additional training records are excluded. Export metadata records selected row count, source IDs and a sample fingerprint. Researchers must verify the retained count after screening, deduplication and filtering rather than assume that an uploaded 500-row file yields 500 eligible advertisements.

Research exports include selected cleaned job data, extracted phrases, sample-linked reviewed labels, verified PSF-AAI, classifier predictions, PSF mappings, employer–PSF alignment, demand, job-title and occupational-family counts, requirement summaries and source-linked requirement evidence, unmapped candidate tables, a workbook and a generated written report. Model evaluation and held-out test predictions are available separately through Evaluate models; they are not presented as findings from the selected analytical sample. Training on additional data does not make evaluation independent: document any overlap between training sources and the research sample. Source IDs, evidence fields and reference pages support traceability. Metrics from a saved evaluation that overlaps job-ad source IDs are withheld from the Model Evaluation page. Any displayed scores still require researcher review and independent validation before publication.

Job-ad samples may be incomplete or unrepresentative. Public ads can be duplicated, stale or ambiguous about required versus preferred skills. PDF layout extraction can omit or misread text; manual verification is required. Exact/alias matching may miss paraphrases, while fuzzy/semantic matching may overstate similarity. Classifier evaluation is conditional on human label quality and sample composition. Independent double coding, agreement/adjudication and out-of-sample evaluation strengthen research validity. Findings are descriptive and do not establish causal relationships or workforce proficiency.
