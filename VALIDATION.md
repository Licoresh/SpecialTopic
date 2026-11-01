# Validation record

## 2026-11-01 — Finish shared design and chart presentation, v2.0.108

- Applied the warm ivory, maroon, gold and charcoal design across theme, shared page styling and charts. Included consistent sizing/spacing, compact workflow strip, overview icon alignment, readable heatmap axes, current hover-label behavior, and the visual direction/reference image.
- Full suite: **476 passed** in 129.51 seconds, with one existing pandas `FutureWarning` at `src/review_queue.py:138`. Python compilation, `node --check src/chart_hover.js`, and `git diff --check` passed.
- Live browser confirmation remains pending because the local workspace is interrupted by a Supabase connection error. No research records, reviewed labels, PSF-AAI mappings, or exports were changed.

## 2026-11-01 — Exclude source-audited fragments from skill graphs, v2.0.107

- Traced “allow individual” to company marketing about customers; also screened “analyst work” occupation/experience wording, “asset across strategy” corporate profile text, malformed “AI based,” and “AI prompt” from a job-title fragment. These now stay out of every skill graph with source-linked reasons in `chart_phrase_review`.
- This is a chart-only screen. Ads, extraction rows, reviewer labels, training data, title counts, and PSF-AAI mappings remain unchanged. Chart presentation version advanced to 9.
- Verification: 136 focused working-tree chart/profile/results/end-to-end/UI/scale tests passed in 63.53 seconds; the commit-specific chart/profile suite passed 33 tests in 1.30 seconds. Python compilation and `git diff --check` passed. Live chart verification is blocked by the running app's Supabase connection interruption. Commit `1bea8c7` was pushed to GitHub main.

## 2026-11-01 — Consolidate repeated chart wording and role variants, v2.0.106

- Employer-skill graphs share documented aliases for communication skills, collaboration variants, and problem-solving variants. Each ad counts once under its broader label. Written/verbal communication and distinct constructs remain separate. Chart aliases are presentation-only; original phrase evidence, researcher categories, training labels, and PSF-AAI mappings do not change.
- Common job-title display combines “business analyst (erp functional consultant)” with “business analyst” and the same-role slash pair “data engineer / senior data engineer.” Distinct-role composites remain separate; original titles stay in evidence.
- Updated the unmapped/emerging chart explanation and chart-presentation cache version. The local saved extraction still contains 20 source IDs and has 0 overlap with the 500-ad cleaned dataset, so current 500-ad skill counts cannot be verified until extraction is refreshed.
- Read-only audit of the selected 500-ad `cleaned_jobs.csv`: the documented ERP title is grouped under `business analyst`; the same-role slash title is grouped under `data engineer`. Resulting chart counts are 61 and 45 distinct ads respectively. Original titles remain in `common_job_title_evidence`.
- The local `extractions_original.csv` still contains only 20 source IDs, with 0 overlap against the selected 500 ads. Skill aliases are verified by synthetic regression tests, but updated skill totals for the final 500 cannot be confirmed until that dataset is extracted again.
- Verification: 56 focused chart/profile/results/end-to-end tests and 79 UI/scale tests passed. Python compilation and `git diff --check` passed. No research labels, source data, training data, or PSF-AAI mappings were changed. Local and uncommitted.

## 2026-11-01 — Group learning wording under a broader chart label, v2.0.105

- The explicit chart aliases “ability to learn,” “learn and apply,” and direct normalized variants display as “learning and application” across shared employer-skill graphs. Each ad counts once under this label even if it contains both phrases. Other related concepts, such as willingness to learn or adaptability, remain separate unless researchers document the same construct.
- Original phrase evidence, reviewer category labels, training inputs and PSF-AAI mappings are unchanged. Chart presentation schema advanced to version 7.
- Focused graph suite: **36 passed** (`tests/test_chart_data.py tests/test_result_views.py tests/test_end_to_end.py`). Python compilation and `git diff --check` passed. No new extraction or visual-browser claim was made.

## 2026-11-01 — Apply chart relevance rules across result graphs, v2.0.104

- One chart-eligible skill table feeds employer-skill rankings, categories, occupational-family comparisons, selected-title/location skills and unmapped/emerging charts. Added exact missing-placeholder handling for job-title labels and geography; source evidence is retained. Requisition codes, clear title variants, exact geography, structured education/experience and valid posting dates continue to use field-specific rules.
- PSF-AAI reference labels and mapping decisions, and model-evaluation classes/metrics, keep their separate validated evidence rules. No broad text filter is applied to them. No research data, labels, mappings or training inputs were changed.
- Read-only audit of the selected 500 ads: 220 common-title categories, no missing-title labels or leading requisition codes, and the seven intended source job families. Location evidence contains 248 exact localities, 98 region-only locations, 144 unfamiliar locations needing review, 9 broad/remote values, and 1 conflicting value; only resolved regions/localities enter those comparisons. Education has 1 unambiguous parsed level, 466 not-stated values and 33 review-needed values. All 500 explicit experience fields are blank, so no numeric experience distribution is invented. Posting dates have 239 usable ads across 28 months; the remaining 261 are not plotted as dates.
- The saved local phrase extraction still has 0/500 source-ID overlap, so current 500-ad skill graph counts cannot be visually confirmed until extraction is refreshed.
- Verification: full suite **471 passed** in 110.73 seconds, with one existing pandas `FutureWarning` at `src/review_queue.py:138`. Python compilation and `git diff --check` passed. No browser screenshot was used to claim refreshed 500-ad skill output. Local and uncommitted.

## 2026-11-01 — Screen questionable chart phrases and consolidate Scrum aliases, v2.0.103

- Skill charts now withhold exact equal-employment boilerplate (including “protect by applicable”), generic “activity/activities and work” duty fragments, and “adoption of insight(s)” KPI wording. The KPI screen also catches the lemmatized “adoption insight” form. These source-linked rows remain in `chart_phrase_review` with reasons.
- “Agile Scrum,” “Scrum,” and exact method/methodology variants display under one “agile scrum” label. Standalone “agile” stays distinct. Chart labels also restore lemmatizer-generated “datum” to “data”; original normalized wording remains available in occurrence evidence. Each ad counts once per displayed skill.
- Read-only scan of `cleaned_jobs.csv`: 500 unique ads. “Agile Scrum” occurs in 1 ad and is explicitly requested as understanding of Agile Scrum methodologies; “activities and work” occurs in 8; legal boilerplate in 74; “adoption of insights” in 1; “ability to learn” in 11; “data governance” in 39; literal “datum” in 0. The methodology phrase is treated as a requested work-method/knowledge competency, not a programming tool.
- Important local-data limitation: `extractions_original.csv` contains 3,388 rows for 20 source IDs, with **0 IDs overlapping** the current 500-ad cleaned file. No final-500 chart totals or browser appearance are claimed from this stale extraction snapshot. Refresh phrase extraction for the 500 ads before relying on its displayed counts.
- Chart exclusions/aliases affect presentation and audit only; no saved phrase labels, source text, PSF-AAI links, reviewer decisions, training records or job records were rewritten. PSF-AAI matching logic is unchanged.
- Full suite before the final KPI-normalization edge: **469 passed** in 110.25 seconds, with one existing pandas `FutureWarning` in `src/review_queue.py:138`. Post-edge focused suite: **34 passed** (`tests/test_chart_data.py tests/test_result_views.py tests/test_end_to_end.py`). Python compilation and `git diff --check` passed. The Streamlit skill’s version-matched docs were unavailable because this environment has a pre-1.57 Streamlit install; no Streamlit APIs were changed. Local and uncommitted.

## 2026-11-01 — Make result heatmaps and date coverage easier to read, v2.0.102

- Put long skill and PSF-AAI competency labels on heatmap rows and comparison groups in columns. Counts, percentage denominators, hover evidence, and full tables are unchanged.
- Multi-month posting-date coverage now uses chronological integer bars. A single month remains a metric; neither view presents sample coverage as market growth.
- Updated the methodology and user guide to match chart order and interpretation.
- Focused checks: **62 passed** (`tests/test_design.py tests/test_result_views.py`). Python compilation, `git diff --check`, and localhost health passed. The authenticated chart page could not be visually reviewed because localhost was signed out at the rerun prompt. No study data, labels, or PSF-AAI decisions changed. Local and uncommitted.

