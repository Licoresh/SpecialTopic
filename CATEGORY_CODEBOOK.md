# Analytical category hierarchy

The study uses one mutually exclusive leaf category per normalized phrase. The requirement type and parent category are derived from that leaf. These are researcher-defined analytical categories, not official TESDA categories. PSF-AAI competency assignments and matching rules are unchanged.

| Stored leaf | Requirement type | Parent | Decision rule |
|---|---|---|---|
| AI / Machine Learning | Competency | Technical / Digital | Explicit AI methods, model development or AI systems |
| Data / Analytics | Competency | Technical / Digital | Analysis, statistics, SQL, reporting and business intelligence |
| Technical / Digital | Competency | Technical / Digital | General programming or digital tools without explicit AI or analytics context |
| Business / Domain | Competency | Domain knowledge | Knowledge of a business function or industry |
| Soft / Enabling | Competency | Enabling capabilities | Communication, collaboration and personal effectiveness |
| Leadership / Management | Competency | Enabling capabilities | Directing people, supervising or managing teams |
| Education / Qualification | Credential requirement | Not applicable | Degrees, licenses and certifications |
| IRRELEVANT | Excluded | Not applicable | Fragments or text outside the coding scope |

The stored Technical / Digital value is retained for compatibility; its displayed leaf is General programming and digital tools. Existing annotations are not automatically reclassified or represented as newly reviewed. Previously saved custom labels remain visible but require review against this codebook.

Use source context and the most specific applicable leaf. For example, Python programming belongs to general programming; predictive model development belongs to AI / Machine Learning. Split compound requirements into meaningful phrases before reviewing. If the same normalized phrase has conflicting meanings across advertisements, inspect the context and refine the phrase rather than silently choosing a category.

Report credentials separately from competency frequencies. Parent totals must use the same counting unit as child totals. For job-level prevalence, deduplicate job IDs within each parent; a job may request several skills. Never sum a parent and its children into a grand total. These categories require researcher pilot review; implementation alone does not establish validity.

## Phrase normalization review

Phrase normalization is separate from category assignment. Preserve the original wording and source advertisement, and combine wording only when the phrases describe the same competency in context.

- Keep exact, source-audited non-skill fragments out of every skill graph: “allow individual(s)” company marketing, “analyst work” occupation/experience wording, “asset(s) across Strategy” corporate profile text, the malformed “AI based” fragment, and “AI prompt” when extracted only as a title fragment. Store them in the chart phrase audit with a reason; do not erase or relabel source evidence.
- For chart display only, group **“communication”**, **“communication skill(s)”**, and **“strong communication skill(s)”** as **“communication”**; **“collaboration skill(s)”** and **“strong collaboration”** as **“collaboration”**; and **“problem solve,” “problem-solving,”** and **“problem solving skill(s)”** as **“problem solving.”** Deduplicate each ad within the display label across employer-skill graphs. Keep distinct facets such as written/verbal communication, teamwork, and adaptability separate unless researchers document a shared construct. Preserve all source wording and reviewer decisions; do not change categories, training labels, or PSF-AAI links.

- For chart display, group **“ability to learn”** and **“learn and apply”** under the broader label **“learning and application.”** This is an explicit umbrella label, not a claim that the phrases are identical. Keep the original wording and advertisement evidence, count each ad once even if it contains both, and do not rewrite researcher labels, training data, or PSF-AAI links. Keep other learning-related phrases (such as “willingness to learn” or “adaptability”) separate unless researchers review and document the same construct.
- Treat exact **“access benefit(s)”** or **“access to benefit(s)”** wording as unclear pending context review. If it refers to compensation or employee benefits, exclude it from competency counts. If the ad describes a genuine work competency (for example, navigating an employee-benefits system), record the specific action stated in the ad and code that competency after review.
- Chart labels may use documented display aliases when the source context shows the same competency: **“agile scrum”**, **“scrum”**, and their method/methodology variants display as **“agile scrum”**; standalone **“agile”** stays separate because it is broader. A lemmatizer-generated **“datum”** token is displayed as **“data”** in this analytics domain; original wording and normalized source values stay unchanged.
- The graph-only relevance screen withholds **“protected by applicable (law)”** legal boilerplate, **“activity/activities and work”** generic duty wording, and **“adoption of insight(s)”** outcome/KPI wording from skill charts. It retains the source evidence and reason in the phrase audit. These display rules do not revise saved researcher labels, PSF-AAI decisions, or training data.
- Apply these checks to the final 500-ad dataset before interpreting skill rankings. Do not infer a skill from an isolated phrase, an AI draft, or the phrase's PSF-AAI mapping. PSF-AAI content and mapping rules are unchanged.
