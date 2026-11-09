# PSF-AAI reference audit — 2026-11-09

Source: bundled official TESDA PSF-AAI PDF. Page numbers below are physical PDF pages (printed page numbers are two lower).

Source SHA-256: a6edcb3a76585ebfd571013079a5124cc50fe7e93fc75875a40af862e633be9a

## Coverage

- All 94 official competency definition headings and all 31 role competency cards.
- All six occupational families; Adaptability is represented in each family. Its overview entries occur on PDF pages 21, 24, 27, 30, 33 and 36.
- Independent row-level regression audit of each role table; wrapped competency names remain supported.
- All 31 role descriptions retained with source pages and family membership.

## Corrections

Added 28 missing competency–role links caused by Self-Management / Self Management and Computational Modelling / Computational Modeling variants.
Removed 15 incorrect Performance Management suffix matches inside People and Performance Management. No official competency definition was added or removed.

Actionable business insights occurs in the Research Manager description on PDF page 96; its official skills are on page 97. It is searchable role context, not a separate competency or a training alias.

| Change | Official competency | Role | Skills PDF page |
|---|---|---|---|
| Added | Computational Modeling | AI Engineer | 83 |
| Added | Computational Modeling | Chief AI Engineer | 88 |
| Added | Computational Modeling | Chief Data Scientist | 78 |
| Added | Computational Modeling | Data Scientist | 74 |
| Added | Computational Modeling | Machine Learning Engineer | 72 |
| Added | Computational Modeling | Senior AI Engineer | 85 |
| Added | Computational Modeling | Senior Data Scientist | 76 |
| Added | Self Management | AI Engineer | 83 |
| Added | Self Management | Chief AI Engineer | 88 |
| Added | Self Management | Chief Analytics Officer | 80 |
| Added | Self Management | Chief Data Architect | 68 |
| Added | Self Management | Chief Data Officer | 58 |
| Added | Self Management | Chief Data Scientist | 78 |
| Added | Self Management | Chief Information Officer | 70 |
| Added | Self Management | Chief Scientific Officer | 101 |
| Added | Self Management | Chief Technology Officer | 91 |
| Added | Self Management | Chief [Business Function] Officer | 48 |
| Added | Self Management | Data Architect | 66 |
| Added | Self Management | Data Governance Manager | 52 |
| Added | Self Management | Data Governance Officer | 55 |
| Added | Self Management | Data Quality Specialist | 50 |
| Added | Self Management | Data Scientist | 74 |
| Added | Self Management | Director of Research | 99 |
| Added | Self Management | Research Manager | 97 |
| Added | Self Management | Senior AI Engineer | 85 |
| Added | Self Management | Senior Applied Data/AI Researcher | 95 |
| Added | Self Management | Senior Data Engineer | 64 |
| Added | Self Management | Senior Data Scientist | 76 |
| Removed | Performance Management | Business Analytics Director | 46 |
| Removed | Performance Management | Chief Data Architect | 68 |
| Removed | Performance Management | Chief Scientific Officer | 101 |
| Removed | Performance Management | Data Architect | 66 |
| Removed | Performance Management | Data Governance Manager | 52 |
| Removed | Performance Management | Data Governance Officer | 55 |
| Removed | Performance Management | Data Quality Specialist | 50 |
| Removed | Performance Management | Data Scientist | 74 |
| Removed | Performance Management | Director of Research | 99 |
| Removed | Performance Management | Research Manager | 97 |
| Removed | Performance Management | Senior AI Engineer | 85 |
| Removed | Performance Management | Senior Applied Data/AI Researcher | 95 |
| Removed | Performance Management | Senior Business Intelligence Analyst | 42 |
| Removed | Performance Management | Senior Data Engineer | 64 |
| Removed | Performance Management | Senior Data Scientist | 76 |

## Verification

18 source, manual-review and end-to-end tests passed; a second focused mapping/review run passed 25 tests. Same-source saved reference rows receive corrected official role links while preserving non-framework custom roles.

The original 500-row dataset yields 489 cleaned ads, 253 distinct chart skills, 42,675 distinct withheld phrases and 31 reference roles. Public and researcher paths agree on all 31 chart/result-data sections. The release changes PSF role associations; the top-level skill count need not change.

Rebuild with scripts/refresh_psf_reference.py followed by scripts/build_public_reference.py. A release revision change invalidates automatic-result caches in both workspaces. Saved manual mapping reviews remain subject to reference-hash freshness checks.
