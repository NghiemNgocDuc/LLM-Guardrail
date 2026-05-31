# Deploying to Render with Supabase and Upstash

This project can be deployed to Render (web services) with Supabase Postgres and Upstash Redis for production state.

Steps

1. Create Supabase project
   - Create a Supabase project and database.
   - Copy the Postgres connection string (postgresql://...) and set it as `DATABASE_URL`.

2. Create Upstash Redis
   - Create a Redis database in Upstash and copy the connection URL.
   - Set as `RATE_LIMIT_REDIS_URL`.

3. Create Render services
   - Connect your GitHub repo to Render.
   - Render will recognize `render.yaml` and propose creating two services:
     - `llm-guardrail-api` (uses `Dockerfile`)
     - `llm-guardrail-web` (uses `Dockerfile.frontend`)

4. Set environment variables in Render
   - For the API service, set these env vars (as secrets):
     - `DATABASE_URL` (Supabase connection)
     - `RATE_LIMIT_REDIS_URL` (Upstash URL)
     - `SECRET_KEY` (strong secret)
     - Any provider API keys (e.g., `GROQ_API_KEY`, `OPENAI_API_KEY`)

5. Configure GitHub Actions
   - In your GitHub repository, add secrets:
     - `RENDER_API_KEY` — render service API key (optional, for trigger deploys)
     - `RENDER_SERVICE_ID` — the Render API service ID for the API service (optional)

6. Push to `main` to trigger CI
   - The workflow `.github/workflows/deploy-to-render.yml` builds the API Docker image and triggers a Render deploy via API.

Notes

- The CI uses GitHub Container Registry (GHCR) to push images; you can change to Docker Hub or skip pushing if Render builds from repo directly.
- For automatic database provisioning you can use Supabase CLI / Terraform; this guide assumes manual creation.
- Ensure you do not commit any production secrets to the repository.
