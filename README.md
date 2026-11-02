# Philippine Job Skills Analysis

A Streamlit application for analyzing Philippine data, analytics and AI job advertisements and comparing employer requirements with the TESDA PSF-AAI.

## Local setup

Use Python 3.11 or later. From the project folder on Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` in `.env` to use your team's shared workspace. Each researcher needs their own account and active team membership. Never commit credentials or use a service-role key in the app.

Start the application:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open http://127.0.0.1:8501. Existing installations can continue using their current virtual environment.

For optional local BGE-M3 suggestions, install `requirements-suggestions.txt` in the same environment. Model files download on first use. Suggestions remain drafts until a researcher reviews and saves a label.

## Workflow

1. Upload the study job advertisements, confirm column mapping, and review source provenance and data quality.
2. Save the cleaned dataset and extract candidate skill phrases.
3. Review phrases and their advertisement context. Save categories and justified PSF-AAI competency links.
4. Train and evaluate the classifier after the reviewed labels pass validation.
5. Explore skills, roles, qualifications and PSF-AAI alignment. Export the selected study results and their metadata.

Skill charts group documented wording variants and count each advertisement once per grouped skill. Original wording remains available for review. Similarity scores are mapping aids, not proof of competency equivalence. Findings describe the selected advertisements.

The bundled PSF-AAI reference is in `data/reference/`. The in-app Methodology page uses [METHODOLOGY.md](METHODOLOGY.md).

## Team updates and data

Run `git pull origin main`, update the requirements in your existing environment, and restart Streamlit. Git delivers application code and the default reference; it does not deliver `.env`, raw uploads, reviewed labels, model files or generated results.

With Supabase configured, signed-in teammates share saved processed data and annotations. The original upload stays on the uploader's device. Administrators can seed empty shared data slots through Settings. Database setup is defined in `supabase/migrations/`.

Internal project notes and design-reference images are local-only and excluded from Git and Docker build contexts.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use isolated synthetic fixtures. Their scores are not research findings.