## 2026-11-01 — Isolate PSF-AAI heatmap filters from page loading, v2.0.101

- Moved heatmap role/competency controls, chart and evidence table into a Streamlit fragment. Editing these controls reruns only the heatmap, not the full Job Market page's shared-data loader. No chart definitions, data, labels or PSF-AAI mappings changed.
- Focused synthetic UI check: **1 passed**, including clearing all selected competencies and rendering the empty-state message. Python compilation and `git diff --check` passed. Browser verification of the authenticated Job Market remains pending because localhost is signed out. Local and uncommitted.

## 2026-11-01 — Keep overview metric icons inside their cards, v2.0.100

- Overview metric icons now flow within the padded label row instead of sitting at the card's outer top-left edge. The icon tile is 40 px and aligned with the label; semantic icon colors, values, and metric definitions are unchanged.
- Added a CSS regression assertion to the existing overview icon test. Focused design test: **1 passed**. Python compilation and `git diff --check` passed. Visual verification is pending because the local browser is signed out.
- No research data, calculations, labels, or PSF-AAI mappings changed. Local and uncommitted.

## 2026-11-01 — Flag questionable benefit wording and learning variants, v2.0.99

- Exact “access to benefit(s)” wording, including the normalized form “access benefit,” is withheld from skill and PSF-AAI demand charts and retained in the source-linked phrase audit pending review.
- “Ability to learn” and “learn and apply” are recorded as a human-review candidate pair. They remain separate until researchers compare source context and document whether they represent the same construct; chart changes do not rewrite saved labels or mappings.
- `python -m py_compile src/analytics.py src/config.py src/workflow.py` and `git diff --check` passed. No extraction rows, reviewer labels or PSF mappings were modified.
- A focused phrase-rule check confirmed the access-benefit wording is withheld while “ability to learn,” “learn and apply,” Python and SQL remain chart-eligible. The local server restarted at v2.0.99 and health returned `ok`. The restarted browser session required sign-in; the authenticated chart could not be visually rechecked because the shared-workspace connection was interrupted.

## 2026-11-01 — Keep chart tooltips anchored and persistent, v2.0.98

- The live page kept a prior hover observer after Streamlit reruns; it removed newer tooltip copies, causing the label to flicker or disappear. The current handler uses version-specific state and a distinct retained-label marker, so the older observer cannot remove it.
- The retained label is cloned inside Plotly's original SVG group to preserve the exact chart coordinates. It updates on a new bar/cell and clears when the pointer leaves the chart.
- Manually checked the real local Job Market page: bar tooltip stayed visible after moving onto it and waiting five seconds; heatmap tooltip stayed visible after moving onto it and waiting nearly two seconds. In both cases it stayed anchored beside the hovered mark. No data was edited.
- `node --check src/chart_hover.js`, Python compilation, localhost health and `git diff --check` passed. No research data, labels, mappings or chart calculations changed.

## 2026-11-01 — Use the visual reference and refine the research pipeline, v2.0.95

- Created `DESIGN_REFERENCE_JOB_MARKET.png` as a project design benchmark. Its visible example counts are explicitly illustrative, not research findings. `DESIGN_DIRECTION.md` records which visual choices are adopted and which are intentionally adapted for filter scope, full evidence, exports and long chart labels.
- Reworked the five-stage analysis overview into one compact bordered strip with unboxed stages. It reduces vertical space without treating the static workflow as progress or implying completion.
- Responsive check at 390 px showed the steps using full-width rows; the compact breakpoint now fits two steps per row and keeps the final step in a readable row.
- Focused design tests: **42 passed** in 5.31 seconds. Full suite: **464 passed** in 106.47 seconds. One pre-existing pandas `FutureWarning` remains at `src/review_queue.py:138`.
- Python `compileall` and `git diff --check` passed. The isolated synthetic Job Market preview returned HTTP 200 and was screenshot-reviewed at 1280 × 720; it rendered all five steps within one surface and kept the stage copy readable.
- The 390 px review had exposed single-column steps. The final responsive rule sets a 160 px stage basis and is covered by a regression assertion; a second narrow-viewport screenshot was not captured after that last adjustment. No real job ads, reviewed labels, PSF mappings, credentials or exports were used in the preview.
- No packages were installed. Research calculations and stored data were unchanged. Local and uncommitted.

## 2026-11-01 — Route-by-route UI and chart audit, v2.0.93

- Visually reviewed synthetic previews for Overview, Upload, Data Quality, Competency Extraction, Manual Labeling, Training, Evaluation, Job Market Analysis, PSF Mapping, Employer–PSF Alignment, Unmapped Skills, Reports, Feedback, Methodology, Research Readiness, and Settings. Also inspected Job Market Analysis role/location and qualification views. The previews used 18 fictional postings and five fictional framework rows; no real data or credentials were used.
- Kept the upload route heading above the dataset selector so the page purpose is clear before choosing a file type.
- Upload heading now follows the selected dataset type on rerun; a full-suite failure exposed that the PSF-AAI selection retained a generic/stale title.
- Fixed the sequential chart palette configuration (Streamlit requires 10 color stops; seven had caused fallback to default colors). Kept the categorical palette and chart values unchanged.
- Shortened the selected-sample KPI label to avoid truncation; made the quality summary, source-ad context table and experience-band table use plain labels. The experience sort key is hidden from the page view; stored and report source tables are unchanged.
- The default upload heading now names the selected dataset and updates on selection; a full-suite regression found the PSF-AAI selection had kept a generic title. Browser verification confirmed both Job Data and PSF-AAI headings.
- Synthetic preview health returned HTTP 200. The refreshed chart used the configured maroon/taupe series with integer job-ad ticks; no sequential-palette fallback warning appeared. Data Quality headings were checked in the rendered table, and the upload, quality and results views were screenshot-reviewed at 1280 × 720.
- Full suite: **463 passed** in 104.48 seconds. One existing pandas `FutureWarning` remains at `src/review_queue.py:138`. Python compileall and `git diff --check` passed. The visual preview is not a mobile-device or school-network benchmark.

## 2026-11-01 — Apply shared visual direction across the research workspace, v2.0.91

- Added DESIGN_DIRECTION.md with a route-by-route design brief inspired by academic campus colors; it explicitly avoids implying MSU-IIT affiliation. Applied a deep maroon, gold and warm-neutral theme across sign-in, workspace chrome, controls, tables, workflow steps and charts. Reduced oversized headings, standardized surfaces, 44 px controls and spacing, and made chart palette consistent without changing chart values.
- Full suite: **461 passed** in 103.81 seconds. Includes empty and populated AppTest coverage for every route. One existing pandas FutureWarning remains at src/review_queue.py:138. Python compileall and git diff --check passed.
- Localhost /_stcore/health returned ok. Visually inspected the sign-in page in the in-app browser at a narrow viewport; no credentials were entered. Authenticated route layout was checked through synthetic AppTest fixtures, not a real signed-in browser session.
- No research data, labels, mappings, calculations, permission checks, routes or export scopes changed. Local and uncommitted.

## 2026-11-01 — Withhold vague and unfinished phrases from skill graphs, v2.0.90

- Added deterministic wording checks for vague-only labels (for example, `strong`, `IT experience`, `business experience`) and unfinished list tails (`etc.`, `and others`). These are omitted from employer-skill demand, occupational-family charts, unmapped/emerging analysis, and automatic PSF-AAI matching because all use the same filtered skill set.
- Withheld phrases remain in `chart_phrase_review` with reasons, including rows not accepted by extraction. Source rows, researcher labels, and exact skill phrases such as SQL, Python, advanced SQL, and communication skills remain unchanged. This is a transparent rule-based screen; it does not claim to detect every semantic ambiguity.
- Full suite: **460 passed** in 99.83 seconds; one existing pandas `FutureWarning` at `src/review_queue.py:138`. The run includes the new phrase-screening regression; `compileall` and `git diff --check` passed.
- No research records or saved labels changed. No extraction rerun required; this is a result-view rule update.

## 2026-11-01 — Complete chart-guide recommendations and narrow-layout review, v2.0.85

