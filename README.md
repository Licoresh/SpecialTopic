# Philippine Job Skills Analysis

A private Streamlit research workspace and a public browser analyzer for Philippine data, analytics and AI job advertisements and the TESDA PSF-AAI.

## Public analyzer

The static public site is served from `public-web/site` on Vercel. A separate Streamlit edition is available at `public-web/streamlit_app.py` and uses the same public analysis engine.

Run the Streamlit public edition locally from the repository root:

```powershell
..\.venv\Scripts\python.exe -m streamlit run public-web/streamlit_app.py --server.address 127.0.0.1 --server.port 8502 --server.maxUploadSize 4
```

Open [the local public analyzer](http://127.0.0.1:8502). The Streamlit edition keeps no sidebar and does not require researcher login. Uploads and results remain in the app session and are not written to researcher tables or project files.

Select a CSV, confirm its editable column mapping, and explore Skills, Roles and locations, Qualifications, PSF-AAI demand, Alignment evidence, and Unmapped / emerging results. The dedicated PSF Mapping review page is not part of the public flow. The public engine uses only an explicitly released research classifier; analysis stays disabled until that artifact is available.

To add the Streamlit edition to Community Cloud, choose repository `Licoresh/SpecialTopic`, branch `main`, and main file path `public-web/streamlit_app.py`. Keep the repository root as the app root. Community Cloud syncs later code changes from GitHub automatically; see [Streamlit's deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).

For Vercel, connect `Licoresh/SpecialTopic` and set `main` as the production branch. Keep **Root Directory** at the repository root. The checked-in [Vercel config](vercel.json) selects **Other**, skips build and install, and serves only `public-web/site`. Remove the private workspace's Supabase environment variables from this Vercel project, then deploy a commit containing the static configuration. The private workspace still runs through Streamlit or Docker with its own configuration.

If the production URL returns `DEPLOYMENT_DISABLED`, check the project owner's Vercel dashboard for usage or plan issues, then redeploy the static revision. See [Vercel's troubleshooting steps](https://vercel.com/docs/errors/deployment_disabled).

### Release an evaluated classifier

Add `PUBLIC_MODEL_GITHUB_TOKEN` to the private workspace's `.env`. Use a fine-grained GitHub token scoped to `Licoresh/SpecialTopic` with **Contents: Read and write** and an account allowed to commit to `main` and deploy through the linked Vercel project.

In the private workspace, an administrator opens **Evaluate models → Public classifier release**, prepares the release, and inspects the exported vocabulary before confirming and publishing. The artifact contains the model parameters and vocabulary, which will be visible to public visitors. GitHub receives `public-web/site/model.json`. The Vercel Git integration deploys the commit and visitors see the released version in the analyzer.

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

### Windows refuses to run Python

If Windows shows **This app can't run on your PC** or **Access is denied** before Python starts, check `py --version` and `python --version` in a new terminal. If the base interpreter or launcher is also blocked, repair or reinstall Python using the architecture-matched full installer from [Python for Windows](https://www.python.org/downloads/windows/). Include pip and the PATH option. Python 3.13 is the version used for this project's local checks. A Git pull cannot repair a Windows Python installation.

After `python --version` works, create a new environment in the project folder rather than copying a teammate's environment or clearing the broken one:

```cmd
python -m venv .venv-clean
.venv-clean\Scripts\python.exe -m pip install -r requirements.txt
.venv-clean\Scripts\python.exe -m streamlit run app.py
```

Keep using `.venv-clean\Scripts\python.exe` for this repaired setup. If local AI suggestions are needed, install `requirements-suggestions.txt` with that same interpreter. Existing `.env`, research data and the original environment are preserved. If a fresh Python installation is still blocked, record the executable path and ask the device administrator to inspect the Windows application-control or security event; do not disable security software.

## Workflow

1. Upload the study job advertisements, confirm column mapping, and review source provenance and data quality.
2. Save the cleaned dataset and extract candidate skill phrases.
3. Review phrases and their advertisement context. Save categories and justified PSF-AAI competency links.
4. Train and evaluate the classifier after the reviewed labels pass validation.
5. Explore skills, roles, qualifications and PSF-AAI alignment. Export the selected study results and their metadata.

Skill charts group documented wording variants and count each advertisement once per grouped skill. Original wording remains available for review. Similarity scores are mapping aids, not proof of competency equivalence. Findings describe the selected advertisements.

The bundled PSF-AAI reference is in `data/reference/`. The in-app Methodology page uses [METHODOLOGY.md](METHODOLOGY.md).

## Team updates and data

Run `git pull origin main`, update the requirements in your existing environment, and restart Streamlit. Git delivers application code, the default reference and approved public classifier artifacts. Private model files, `.env`, raw uploads, reviewed labels and generated results stay outside Git.

With Supabase configured, signed-in teammates share saved processed data and annotations. The original upload stays on the uploader's device. Administrators can seed empty shared data slots through Settings. Database setup is defined in `supabase/migrations/`.

Internal project notes and design-reference images are local-only and excluded from Git and Docker build contexts.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use isolated synthetic fixtures. Their scores are not research findings.
