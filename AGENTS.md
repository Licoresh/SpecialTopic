# Project instructions

## Versioning

- Increment the patch version in `src/config.py` for every completed code or UI update, even before committing.
- Use the highest existing working-tree or HEAD version as the baseline; never decrease or reuse a released version.
- Every new commit must carry a version newer than its parent. If the update already bumped it, do not bump it twice just to commit.
- Report the resulting version with the completed update.

## Interface consistency

- Reuse the shared theme and `src/design.py` for every page, including sign-in and error states.
- Keep a consistent type scale, 44 px controls, shared spacing tokens, card padding and alignment at desktop and mobile widths.
- Use one visible card layer per section. Avoid nested bordered containers and redundant layout wrappers.
- Use Material Symbols and the shared semantic theme palette; keep the same icon and color for the same action or status across pages.
- Keep decorative graphics separate from real research charts; never invent KPI values or sparklines.