- Audited the supplied guide's selection table, dashboard recommendations, interaction and interpretation rules. Kept optional lollipop, donut/waffle, choropleth, beeswarm, scatter, hexbin and treemap views out because the guide marks them optional and this dashboard lacks a justified comparison/denominator for those views; ranked bars and tables answer the current questions more directly.
- Added the recommended skill-by-occupational-family overview heatmap. Color is the share of all ads in each family, while hover retains exact skill-ad counts and family totals; unclassified families are counted below, and ads without chartable skills remain in the denominator. Family/title drill-down shows at most ten skills by default, a searchable complete selected-group table, group size and a small-group warning.
- Replaced the role-by-family PSF heatmap with reviewed competency-by-role evidence, keeping role ranking separate. Counts are unique ads per cell; color uses the within-role share and hover includes the denominator. Role filtering now scopes the competency percentages correctly and preserves multi-role/competency overlap.
- Changed education to a naturally ordered horizontal bar; missing education remains a count and percentage below it. Experience includes frequency evidence plus median/range only for at least two exact single-value numeric requirements; ranges and open-ended values are not coerced. Location charts now compare regions first, then exact cities within a selected region, and say raw counts are not population-adjusted rates.
- Added responsive wrapping for overview/result metrics and workflow cards below 900px so fixed-width cards no longer force a clipped horizontal row.
- Focused results/design/data tests: **59 passed**. Full suite: **453 passed** in 101.14 seconds with one unrelated pandas `FutureWarning` at `src/review_queue.py:138`.
- Python AST parsing and `git diff --check` passed. No study records, labels or PSF-AAI review decisions changed. Guide text and tables were read; visual DOCX rendering was unavailable because LibreOffice (`soffice.exe`) is not installed. Localhost visual review and health are recorded after refresh.

## 2026-11-01 — Apply PSF-AAI chart-selection guide to role heatmap, v2.0.83

- Read the supplied chart-selection guide. It recommends charting the comparison that is analytically meaningful, keeping missing values as a count outside the graph, and reporting full counts/denominators with percentage heatmaps. The app's existing top-category default is 15, within its recommended 10–15 range.
- Updated the PSF-AAI role-by-family heatmap to color by each role's within-role family share on a fixed 0–100% scale. Hover retains exact cell job-ad count and the all-family role denominator; the denominator remains stable when families are hidden. One visible cell stays a headline metric with its share and role total.
- Focused results/design tests: **46 passed**. Full suite: **446 passed** in 100.05 seconds with one unrelated pandas `FutureWarning` at `src/review_queue.py:138`.
- Python AST parsing and `git diff --check` passed. The project server was restarted from this repository with the project interpreter; `/_stcore/health` returned HTTP 200 (`ok`) and the loaded project version is v2.0.83. No research records, labels, or PSF-AAI review decisions changed. The guide's text/tables were read; visual DOCX rendering was unavailable because LibreOffice (`soffice.exe`) is not installed.

## 2026-11-01 — Exclude non-skill phrases from demand graphs, v2.0.82

- Added explicit handling for missing/not-mentioned placeholders and experience-duration/year fragments (including parsed `3+year` forms and malformed year fragments). They are excluded from employer skill demand, automatic PSF-AAI matching, unmapped and emerging skill outputs. Source occurrences and reasons remain in the phrase audit; explicit experience fields remain in Qualifications.
- Irrelevant and credential phrases remain excluded. The employer-skill view reports counts below the graph for placeholders, experience/year wording, irrelevant labels and ads with no chartable skill; none become graph categories.
- Updated workflow status filtering and tests to cover phrase suppression, PSF mapping inputs and truthful per-ad counts. The pipeline integration test confirms SQL remains in demand/mapping while “not mentioned” and `3+year` remain auditable but are excluded from both.
- Full suite: **445 passed** in 97.00 seconds, with one unrelated pandas `FutureWarning` at `src/review_queue.py:138`. No source data, saved labels or PSF review decisions were modified.
- Python AST parsing and `git diff --check` passed. Localhost was refreshed to v2.0.82 and health returned HTTP 200. AppTest verified result view captions and chart exclusions; responsive browser screenshots were not reviewed.

## 2026-11-01 — Single-value results and large-dataset chart scaling, v2.0.81

- Results with one category or one heatmap cell now use a large labeled metric; a single posting month is described as coverage, not a trend. Multi-category charts retain their selected visual form and aggregations.
- Chart controls now explain that charts show at most 10–30 aggregated categories while complete evidence remains paginated and exportable. Single-value metrics reuse the shared responsive metric styling.
- Added a synthetic 500-ad / 93,622-row regression covering distinct-ad aggregation, 30-bar chart bounds and 100-row table pages. Focused results/design/scale tests: **45 passed**. Full suite: **441 passed** in 104.21 seconds with one unrelated pandas `FutureWarning` at `src/review_queue.py:138`.
- Applied the descriptive-analysis guide: remove chart clutter, keep labels and units explicit, use consistent emphasis, and prefer a prominent number when no comparison exists. No research data or chart calculations were changed.
- `git diff --check` and Python AST parsing passed. Localhost health returned HTTP 200 after refresh. Browser screenshot/responsive interaction review was unavailable in this run; Streamlit AppTest covered the results views. Local and uncommitted.

## 2026-11-01 — Remove audience guidance from results, v2.0.80

- Removed the green audience-guidance strip and its scoped CSS from Job Market Analysis. Results metrics, filters, chart controls and methodology remain unchanged.
- Focused results/design suite passed: 42 tests. Changed Python files passed AST parsing; `git diff --check` passed; source search confirms the removed copy/style is gone.
- Bytecode compilation via the system Python was blocked while replacing an existing `.pyc`; the AppTest suite ran successfully using the project virtual environment. No full suite or browser screenshot run. No research data changed. Local and uncommitted.

## 2026-10-29 — Tooltip handoff and all count axes, v2.0.72

- User clarified the pointer moves from the bar onto the tooltip. Reproduced native Plotly removal on this transition. A trusted local browser handler now retains a copy of the already-rendered SVG card inside the chart, updates on another hover, and clears on chart exit or redraw. It never calls Python, extraction or storage. One observer attaches handlers to new chart nodes; script layout is hidden. This uses Streamlit's supported JavaScript-enabled HTML API and Plotly DOM/event conventions, which should be rechecked on frontend upgrades.
- Browser synthetic preview confirmed native hover text became empty while the retained card remained readable under the pointer; it updated to another bar and cleared outside the chart. Rerun and remove/restore checks confirmed handlers reattach. Escape clearing requires keyboard focus inside the chart. Full browser refresh loads script changes during development.
- All indivisible count scales now use integer ticks: job/demand bars, horizontal distributions, posting totals and heatmap color scales. Decimal metrics remain unchanged. 40 presentation/populated-page tests passed after correcting a helper-name collision caught by the first run; compilation/diff/localhost health passed. Browser checks used synthetic data; no research records changed.

## 2026-10-29 — Exclude unused chat-model checks from study methods, v2.0.70

- Updated the Methodology page to describe the study's actual BGE-M3 suggestion and researcher-review process, and state that no separate chat-model check produced or informed study labels, mappings, or results. The optional software integration remains separate from the analysis method.
- `METHODOLOGY.md` is rendered directly by the Methodology page. Source inspection and `git diff --check` passed; no research records changed. No tests run for this documentation-only update.

## 2026-10-29 — Methodology page overview, v2.0.69

- Added a concise workflow table to the top of the Methodology page, separating each system stage from the researcher checkpoint and clarifying phrase-wide category labels versus occurrence-level PSF-AAI decisions.
- The Methodology page reads `METHODOLOGY.md` directly. Source inspection and `git diff --check` passed; browser review confirmed the page renders the updated Markdown. No research records changed.

## 2026-10-29 — Explicit readable result tooltips, v2.0.68

