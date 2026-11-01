# Research workspace visual direction

**Status:** Implemented in v2.0.108; live browser confirmation is pending because the shared Supabase session is interrupted.
**Reference:** MSU-IIT-inspired academic workspace direction; this is an independent design choice and does not imply official university endorsement.

## Visual reference

![Job Market Analysis visual design reference. Every chart value is illustrative and is not a study result.](DESIGN_REFERENCE_JOB_MARKET.png)

The image is a visual benchmark for spacing, hierarchy, chart emphasis and evidence proximity. Its displayed counts are placeholders, not findings. The application must use the selected research data for every count and export.

Adopted across the system: warm ivory surfaces, maroon primary emphasis, restrained gold, readable charcoal text, aligned controls, a compact process strip, and one prominent comparison at a time. Applied route by route through shared theme and layout rules.

Research-specific adaptations: keep the authenticated dataset and competency filters in the shared sidebar; keep complete evidence and all export rows available; use question-appropriate chart forms and denominators; retain full-width horizontal bars when long occupational labels need room. These departures preserve the working research workflow and readability instead of copying a single static page literally.

## Design intent

Make the research workflow feel calm, clear, and dependable. Researchers should see where they are, what the current page is for, what evidence supports a decision, and what action comes next. Visual hierarchy should clarify the work without suggesting findings that are not in the data.

This is a presentation system. It does not change research data, labels, calculations, mappings, exports, navigation routes, or authentication.

## Shared visual system

| Element | Direction |
| --- | --- |
| Brand | Deep maroon, #78182B; use for primary actions, active navigation, key chart emphasis, and page accents. |
| Supporting accent | Warm gold, #D6A33D; use sparingly for numbered workflow markers and framework emphasis. |
| Foundation | Warm ivory, #FBF8F4; white surfaces, neutral #F6F5F3, and charcoal #24303D. |
| Semantic states | Keep success green, information blue, review/warning amber, and errors red distinct from brand decoration. |
| Type | Existing sans-serif family; compact page titles, readable body text, tabular numerals for counts, sentence case labels. |
| Spacing | 4, 8, 12, 16, 24, and 32 px rhythm. Use 16 px card padding and aligned control rows. |
| Controls | 44 px minimum height, consistent 8 px corners, visible keyboard focus, clear disabled and busy states. |
| Surfaces | One visible card layer for a section, 10 px shared radius, fine neutral borders, and restrained shadows. Avoid nested bordered boxes. |
| Layout | Content capped near 1440 px, responsive cards and tables, compact breadcrumb, grouped sidebar navigation. |
| Icons | Material Symbols. Use a stable icon and semantic color for the same action/status on every page. |

## Page direction

| Route | Visual hierarchy |
| --- | --- |
| Sign in | One centered form with clear identity, access-help text, and concise verification state. |
| Overview | Actual study counts, current workflow state, one next action, then supporting steps. No decorative data-like sparklines. |
| Upload study data | File selection and encoding first, compact preview next, then save. Keep source data visibly distinct from analysis transformations. |
| Review data quality | Screening scope, exclusions and duplicate checks first; preview and evidence remain easy to inspect. |
| Extract skill phrases | Current-input state, extraction action/progress, and saved result status. Keep candidate phrases separate from reviewed labels. |
| Review and label phrases | Review table first, save actions close to it, and source evidence available beside each decision. Preserve the compact table workflow. |
| Train classifier | Reviewed-label eligibility and source selection first, model action next, then recorded run status. Predictions never look like approved labels. |
| Evaluate models | Evaluation design, held-out data definition, and computed metrics in that order. Show a metric only when it was actually calculated. |
| Job market | Scope and filters before job/skill charts; true advertisement counts, clear denominators, readable labels, and complete tables. |
| PSF mapping | Competency decision, framework evidence, Range of Application, and save status presented together without nested cards. |
| Employer–PSF alignment | Alignment categories and denominators first, then evidence-backed charts and table. Gold is a visual accent, not an alignment claim. |
| Unmapped / emerging skills | Distinguish “not clearly mapped” from “framework gap.” Keep review candidates separate from confirmed researcher decisions. |
| Reports | State export scope and available files; keep download actions easy to find and preserve complete records. |
| Research readiness | Audit checklist with clear pass, warning, and blocked states. A pass never implies thesis approval. |
| Methodology | Structured reading flow: data, definitions, decisions, and limitations. Keep citations and research wording intact. |
| Feedback | Short input form with privacy/purpose context and clear submit/confirmation state. |
| Settings | Group controls by data, review, analysis and model behavior; label the effect before the control. |

## Chart and evidence rules

- Use maroon for the main series and gold for a deliberate comparison or highlight; use neutral colors for secondary bars. Use the shared categorical palette only when several series need distinction.
- Keep semantic status colors stable across icons, badges, tables, and charts.
- Keep integer advertisement axes on whole numbers. Use readable horizontal bars for long labels and heatmaps only for real comparisons with explicit denominators. Put long skill or competency labels on heatmap rows and comparison groups in columns; use bars for discrete sample-frequency bins.
- Hover adds exact values and source context; it must not be the only way to discover an essential count.
- Do not truncate source labels in evidence tables or exports. Explain overlapping categories and multi-mapping in nearby text.
- Loading skeletons appear only while the page or data is genuinely unavailable; keep existing content visible during background work.
- The five-step analysis overview is one compact bordered strip with unboxed stages; numbered badges establish sequence without implying that any stage is complete.

## Acceptance checks for future interface work

1. The same maroon/gold, neutral surfaces, type scale, spacing, icon meaning, and status colors appear on every route, including sign-in.
2. Desktop, tablet, and mobile layouts wrap without clipping titles, controls, charts, tables, or account actions.
3. Every control is keyboard reachable and has a visible focus state; status does not rely on color alone.
4. Each section has one clear visual container layer, aligned controls, and a useful empty, loading, error, and success state.
5. Charts show only observed data, preserve exact calculations and exports, and use appropriate labels and denominators.
6. Existing data, workflow, permission checks, model behavior, and exports still pass the project's automated checks.

## Suitability assessment

This direction fits a Philippine academic research dashboard: it favors traceability, legible evidence, conservative status language, and repeatable workflow over promotional visuals. The maroon/gold choice is an aesthetic reference only; there is no use of official seals or a claim of university affiliation. Research claims and result graphics remain driven by the selected dataset and reviewed evidence.
