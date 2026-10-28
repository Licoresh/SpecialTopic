# Validation record

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