- Result charts now use explicit dark hover backgrounds and white text. Bar and distribution hover templates include wrapped, HTML-escaped category labels and their values; count bars use integer formatting and grouped model metrics preserve decimal values and matching trace labels. Original x/y values, counts and source frames remain unchanged.
- 19 presentation checks passed, including long-label wrapping/escaping, grouped trace identity and count preservation. An isolated Streamlit browser preview at 420px chart width verified full long job titles and Job ads: 1 on center and edge bars. Computed tooltip colors were rgb(23,59,56) and rgb(255,255,255). This preview used synthetic data; the authenticated results page was not exercised.

## 2026-10-29 — Methodology aligned with current workflow, v2.0.68

- Clarified optional Ollama behavior and fallback, recorded that local inference was not verified because the endpoint was unreachable on 2026-10-29, and corrected the current review-table description. Described phrase-wide category labels separately from occurrence-specific, multi-competency PSF-AAI decisions and required rationales.
- Documentation/version inspection only; no research records changed. Live Ollama inference remains unverified.

## 2026-10-29 — Methodology aligned with saved-result workflow, v2.0.67

- Added saved extraction provenance, separate software/pipeline revisions, exact legacy compatibility, shared freshness checks, and the distinction between extraction reuse and updated occurrence-level PSF reviews. Corrected the default unique-phrase display description and documented persistent mapping status, server-confirmed saves and integer frequency-axis intervals.
- The real Streamlit Methodology renderer executed in AppTest without exceptions and included the revised sections; diff checks passed. Documentation was checked against the current implementation. No research data or original extraction metadata changed.

## 2026-10-29 — Reuse compatible saved extraction results, v2.0.66

- Extraction freshness now uses an explicit pipeline revision independently of the app's display version. New runs record both revisions. Legacy v2.0.60–2.0.65 hashes are accepted only when reconstructing the complete current input fingerprint exactly matches the saved hash; this compatibility belongs to pipeline revision 1 only. Historical metadata is never rewritten.
- Results and Research Readiness use the same compatibility check. Real data/framework/annotation/upload/mapping/settings/model changes, unknown legacy releases and future pipeline changes remain blocked. Successful saved-result loading already invalidates session read caches.
- 39 focused tests passed: legacy/current freshness, actual input changes, pipeline upgrades, Load saved results → Job Market → Research Readiness without extraction, immutable metadata/output, extraction retry guards and end-to-end exports. Compilation/diff/localhost health passed. Live authenticated shared loading was not exercised; the standalone local backup did not match local-only input state, so no claim of active shared-run freshness is made. No research records changed.

## 2026-10-29 — Whole-number job counts, v2.0.65

- Job-ad and employer-demand bar charts now use integer tick intervals with at most about eight intervals. Decimal model scores keep their original axes. Direct assertions passed for count totals 1, 2, 5 and 500, unchanged source frames, and a decimal score.

## 2026-10-29 — Chart hover and visible saved mappings, v2.0.64

- Removed physical border/padding from Streamlit's measured Plotly node; an inset shadow keeps its border without changing measured size. Installed frontend sizing makes the old decoration a potential redraw trigger; the original flicker was not reproduced conclusively.
- PSF Mapping now displays persisted competency names (or a reviewed no-match), reviewer and Philippine timestamp on every render; saved decisions use Update competency links. Unsaved competency selections and stale references remain explicit. Removed reference IDs remain visible in stale review summaries.
- The shared mapping RPC must confirm the expected new integer version before the UI can report success; an uncertain response clears caches and asks the reviewer to inspect persisted status.
- 39 focused tests passed, including save/revisit/occurrence-switch/no-match, authenticated reviewer identity, RPC confirmation, mapping evidence and chart sizing. UI imports were preloaded to avoid the existing cold-start test timeout. Compilation and diff checks passed; localhost health returned ok. Browser verification used isolated synthetic charts: wrapper heights stayed 450/300 with zero border/padding, and the Python/12 tooltip remained visible across idle samples. Live authenticated research writes were not exercised. No research records changed.

## 2026-10-28 — Share restored source evidence, v2.0.63

- Manual Review → Team updates → Restore shared ad evidence lets an authenticated admin recover verified local raw CSV context into blank shared candidate text. It patches only `original_text` for matching advertisement IDs and job source types. Existing evidence, annotations and active study selection remain unchanged.
- 85 shared-storage, review-queue and UI-performance checks passed (UI imports preloaded); compilation, diff checks and localhost health passed. Live database repair was not performed: Supabase MCP OAuth refresh failed, and no local server credential was configured. Run the action on the original-upload computer, then refresh the teammates' shared review tables.

## 2026-10-28 — Resolve unmarked review evidence, v2.0.62

- Review text recovery now uses the exact source ID for job candidates even when deduplication removed the extraction's `_job_context` marker. Blank original text falls back to that source's stored job description. Existing context is preserved; unknown source IDs remain blocked.
- Older candidates can recover text from an exact raw CSV archive, verified against its full upload hash and original row. The screenshot source `jobs:a06d0b386aec539e:7` recovered 1,968 characters. This does not add archived ads to the active study dataset.
- 25 review-queue and UI-performance tests passed after preloading `src.ui`, including rejection of a changed archive. The initial run passed 23 tests but hit the existing AppTest three-second cold-import timeout. Compilation and diff checks passed. Live browser verification was unavailable because local browser control is disabled.

## 2026-10-28 — Restore evidence for shared extracted occurrences, v2.0.61

- Shared extraction indexes omit long source text to keep reads compact. Manual PSF-AAI review now restores missing evidence from the matching candidate using the same source ID and normalized phrase.
- Existing extracted evidence remains authoritative; context is never copied from a different advertisement.
- Targeted verification: `tests/test_review_queue.py`.

## 2026-10-24 — Retry finished extraction saves, v2.0.59

- Finished extraction and diagnostics are retained in the originating job's memory after a connection/file-write failure. Retry saving recomputes input fingerprints and checks cleaning metadata plus local/published model identity before publication, without repeating NLP or matching. Local model guards are separate from the cross-device study signature. A restart, sign-out, dismissal or replacement job discards the in-memory retry copy; this is not durable job recovery.
- Failed result refreshes preserve the visible snapshot. Malformed or empty GET response bodies raise an error instead of being treated as an empty shared dataset. Successful minimal write responses remain supported.
- Full suite passed 339 tests in 85.53s with one existing pandas FutureWarning. Tests verify one computation across a failed save/retry, exact restored output, rejection of changed jobs/taxonomy/labels/settings/cleaning/model, preserved visible tables and malformed-response errors. Compilation and diff checks passed. Research data was not changed; school-network behavior and simultaneous multi-device operation remain unverified.

## 2026-10-24 — Connection recovery and extraction progress, v2.0.58

- Supabase reads and explicitly repeat-safe app_state upserts retry connection resets, timeouts and transient 502/503/504 responses at most three times, using a fresh pooled connection after failure. Permission/certificate errors fail immediately. Review-save RPCs are not replayed. UI progress displays retry attempts, elapsed time, preprocessing/scanning counts and upload batches; stage percentages are not time predictions.
- Profile matching reuses word-to-profile scores and uses RapidFuzz's native maximum-score search with the same scorer and thresholds. Read-only comparison on the entire 500-ad dataset produced exactly equal extraction and diagnostic frames: 93,622 records, 90.719s baseline versus 64.539s optimized (29% less local computation time). A 25-ad check also matched all 5,660 records (5.965s versus 2.421s). No classifier or reviewed annotations were supplied in these timing runs; they do not measure model accuracy or network transfer time.
- Gzip level 6 preserves the storage codec while reducing compression effort. A 2,000-record compact payload measured 0.0417s/145,139 bytes at level 9 versus 0.0187s/147,042 bytes at level 6. Level 1 was rejected because it increased transfer size to 185,491 bytes.
- Full suite: 330 isolated tests passed in 80.99s, with one existing pandas downcasting FutureWarning. Tests cover identical matching scores, progress/output equality, bounded retry behavior, fresh connections with identical snapshot payloads, auth/TLS failures and preservation of the previous manifest when a chunk upload fails. Compilation, diff and localhost health checks passed. No live Supabase data or research files were changed. Teammate hardware/network timing and authenticated browser rendering remain unverified.

## 2026-10-23 — Deferred extraction results, v2.0.57

