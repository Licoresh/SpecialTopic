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

Manual Labeling uses the pinned open-weight BAAI/bge-m3 encoder to rank broad competency descriptions and entries in the active PSF-AAI taxonomy against each phrase and its nearby source sentence. BGE-M3 is an embedding model, not a trained category classifier. Scores are similarity rankings, not calibrated confidence, accuracy or research metrics. The workflow filters common connector-led/trailing phrase fragments and prioritizes exact research vocabulary and multiword candidates before applying the per-posting cap. Reviewers still inspect the full source context and can edit or reject every draft.

Only manually reviewed Philippine job-ad phrases with source type, source ID, reviewer and timestamp qualify as training observations. PSF assignment is optional and refers to the reviewed reference. AI drafts are suggestions, not gold labels: they are never saved or used for training unless a researcher explicitly copies a value, checks it against its source context, and saves it. BAAI/bge-m3 ranks category descriptions and entries in the active PSF-AAI taxonomy; it is an embedding model, not a trained category classifier. Similarity scores are not calibrated confidence, accuracy or research metrics. The app cannot establish that a saved label is correct or independently reviewed.

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

Exports include cleaned job data, extracted phrases, reviewed labels, verified PSF-AAI, classifier predictions, PSF mappings, employer–PSF alignment, demand, job-title and occupational-family counts, requirement summaries and source-linked requirement evidence, unmapped and emerging candidate tables, model evaluation, test predictions, a workbook and a generated written report. Source IDs, evidence fields and reference pages support traceability. Metrics from a saved evaluation that overlaps job-ad source IDs are withheld from the Model Evaluation page. Any displayed scores still require researcher review and independent validation before publication.

Job-ad samples may be incomplete or unrepresentative. Public ads can be duplicated, stale or ambiguous about required versus preferred skills. PDF layout extraction can omit or misread text; manual verification is required. Exact/alias matching may miss paraphrases, while fuzzy/semantic matching may overstate similarity. Classifier evaluation is conditional on human label quality and sample composition. Independent double coding, agreement/adjudication and out-of-sample evaluation strengthen research validity. Findings are descriptive and do not establish causal relationships or workforce proficiency.
