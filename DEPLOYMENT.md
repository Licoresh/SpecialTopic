# Deploy the shared research workspace

The repository contains a Streamlit app, Supabase-backed shared records, a Docker setup for a persistent server, and a Vercel container entry point. Keep Supabase credentials in the host's private environment settings. Use only `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`; this app must never receive a Supabase secret/service-role key.

## Before deployment

For an existing workspace upgrading to **2.0.19**, apply the new `supabase/migrations/20261018090000_occurrence_psf_mappings.sql` once before updating the application. It adds occurrence-specific, many-to-many PSF reviews, authenticated reviewer writes, optimistic version checks and audit history. The original annotation tables are retained. This migration needs verification in a Supabase staging environment; local Python tests do not exercise database permissions or SQL execution.

1. In Supabase, apply the files in `supabase/migrations` in filename order if the project has not already been set up. Do not rerun migrations that have already been applied.
2. Create one Auth account per team member and disable public sign-ups. In the Supabase SQL Editor, grant the coordinator and reviewers explicitly, substituting each account's exact email:

   ```sql
   insert into public.research_members(user_id, role)
   select id, 'admin' from auth.users where email = 'coordinator@example.org'
   on conflict (user_id) do update set role = 'admin', active = true;

   insert into public.research_members(user_id, role)
   select id, 'reviewer' from auth.users where email = 'reviewer@example.org'
   on conflict (user_id) do update set role = 'reviewer', active = true;
   ```

   Repeat the reviewer statement for every reviewer account. Auth accounts without an active membership cannot enter the workspace.
3. Back up the research files on the current computer. Git deliberately excludes `.env`, `.streamlit/secrets.toml`, uploaded/processed datasets, model files, and outputs.
4. Rotate the Supabase secret/service-role key previously shared in chat. It is not needed by this app.

## Run with Docker Compose on your computer

1. Install and start Docker Desktop for Windows.
2. Clone `https://github.com/Licoresh/SpecialTopic.git`, open PowerShell in the cloned repository folder, and copy the example environment file:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

3. In `.env`, replace `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` with the values from Supabase Project Settings → API. Keep the publishable key only; do not paste the secret/service-role key.
4. Build and start the app:

   ```powershell
   docker compose up --build -d
   ```

5. Open `http://localhost:8501` and sign in using an account already granted access in `research_members`.
6. Check status or logs with `docker compose ps` and `docker compose logs -f research`. Stop the services with `docker compose down`. The `data`, `train`, `models`, and `outputs` folders remain on disk because Compose mounts them from the project directory.

The computer-only setup binds the Streamlit port to localhost. To share with teammates, use a server with a public IP, point a DNS name to it, allow inbound ports 80 and 443, put that domain in `APP_DOMAIN` in `.env`, then start the HTTPS proxy profile:

```powershell
docker compose --profile public up --build -d
```

Caddy obtains and renews HTTPS certificates automatically when the DNS record points to the server and ports 80/443 are reachable. Teammates then use `https://your-domain.example`. Back up the mounted research folders and Supabase database regularly. Do not expose port 8501 directly to the public internet.

For a plain Docker image instead of Compose, build and run it from the repository root:

```powershell
docker build -t future-of-work .
docker run --rm -p 8501:8501 --env-file .env -v "${PWD}/data:/app/data" -v "${PWD}/train:/app/train" -v "${PWD}/models:/app/models" -v "${PWD}/outputs:/app/outputs" future-of-work
```

Docker's bind-mounted directories persist files on the host. The Docker image intentionally excludes local data, models, outputs, tests, and secrets.

## Deploy from GitHub to Vercel

Vercel currently supports Dockerfile-based container deployments. This repo includes `Dockerfile.vercel`, which starts Streamlit on Vercel's `$PORT`, and `vercel.json` pins the Container framework preset so Vercel does not misread `app.py` as a Python Function. The Vercel container documentation describes WebSocket support as a beta feature; confirm it is enabled for your account and test login, navigation, uploads, and saves in a preview deployment before inviting reviewers.

1. Push the repository to GitHub and sign in to Vercel with the GitHub account that can access it.
2. In Vercel, choose **Add New → Project**, import `Licoresh/SpecialTopic`, set **Root Directory** to the repository root (the folder containing `app.py`, `Dockerfile.vercel`, and `vercel.json`). The checked-in `vercel.json` selects the Container framework preset. If Vercel has already selected Python, change it under **Project Settings → Build and Deployment → Framework Preset** to **Container**. The Python preset treats `app.py` as a serverless function and produces “Found app.py but it does not export a top-level app/application/handler” because this project runs Streamlit from the container.
3. Leave Python function/build commands and output-directory overrides empty. The root `Dockerfile.vercel` starts Streamlit and listens on Vercel's `PORT`.
4. In the project settings, add `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` under **Environment Variables** for Preview and Production. Do not add `SUPABASE_SECRET_KEY`, passwords, or any `.env` file.
5. Redeploy the latest commit from `main`. Check the build and runtime logs, test two individual accounts on separate devices, and verify that an annotation saved on one device appears on the other after refresh.
6. Promote the tested deployment to Production and add a Vercel domain. For later updates, push to the connected branch; Vercel builds a new deployment from that commit.

Vercel containers scale as stateless function instances; files written inside a container are not durable across instance replacement and instances may not share a local filesystem. Supabase stores shared workspace records, but local model artifacts, raw file backups, and generated downloads may be temporary. This makes Vercel useful for a limited web preview, but the persistent Docker server above is the recommended home for the full research workflow, especially large uploads and model training. Do not treat a Vercel deployment as the only copy of research files. If Vercel reports a WebSocket, upload-size, timeout, or memory error, use the persistent Docker host instead.

The Vercel Docker image installs the CPU-only PyTorch wheel and Sentence Transformers in separate layers to avoid an oversized image upload. Vercel Container Registry allows compressed layers up to 500 MB and images up to 15 GB. If Vercel still reports a 413 upload error, the optional model runtime should be removed from `Dockerfile.vercel` and run on a persistent Docker host; `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` addresses function bundle limits, not registry layer uploads. BGE-M3 weights are separate (about 2.3 GB) and download when suggestions first run. Vercel documents a 2 GB maximum function memory on Hobby and 4 GB on Pro/Enterprise; the BGE-M3 model may exceed Hobby memory, and each temporary instance can need its own model download. The package being installed does not guarantee that BGE-M3 inference will fit the selected Vercel plan. Use the persistent Docker deployment for reliable local-model suggestions.

## Research use checks

After hosting, confirm that two authorized users can sign in, a reviewer can save and retrieve an annotation, an unauthorized account is denied, and the administrator can open model training. Keep backups outside the server. Verify all sources, labels, mappings, and analysis outputs before reporting findings. Software tests do not certify the dataset or research conclusions; see `METHODOLOGY.md` and `VALIDATION.md`.

References: [Streamlit Docker deployment](https://docs.streamlit.io/deploy/tutorials/docker), [Vercel Docker container deployments](https://vercel.com/kb/guide/does-vercel-support-docker-deployments), [Vercel WebSocket limits and support](https://vercel.com/docs/limits), and [Supabase session security](https://supabase.com/docs/guides/auth/sessions).
