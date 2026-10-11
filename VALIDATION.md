# Validation record

## Automated software tests

The cleanup verification passed **121 tests in 34.38 seconds**. Tests use synthetic data only in temporary directories; these test metrics are not research results. Coverage includes CSV/XLSX loading, editable automatic column mapping, job cleaning, NLP, extraction, manual labeling, both TF-IDF classifiers, stratified evaluation, model persistence, PSF mapping, employer alignment, demand denominators, emerging/unmapped outputs, exports, and Streamlit pages. A dedicated source-reader check verifies the bundled official PDF parser.

## Official framework source

The official TESDA PDF was downloaded from its clean HTTPS URL with tracking parameters removed and saved at `data/reference/psf_aai_official.pdf`. It has 315 viewer pages. Three representative pages (FSC, ESC and a multi-column proficiency table) were rendered and visually inspected. The parser extracted 78 FSC and 16 ESC definition blocks, official competency codes, descriptions, 1-based PDF viewer page numbers, source URL and SHA-256. It also extracted 1,029 literal career-map competency links across 28 roles. The test checks these counts, IDs, pages and hashes. Aliases are not synthesized. Extracted records remain a draft until a researcher verifies and activates them.

## Application and data integrity

All 16 configured Streamlit pages passed AppTest in the prior run, and the full test suite still passes after cleanup. The existing posting CSV matches its recorded SHA-256. `train/labeled_competencies.csv` has zero reviewed rows, and no fitted research pipeline or research metrics are present. Two isolated prototype model binaries and temporary PDF page images remain in ignored local folders because automatic approval review blocked their deletion; the application does not load or display them.
