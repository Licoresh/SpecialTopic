# Validation record

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