- Extraction page entry no longer downloads saved extraction or NLP diagnostic tables. Explicit result loading uses the existing authenticated background worker, exposes progress/cancellation/errors, and transfers the completed read into the session cache. Only review columns and the diagnostic limit flag are requested; displayed pages remain limited to 100 records.
- 321 isolated software tests passed in 100.04 seconds; one existing pandas downcasting FutureWarning remains. The focused extraction/worker run passed 16 tests. Checks include a blocked reader with responsive page controls, visible connection failure, preservation of approved labels, unchanged result rows, and browser pagination. Compilation and diff checks passed.
- No research records, labels, PSF mappings, or export scope changed. The teammate screenshot has different button wording from this checkout; their exact installed version, network latency, and authenticated browser behavior remain unverified. Old shared snapshots may still take time to download when explicitly requested.

## 2026-10-22 — Review-page drafts and queue reuse, v2.0.55

- Both draft columns remain visible, including pages without predictions. Draft status distinguishes missing, incomplete, ready and intentionally irrelevant rows. Generation processes only missing/incomplete visible rows unless the researcher explicitly regenerates a complete page. Tests cover pages 3 and 4, partial drafts and unchanged manual fields.
- Page BGE-M3 batches are saved before optional Ollama context checks. The editor polls saved drafts while the job runs and preserves manual category/competency cells, including browser edits arriving with an update. Completion does not refresh away pending decisions or evidence. Readers and writers share a file lock; a busy Windows replacement leaves displayed drafts intact until the next poll.
- Prepared queues, fragment flags and source-ad counts are cached within the authenticated session. Local file revisions invalidate the cache; shared mode uses revision checks, a 15-second lifetime and explicit Team updates invalidation. Source evidence, save conflict checks, extraction semantics, reviewed-label gates and exports are unchanged.
- Read-only local check on 93,582 usable occurrences and 94 reference entries: cold queue preparation **2.3698s**, repeated cached preparation **0.0128s**. This excludes local source-pack inventory scans and is not whole-page or school-network timing. No research data was modified.
- Actual pinned BGE-M3 inference ran offline on one existing SQL occurrence, without saving its prediction: model loading **22.214s**, first inference/reference encoding **13.156s**, repeat inference **0.119s**. Both runs returned an allowed category and three IDs in the active reference. This confirms execution and schema validity, not research accuracy. Ollama was unreachable; its successful live inference was not tested.
- Full regression suite: **318 passed in 73.45s**, with one existing pandas downcasting FutureWarning in `review_queue.py`; focused suite: **113 passed in 39.80s**. Compilation, diff and localhost health checks passed. Authenticated browser rendering and multi-device school-network performance remain unverified.

## 2026-10-21 — Background processing and compact review reads, v2.0.54

- Extraction, classifier training (including opt-in after-save training), page AI drafts and bounded local AI batches now run in a session-owned background worker. One heavy job is admitted per app process. A fragment polls only job status, so page navigation remains available and completion does not rerun the page or discard unsaved edits. Cancellation is cooperative; publication disables cancellation. Training retains its existing local lock and shared lease.
- Worker credentials and HTTP/cache state are isolated from Streamlit session state using a ContextVar. Workers never receive refresh tokens. Expired access tokens stop the next authenticated operation; signing out requests cancellation. Worker HTTP connections are closed after completion. A process restart interrupts jobs; progress is not a durable cross-session queue. Saved draft batches remain resumable.
- Shared extraction saves include a compact review projection and source-to-chunk metadata, published in the same immutable manifest only after all chunks succeed. Review screens avoid downloading full evidence; occurrence mapping fetches only chunks for selected sources. Complete reads/exports still use the full generation. Old snapshots remain readable but need an extraction rerun to gain the new indexes. Chunk names remain compatible with the existing admin cleanup RPC. No SQL migration or new dependency is required.
- Local cold review reads project only necessary CSV columns. Source-filtered reads stream large CSVs in bounded chunks and cache the selected evidence. The UI restores source text for the displayed occurrences. Shared training does not scan unrelated local training files. Bounded suggestion runs stop scanning once their requested draft count is reached; a file lock protects draft read/merge/write against concurrent processes.
- Extraction records its input signature before processing and checks again before publication, refusing to publish if the data, framework, settings, model or reviewed labels changed. Existing provenance, researcher approval, category conflict, occurrence mapping and model evaluation rules remain in force. No real research data or labels were modified by these checks.
- Read-only benchmark on the actual **500 job ads / 93,622 extraction rows** (443,370,864-byte CSV): full DataFrame estimated memory **981,413,558 bytes**, four-column review DataFrame **24,311,970 bytes**. Cold full read **2.5454s**, cold review read **2.0369s**, repeat review read **0.0050s**; ten-source evidence read **2.8125s cold / 0.0010s repeated**. Exact DataFrame equality was checked against the original for review columns and selected full evidence. These are single-run component timings and pandas memory estimates, not process peak RAM, UI/network timings or research accuracy metrics.
- Full regression suite: **312 passed in 73.87s**. After replacing the new boolean context marker with a string to avoid pandas downcasting warnings, **93 focused UI/performance/worker tests passed in 39.56s with no warnings**. Tests use isolated synthetic workspaces; worker teardown completes before their filesystem/network guards reset. Added checks cover nonblocking launch, duplicate rejection, cancellation/publication boundaries, auth isolation/expiry, connection cleanup, input-change rejection, concurrent draft preservation, unsaved UI state, compact-projection reads and full-evidence equality. Compilation, diff checks and localhost health passed.
- Limits: true relational database pagination and a durable distributed job queue are not implemented. The full review metadata index is still loaded; complete analytics/exports can still be expensive. First AI model loading, shared-network performance, browser rendering and simultaneous use on school devices were not benchmarked. Local browser automation was disabled. Changes remain local until committed and pushed.

## 2026-10-21 — Performance improvements, v2.0.53

