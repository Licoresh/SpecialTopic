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