- Reuse decoded local frames by file revision and shared chunked frames by immutable generation, within the authenticated session. Callers receive independent DataFrames; logout clears them. Review saves invalidate derived results without redownloading unchanged chunks. Existing authentication, optimistic concurrency, provenance and stale-result gates remain.
- Manual Review requests the lightweight candidate index, fetches original source evidence for the displayed occurrences, prepares only needed extraction columns, and resolves mapping evidence for the displayed sources. Closed source tools do not scan the training folder. Large general tables display 100 rows per page; complete CSV/XLSX exports remain available.
- Result bundles now reuse unchanged input/extraction/review/correction revisions instead of expiring every 12 seconds. Workbook/CSV/report generation runs when downloaded, not while opening Reports. Supabase requests reuse session-local HTTPS connections; spaCy imports only when preprocessing starts. Range-of-Application text is normalized once per matcher.
- Read-only timing on this PC's 93,622-row extraction file (443,370,864 bytes): repeated CSV read **2.6216 → 0.0084 seconds**; profiled review preparation with extraction cached **3.4351 → 0.2875 seconds**. The isolated comparison excluded local training-folder inputs and retained all 93,622 extracted candidates. Cold CSV read remained **2.8243 → 2.6016 seconds**. These are single-run component timings, not end-to-end school-network or AI-inference measurements.
- Compared the previous matcher from Git HEAD with the updated matcher using the first 2,000 real extracted phrases and all 94 bundled competencies: **1.5587 → 1.0574 seconds**, with exactly equal candidate dictionaries, scores and ordering. No labels were generated or promoted by this comparison.
- Full suite: **299 passed, one existing pandas FutureWarning, in 71.52 seconds**. After batching context requests, the focused performance/import suite passed **14 tests**. Checks cover cross-session isolation, invalidation, failed-load handling, context preservation, scoped extraction equality, page navigation, deferred downloads, concurrent review safeguards and training/import gates. Tests use isolated synthetic fixtures; they are not classifier evaluation metrics.
- Compilation, diff checks and localhost health passed. The live app showed v2.0.53 and shared-workspace access, but browser control was subsequently disabled in Work settings before the review load completed. Final live first-load timings and school-device performance remain unverified. No research data, taxonomy definitions or saved annotations were changed.
- Context batch filters follow the [PostgREST logical-operator syntax](https://docs.postgrest.org/en/stable/references/api/tables_views.html#logical-operators). No database migration or dependency installation is required.

## 2026-10-19 — Explicit reference account layout, v2.0.32

Replaced nested native identity widgets with escaped HTML and an inline outline SVG so the avatar, blue email, muted role and two dividers have explicit geometry matching the supplied reference at app scale. Retained the native popover and sign-out handler. Added a white popup pointer, 360px viewport-bounded card, 26px heading, 60px avatar and 58px action button. All 16 design/auth tests passed in 3.37 seconds; compilation and diff checks passed. Browser inspection was attempted and remains blocked by disabled Local browser use; exact visual matching is not verified.

## 2026-10-19 — Account card spacing refinement, v2.0.31

Reduced card width from 340px to 300px, padding from 24px to 16px, section gaps from 20px to 8px, identity padding to .65rem, avatar to 32px and sign-out minimum height to 44px. Preserved the reference layout and existing account/sign-out behavior. All 16 design/auth tests passed in 3.43 seconds; compilation and diff checks passed. Rendered dimensions remain unverified.

## 2026-10-19 — Reference-based account card, v2.0.30

Updated the Account popover to follow the supplied visual reference: rounded white card with shadow, bold heading, circular profile symbol beside wrapping email/role text, separated identity section, and a pale-blue full-width native sign-out button with logout icon. Uses real session identity and the existing sign-out callback. All 16 design/auth tests passed in 3.68 seconds; compilation and diff checks passed. Browser inspection was attempted but Local browser use remains disabled, so visual matching is unverified.

## 2026-10-19 — Portrait account menu, v2.0.29

Following the user's screenshot clarification, replaced the content-width popup with a 224px-wide portrait card. Its vertical content has a 216px minimum height plus outer padding, a heading, separated email/role lines and the existing sign-out button. Height can grow and email wraps; width remains bounded by the viewport. All 16 design/auth checks passed in 3.47 seconds, including account contents and sign-out. Compilation and diff checks passed. Rendered sizing remains unverified.

## 2026-10-19 — Compact account menu, v2.0.27

Removed the oversized divider and reduced account-menu spacing. Scoped the Account popover to 280px with a viewport-safe maximum and wrapping email text. Kept the existing sign-out handler and 44px button target. All 16 design/auth tests passed in 3.44 seconds, including a new identity/sign-out regression check. Compilation and diff checks passed; the rendered dimensions have not been browser-verified.

## 2026-10-19 — Research workspace presentation, v2.0.26

- Final full suite: `..\.venv\Scripts\python.exe -m pytest -q --disable-warnings --maxfail=2 --tb=short` — **263 passed, 1 warning in 83.55 seconds**. Synthetic fixtures only; these are software checks, not research results.

- Reworked Overview around one next action, actual saved-state metrics, six workflow cards and a concise research-readiness panel. Applied a shared surface, typography, navigation and spacing treatment. No dashboard trends or completion percentages were invented.
- Manual Review now places search, filters and pagination together; guidance, AI details and team refresh are compact popovers. Preparation tools appear below the review workspace but execute before loading its data, preserving immediate updates. The same combined editor, full-screen action bar, source provenance, rationale validation and account attribution remain. Offline imports are collapsed. The table has an accessible description and space for the ten-row batch.
- Pre-change source copies are under ignored `tmp/product-design-v2025-before`. No dependency or database migration was added, and no live research records were changed. Compilation, diff checks and localhost health passed.
- Browser inspection remained blocked: the tool repeatedly reported Local browser use disabled, including after the user indicated they would enable it. No new screenshots or responsive visual sign-off are claimed. Test coverage includes populated/empty screens, mappings, generation, account attribution, auth, filters and model flows; new checks cover overview counts/actions and filtered empty states. Text-pair contrast checks cover the added dark panel, button and muted-text colors. A misplaced assertion in a newly added test was corrected before the final run.

## 2026-10-19 — Account reviewer attribution, v2.0.25

- Removed the Reviewer ID reminder from Manual Labeling and PSF Mapping. Signed-in sessions use their account email without an editable reviewer field. Offline work retains its explicit reviewer field; a configured shared session missing its account identity asks the user to sign in again rather than fabricate attribution.
- UI suite: **61 passed in 50.80 seconds**. New synthetic tests verify both review pages hide manual identity entry and persist the account identity on two competency links; Manual Labeling also preserves it on category annotations. The initial test used duplicate rationales and was correctly rejected by existing validation; the fixture was corrected to distinct Python/SQL evidence. No live shared records were saved.
- Compilation and diff checks passed. Restarted the actual app with `..\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true`; health returned `ok`.

## 2026-10-19 — Full-screen manual review workspace, v2.0.24

- Added **Full-screen review**, which expands the same review workspace and preserves its widget/draft state. Save and AI generation share a sticky action bar above the table. Reviewer details, filters, source evidence and mapping rationales remain accessible. The table-only expansion button is hidden in this workspace to avoid excluding the actions.
- AI context checks and notes now appear as read-only columns beside the category and competency drafts in the editable table. The former separate AI notes table was removed. Long notes open on double-click; horizontal scrolling retains the pinned phrase column.
- Full synthetic suite passed **253 tests, 1 warning in 75.68 seconds**. Updated AppTests exercise generation while expanded, saving multiple links while expanded, and preserving rationale fields when switching out and back. After the final CSS adjustment, the design suite passed **10 tests in 2.70 seconds**, including a new scoped/reversible fullscreen-style check. Compilation and diff checks passed.
- Browser verification used a separate local synthetic preview, with shared storage disabled and preseeded mock AI drafts. Confirmed full viewport expansion, sticky actions while scrolling, visible competency dropdown, context-note expansion and restoration of sidebar/normal layout. Visual proof: ignored `tmp/fullscreen-review.png`. The live user's selections were not touched; real model inference and live Supabase writes were not exercised. No dependency was added.

## 2026-10-19 — Combined review table and multiple AI candidates, v2.0.23

- Supersedes the v2.0.22 separate-tab layout. Manual Review presents Category and an inline PSF-AAI multiselect in one table, with one row per phrase and source advertisement. Evidence expanders retain separate rationales and explicit confirmation. Category decisions retain their phrase-level scope; competency decisions remain advertisement-specific.
- AI review drafts now retain up to three ranked, distinct PSF-AAI candidates from the active reference. These are alternatives for researcher assessment, not approved mappings or probabilities. Legacy single-candidate drafts remain readable and require page-level regeneration to gain multiple candidates. The automatic research mapper remains separate.
- Final full suite: `..\.venv\Scripts\python.exe -m pytest -q --disable-warnings --maxfail=2 --tb=short` — **253 passed, 1 warning in 69.99 seconds**. The targeted AI/UI suite also passed **77 tests**. Checks cover multiple-link save/reload, source isolation, blank manual fields, rationale validation, partial-save reporting, ranked-candidate persistence, and legacy draft compatibility. Tests use synthetic fixtures and mocked embeddings; no real model inference or model-quality evaluation was performed.
- Compilation with `..\.venv\Scripts\python.exe -m compileall -q app.py src pages` and `git diff --check` passed. Localhost health returned `ok`. Streamlit minimum version is now 1.65; the installed version already meets it, so no dependency installation was needed.
- Browser access became available. The live combined table and inline dropdown with multiple selected tags were visually inspected at the available narrow viewport. User selections were left unsaved and untouched. This is not a complete responsive viewport audit or a live persistence test.
- Category and occurrence writes remain separate transactions; a later failure reports the saved portion explicitly. Live Supabase occurrence-review writes and the previously prepared migration remain unverified. No live research data or framework definitions were changed during verification.

## 2026-10-18 — Header clearance fix, v2.0.21

The user's screenshot showed the workspace header and Account button clipped beneath Streamlit's fixed toolbar. Removed desktop and mobile top-padding overrides from `src/design.py`, preserving Streamlit's native top clearance while retaining horizontal gutters and bottom spacing. Added a regression check against overriding that clearance at any declared breakpoint. `..\.venv\Scripts\python.exe -m pytest tests/test_design.py tests/test_ui.py -q` passed **65 tests** in 46.98 seconds. Compilation and `git diff --check` passed. The rendered fix has not yet been browser-verified.

## 2026-10-18 — UI redesign, v2.0.20

- Baseline before redesign: `..\.venv\Scripts\python.exe -m pytest -q` — **235 passed** in 89.57 seconds.
- After redesign: the same full-suite command — **245 passed** in 82.17 seconds. A final targeted authentication/chart check passed **9 tests** after refining error messages and long chart labels. Timings describe these runs, not a performance benchmark.
- `..\.venv\Scripts\python.exe -m compileall -q app.py src pages` passed. Streamlit parsed the updated theme configuration. `git diff --check` passed. There is no separate frontend build, lint, or type-check configuration in this repository.
- Coverage includes all existing empty/populated page tests, direct protected-page access, expired sessions, failed-login cleanup, successful login with membership checks, missing-input validation, disabled login controls, model training, mapping review, settings, corrections, and export snapshots. New tests confirm chart counts/categories are unchanged, CSV generation is deferred until its expander opens, and the training-file inventory is read once per render. Primary-button and body-text contrast meet the tested 4.5:1 threshold.
- The redesign modifies presentation and removes duplicate UI work. The research extraction, classification, alignment, database schema and routing implementations were not changed for this redesign. Previously pending many-to-many mapping changes remain in the working tree.
- Isolated synthetic preview servers started and both health endpoints returned `ok`. No live credentials or research records were used for these checks.
- **Visual checks remain unverified:** the browser tool reported “Local browser use is disabled in Work settings,” including after the user indicated they would enable it. No screenshots, viewport/overflow checks at 320, 375, 390, 430, 768, 1024, 1440 or 1920 px, browser-console/network checks, or live Supabase login were completed. Run those checks before release. Automated AppTest results are not visual or live integration verification.
- Rollback copies of pre-redesign UI/configuration files are in the ignored local folder `tmp/ui-redesign-before`. No dependency was added. Synthetic previews are disposable developer-only files under `tmp`; they are not application routes or deployment entry points.

## Earlier validation record

## Automated software tests

The cleanup verification passed **121 tests in 34.38 seconds**. Tests use synthetic data only in temporary directories; these test metrics are not research results. Coverage includes CSV/XLSX loading, editable automatic column mapping, job cleaning, NLP, extraction, manual labeling, both TF-IDF classifiers, stratified evaluation, model persistence, PSF mapping, employer alignment, demand denominators, emerging/unmapped outputs, exports, and Streamlit pages. A dedicated source-reader check verifies the bundled official PDF parser.

## Official framework source

The official TESDA PDF was downloaded from its clean HTTPS URL with tracking parameters removed and saved at `data/reference/psf_aai_official.pdf`. It has 315 viewer pages. Three representative pages (FSC, ESC and a multi-column proficiency table) were rendered and visually inspected. The parser extracted 78 FSC and 16 ESC definition blocks, official competency codes, descriptions, 1-based PDF viewer page numbers, source URL and SHA-256. It also extracted 1,029 literal career-map competency links across 28 roles. The test checks these counts, IDs, pages and hashes. Aliases are not synthesized. Extracted records remain a draft until a researcher verifies and activates them.

## Application and data integrity

All 16 configured Streamlit pages passed AppTest in the prior run, and the full test suite still passes after cleanup. The existing posting CSV matches its recorded SHA-256. `train/labeled_competencies.csv` has zero reviewed rows, and no fitted research pipeline or research metrics are present. Two isolated prototype model binaries and temporary PDF page images remain in ignored local folders because automatic approval review blocked their deletion; the application does not load or display them.

## 2026-10-18 — Manual Review multiple competencies, v2.0.22

- Manual Labeling now has Categories and PSF-AAI competencies tabs. The latter selects a phrase and advertisement, then supports multiple exact active-reference competencies with separate rationales. Both review pages share the occurrence review store. Category edits preserve each source's legacy reference; category filters do not hide phrases from competency review.
- Synthetic AppTest checks verify two-link save/reload, source isolation, blank initial selections, and missing-rationale rejection. Helper checks verify exact extracted context and preservation of distinct legacy references. The full suite passed **250 tests in 69.92 seconds** with `..\.venv\Scripts\python.exe -m pytest -q --disable-warnings --maxfail=2`. A final reference-normalization refinement was checked with all four review-queue tests. Compilation and `git diff --check` passed.
- Localhost was restarted on 127.0.0.1:8501 and its health endpoint returned `ok`. This confirms server availability, not browser rendering or authenticated shared writes.
- Browser inspection remains blocked by disabled Local browser use in Work settings. The existing occurrence-mapping Supabase migration remains unapplied/unverified on the live database. No research data or framework definitions were edited by these tests.

## 2026-10-24 — Unique manual-review phrases, v2.0.60

Manual Review now defaults to one row per normalized phrase, using the existing representative-source grouping. All advertisement occurrences remains available for context-specific PSF-AAI review. No source records or frequencies are deleted; category saves still expand across occurrences, while competency links remain advertisement-specific. Related phrases are not merged by fuzzy similarity.

Verification: 96 targeted UI, review-queue and performance tests passed in 43.52 seconds. Tests cover deduplicated pagination, preserved source counts, category propagation and PSF mapping isolation. Compilation, git diff checks and localhost health passed. Synthetic grouping of 98,681 rows into 2,000 distinct phrases took 0.094 seconds; this is grouping-only timing, not school-network performance. Live authenticated shared writes and visual browser interaction were not tested. No research data changed.


## 2026-10-30 — Training-only model selection, v2.0.73

Model selection now uses training CV mean macro F1, mean weighted F1 and lower macro-F1 standard deviation, with stable model order for exact ties. Selection finishes before holdout predictions; publication uses that fixed choice. Both candidates keep holdout diagnostics without using those scores to choose the winner. Missing or nonfinite CV stops the run before holdout evaluation and preserves existing model artifacts. New metadata records selection_basis=training_cross_validation; earlier saved runs stay readable with a legacy comparison notice. No refit on test labels. Review, extraction, PSF-AAI mapping and study-data handling are unchanged.

Verification: 34 focused synthetic tests passed across classifier selection, training persistence, source/conflict validation, evaluation calculations, UI save/load/predict, historical metadata and end-to-end workbook exports. Tests verify the winner cannot change when holdout scores favor the other candidate, and invalid CV leaves saved artifacts byte-for-byte unchanged. Compilation and git diff --check passed. These are software tests in temporary workspaces with live Supabase disabled, not research metrics. No real annotations or saved research models were retrained or changed. Existing grouped-CV behavior remains conservative: a category missing from a fold blocks selection; review more independent sources across categories. Local update, not committed or pushed.


## 2026-10-30 — Temporarily hide Research readiness, v2.0.74

Set native st.Page visibility to hidden for Research readiness only. The page remains registered for existing overview links and direct authenticated navigation; its implementation and checks are retained. AppTest verified its hidden state and every other page visible, without live data reads. git diff --check passed. Started localhost on 127.0.0.1:8501; health returned ok. Local, not committed or pushed.


## 2026-10-30 — Professor feedback and audience-led result views, v2.0.75

Implemented meeting feedback on duplicate skill labels, overcrowded role/location charts, numeric experience requirements, missing fields, unclear phrases and readable graph values. Results now have Skills, Roles and locations, Qualifications, and PSF-AAI demand views for the chancellor and students. Horizontal bars show integer distinct-ad counts, full labels, zero baselines, highest-demand or alphabetical order, visible chart limits and purposeful emphasis. Focus selectors replace the full role/location matrices. Requirement coverage is text; experience-year tables preserve parsing evidence and missing/ambiguous statuses. Only linked PSF evidence enters competency demand plots.

A separate chart view consolidates case/Unicode/space/list variants without fuzzy synonym merging. Conservative unclear-phrase rules withhold chart labels, preserve source-linked reasons, and leave raw records, reviewed labels and PSF mappings intact. Charts count each selected ad once per phrase, including no-detection ads in denominators. New exports include chart_skill_demand, chart_skill_occurrences, chart_phrase_review, requirement coverage and explicit experience parsing evidence. Display cache revision changes without invalidating an otherwise current extraction. Data-quality preview is deferred until expanded. Methodology and user guide document policies, limitations, the supplied descriptive-analytics slides, ONS and Government Analysis Function references.

Verification: full isolated suite passed 408 tests (103.22 s); compilation and git diff --check passed. Browser inspected synthetic charts and qualification coverage/table; role filters, alphabetical order, audit preservation and mixed mapped/unmapped cases have regression coverage. Synthetic chart preparation of 98,681 occurrences / 2,000 phrases took 0.539 s; this is chart preparation only, not complete app or school-network timing. Localhost health returned ok. No real research records or model artifacts were changed. The supplied PDF was read and its decluttering slide rendered/inspected; unrelated assignment instructions in it were not followed. Synthetic proof image is outside the repo at C:/Users/User/.codex/visualizations/2026/10/10/01a12448-83b3-70a2-bb64-4b9ae314a86c/research-chart-preview.png. Local update, not committed or pushed.


## 2026-10-30 — Complete lowercase and meeting-feedback corrections, v2.0.76

User clarified strict lowercase analysis values and related-title grouping or alphabetical specifics. Descriptive job *_clean/cleaned_text fields now lowercase; analysis_jobs refreshes derived fields in a copy for existing uploads, analysis_job_values drives normalized preview/export, and chart labels no longer restore vocabulary capitals. Raw source wording, IDs, dates, case-sensitive link paths, original occurrence evidence and official PSF-AAI records remain intact. Cleaning is idempotent with no repeated *_clean_clean columns. Stored research records were not rewritten.

Related-role counts prioritize meaningful source job_family, then conservative explicit title-head rules. Seniority variants may share a group; ambiguous/composite/unrecognized titles remain specific when no source family overrides them. Original title, normalized title, group and grouping_basis are exported per advertisement. Specific-title counts/charts/selectors are alphabetical even in demand-ranking mode. Role grouping never merges source ads. Added actual five-stage visual workflow cards on Job market and Methodology, consistent alphabetical/highest-demand controls on other result pages, concrete category-dictionary/model provenance, CAR (Context/Approach/Results) report headings, and a meeting concern-to-implementation checklist in Methodology.

Verification: full isolated suite 416 passed (92.01 s), including raw-evidence preservation, annotations, title grouping, alphabetical controls, export scope, mapping behavior and normalized previews. One old capitalization-specific extraction test was updated to assert normalized phrase identity plus preserved original source text and human labels; no production inference change was needed for that assertion. Browser inspected workflow cards, lowercase skill/location labels, related roles and alphabetical specific-title mode using synthetic data. Independent source review found no blocking evidence/hash regression; a source-family override caption was clarified. Compilation and diff checks passed, localhost health ok. Synthetic screenshot: C:/Users/User/.codex/visualizations/2026/10/10/01a12448-83b3-70a2-bb64-4b9ae314a86c/lowercase-titles-preview.png. Local update, not committed or pushed.


## v2.0.77 — Revision plan, focused results and extraction performance (31 October 2026)

- Added ten-stage workflow details, reasoned screening exclusions and confirmation-only duplicate candidates based on identical normalized title/employer/location/full description. Screening retains the mapped-upload fingerprint and archived records.
- Added ordered education-level charts/evidence; bounded experience-band tables/evidence; alphabetical titles within source families with provider/URL evidence; conservative PSA PSGC location hierarchy with explicit unresolved statuses.
- Added cascading family/title/geography filters and reset, date-coverage summaries, reference-order competency charts and bounded PSF role/family heatmap. Multi-role filtering restricts exploded role rows; counts remain distinct ads. Added exact Power BI/Excel presentation aliases, status colors, data-driven takeaways and exports.
- Result summaries are precomputed in the cached bundle; only the selected result section constructs charts. spaCy document text is retrieved once per document rather than once per n-gram. Extraction semantics and pipeline revision are unchanged.
- Full isolated suite: **433 passed**, 2 warnings, 137.10 s. After the final implementation changes, focused result/preprocessing/screening/chart/export checks: **53 passed**, 1 warning, 20.30 s. Benchmark retention tests: **5 passed**. Compilation and git diff --check passed. Live Supabase was disabled in software tests.
- Actual local first-N benchmarks covered 20/100/250/500 ads. A comparison retaining all 500 rows measured total local processing 114.78→34.13 s and extraction/matching 110.18→29.49 s; source/taxonomy fingerprints, 93,581 candidates, 7,963 accepted occurrences and 2,007 chart labels matched. Full extracted records/diagnostics also matched in a separate 20-long-ad comparison. Full baseline 500-ad frames were not retained, so their complete byte equality is not claimed. Database/auth/browser timing is excluded; cache and concurrent-load conditions limit comparisons. Reports are outside the repo in performance-assessment-2026-10-31 under the visualization workspace.
- Eleven potential duplicate repostings were flagged in the local source file; the active dataset was not rewritten or reduced. The benchmark now retains all rows and reports candidates separately. No research labels/models were published or trained.
- Browser visual verification uses synthetic advertisements, not research findings. Localhost restarted on 127.0.0.1:8501; health returned ok. This update is local and uncommitted.


## v2.0.78 — Reference styling, shared sizing and flat layouts (31 October 2026)

Shared design applied through render/page_intro and auth states across all16 workspace pages. Added a lightweight decorative SVG header, breadcrumb treatment, consistent Material icons, theme palette, native workflow/KPI components, working Export results action, standard44px controls, shared spacing tokens and flat visual sections. Kept native titles/forms/actionguards, Plotly measurement-node sizing, hover handler and scoped/reversible fullscreen review behavior.

Verification:137 isolated page/auth/presentation/performance-cache checks passed (70.52s), including all empty/populated workspace pages. Following layout changes,61focused checks passed (13.63s); later palette/navigation checks41passed (14.49s); final35chart/auth/export checks passed (6.13s). These runs overlap and are not additive. Compilation and git diff --check passed. Browser verification used synthetic records in a separate temporary workspace with Supabase disabled; no real data or models were changed. At1280px, workflow cards measured158px each, KPI cards153.8px each, selectors44px and export action44px. At390px, workflow cards measured130px each, controls44px and document width390px with no page overflow. Temporary viewport override was reset. Localhost restarted and health returnedok. Changes are local/uncommitted.


## 2026-11-01 - Heatmap spacing and nested table rendering, v2.0.87

Moved heatmap x-axis labels below the grid and reserved title/label space; dense matrices receive extra height. Corrected the skill-by-occupational-family dataframe so it is nested inside its disclosure expander. No counts, denominators or research data changed. `tests/test_design.py tests/test_result_views.py`: 56 passed. `compileall`, `git diff --check`, and localhost health all passed. App tests use synthetic fixtures; no authenticated browser screenshot was captured.

## 2026-11-01 - Remove requisition codes from analytical job-title labels, v2.0.88

Leading identifiers matching 2–6 letters followed by at least four digits and a separator are omitted from title-analysis labels (for example, `DE033824-Health Operations Analyst` displays as `health operations analyst`). Original titles remain unchanged in the source data and title-evidence exports. Verified against the active 500-ad file: eight matching ads now share the clean label; source titles are preserved. No research records were rewritten.

Verification: `tests/test_job_profile.py tests/test_result_views.py tests/test_end_to_end.py`: 38 passed. Actual-data title check confirmed eight ads under the clean label and no code in analysis labels. `compileall`, `git diff --check`, and localhost health passed. Streamlit skill discovery found the installed Streamlit version predates the bundled references; this data-layer change uses no new Streamlit APIs. Local and uncommitted.

## 2026-11-01 - Exclude occupational labels and context fragments from skill results, v2.0.89

Skill charts and accepted-skill input now exclude clear occupational labels, incomplete standalone `data`, `industry experience`, and `base` (the lemma produced from source wording `based`). Excluded accepted rows remain visible in phrase-audit evidence with source wording and reviewer decisions; no annotations or source files are rewritten. Valid skill labels such as SQL, Python, data analysis, communication and data engineering remain eligible.

Verification: chart, end-to-end, gap, large-scale, results, revision and extraction suites: 44 passed. On the local extraction file, the chart output contained none of the excluded terms and the phrase audit retained all 8 terms checked. The source extraction frame was unchanged. `compileall`, `git diff --check` and localhost health passed. App tests use software fixtures; no model was retrained. Local and uncommitted.
