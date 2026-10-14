# Private self-hosting on a free cloud VM

This profile runs the dashboard, gateway, guardrails, database, and model on
one VM. It uses no hosted AI API. It stores audit decisions and redacted
metadata while omitting raw blocked prompts and skill excerpts. The existing
Render deployment is not moved or changed by these instructions.

## What is realistically free

Oracle currently documents **2 Arm OCPUs and 12 GB RAM total** for its Always
Free A1 allocation, with 200 GB of combined boot/block storage. Choose an
Always Free eligible Ubuntu image in your tenancy's home region and stay
inside those allocations. Older 4-core/24-GB guides describe a different
allowance. Capacity can be unavailable, and idle VMs may be reclaimed after
seven days. [Oracle resource limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)

Oracle advertises no scheduled expiration for Always Free services under its
current terms, requires card verification, and provides no free-tier SLA.
Accounts left idle for 30 days can be suspended or terminated. This is a
zero-subscription-cost option within current limits, not a promise of free
hosting or uninterrupted availability forever. A health monitor does not
guarantee that an idle VM will be retained. [Oracle Free Tier FAQ](https://www.oracle.com/cloud/free/faq/)

CPU inference is suitable for light traffic. Start with `qwen3:1.7b`, a small
Apache-2.0 model, and measure response times on your actual VM. It is not a
replacement for a large model's quality or a guarantee of particular
latency. This profile uses one API worker, one inference request at a time,
a 2,048-token context, and disables Qwen thinking to limit CPU work.
[Official Qwen3 model](https://huggingface.co/Qwen/Qwen3-1.7B)

## Other cloud options

Google Cloud Run is a possible alternative for infrequent CPU inference that
scales to zero. Its request-based free allowance includes 180,000 vCPU-seconds
and 360,000 GB-seconds per month. Billing registration is required; compute,
storage, builds, and traffic can incur charges beyond applicable free limits.
It needs a separate deployment and persistent audit-storage design: this
Compose file targets a VM and cannot be deployed unchanged to Cloud Run.
[Google free tier](https://docs.cloud.google.com/free/docs/free-cloud-features)

Hugging Face currently requires a paid plan to create Docker/CPU compute
Spaces, despite CPU Basic having no hourly hardware charge. Eligible free
personal accounts can host two Gradio ZeroGPU demos, with five minutes of
GPU usage per day for free accounts. Shared queues, quotas, and ephemeral
local storage make this unsuitable for the private persistent VM stack.
[Spaces eligibility](https://huggingface.co/docs/hub/spaces-overview),
[ZeroGPU limits](https://huggingface.co/docs/hub/spaces-zerogpu),
[Storage lifecycle](https://huggingface.co/docs/hub/spaces-storage)

Cloudflare Workers AI includes a daily free inference allowance, but inference
runs through Cloudflare's hosted service. It is an alternative hosted AI
provider, rather than the self-hosted private model required by this profile.
[Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)

## Where data goes

```text
Browser -- HTTPS --> Caddy -- private Docker network --> API + guardrails
                                                   |--> PostgreSQL
                                                   |--> Redis
                                                   |--> OPA
                                                   `--> Ollama + local model

Separate setup container -- Internet --> model weights only
```

Only Caddy publishes ports 80 and 443. The API, PostgreSQL, Redis, OPA, and
Ollama connect solely to an `internal: true` Docker network. Caddy bridges
that network and a public network for HTTPS and certificate renewal; it
proxies a fixed API destination and has no database or app secrets. Docker's
internal network supplies runtime isolation from external connectivity.
[Docker networking](https://docs.docker.com/reference/compose-file/networks/)

The disposable `model-pull` setup service uses a separate network and shares
only the model volume. It cannot access the application database, Redis, or
application secrets. Model downloads and container builds need the Internet;
ordinary application and inference containers do not.

`PRIVATE_MODE=true` rejects hosted AI providers, remote fallbacks, arbitrary
model overrides, remote database/policy endpoints, Pinecone, hosted identity,
email, payments, and backend telemetry. The frontend is compiled with
`VITE_PRIVATE_MODE=true`; telemetry and remote font loading are disabled.
Private API policy also disables external callbacks and keeps chat history
in page memory rather than browser storage.

Ollama is pinned to `0.40.4`, runs with `OLLAMA_NO_CLOUD=1`, and has no published
port. Its `0.0.0.0:11434` binding is confined to the private Docker network.
Before sending a prompt, the adapter verifies that cloud features are disabled
and the configured model is downloaded locally. Verification failures stop
inference. [Ollama local-only mode](https://docs.ollama.com/faq),
[Pinned release](https://github.com/ollama/ollama/releases/tag/v0.40.4)

The hosting provider and VM administrators still control the infrastructure.
TLS protects traffic in transit; it does not conceal plaintext from the
machine that processes it. Local inference reduces disclosure to inference
vendors, but this deployment cannot promise that nobody can access data.
Protect the VM, account, secrets, and backups accordingly.

Deterministic secret, PII, injection, and skill checks remain the primary
blocking logic. The self-hosted model generates permitted chat responses;
changing inference providers does not turn an LLM into a perfect detector.
External agents must still honor gateway/skill decisions.

Private streaming holds model output until the complete output policy passes,
so the first visible text arrives after generation finishes. Blocked or
interrupted output is not released as partial tokens. Managed skill writes
also require flagged content, names, and descriptions to be redacted before
saving; approving a scan does not bypass this private storage rule.

If enabling private mode outside this Compose profile, isolate OPA networking
or disable its `http.send` capability: a custom Rego rule can otherwise initiate
its own network request. Validating the gateway's OPA URL alone cannot prevent
network access from inside the policy engine.

## Deploy a fresh installation

Prerequisites: an eligible Oracle account and VM, Docker Engine with Compose
v2, and a DNS hostname pointing to the VM. Use a hostname you control or a
free DNS provider's subdomain; a paid domain is optional. DNS availability
has its own provider limits. Open TCP 80/443 for Caddy and restrict SSH to
your administration IP. Do not expose ports 5432, 6379, 8181, 8000, or 11434.
Caddy obtains and renews a public HTTPS certificate when DNS and these ports
are correct. [Caddy HTTPS setup](https://caddyserver.com/docs/quick-starts/reverse-proxy)

Clone the repository on the VM and create the private configuration:

```bash
cp .env.private.example .env.private
chmod 600 .env.private
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Run the generator three times. Put a different generated value in each of
`SECRET_KEY`, `POSTGRES_PASSWORD`, and `REDIS_PASSWORD`. These hex values avoid
URL escaping issues. Set `PRIVATE_HOSTNAME` to the DNS hostname without a
scheme, path, or port. Leave `DEFAULT_MODEL=qwen3:1.7b` for the first deployment.
Never commit `.env.private`, copy production credentials into the example, or
paste the expanded Compose configuration into shared logs.

Use this standalone Compose file; do not combine it with the regular stack:

```bash
docker compose --env-file .env.private -f docker-compose.private.yml config --quiet
docker compose --env-file .env.private -f docker-compose.private.yml --profile setup run --rm model-pull
docker compose --env-file .env.private -f docker-compose.private.yml up -d --build
docker compose --env-file .env.private -f docker-compose.private.yml ps
```

The model download happens before startup. API startup runs Alembic migrations
against the new private database. Open `https://YOUR_HOSTNAME/` and check
`https://YOUR_HOSTNAME/health`. Health confirms that the application responds;
also submit a short permitted prompt to verify inference. Try a synthetic
blocked prompt and check that audit records contain no original content.
The source has automated private-mode tests, but this guide does not claim an
Oracle account was created, images were run, or a live deployment was tested.

Sign up with a strong password and sign in. A fresh signup is a member of its
initial workspace. Use the workspace picker to **create a new workspace**;
the creator becomes its administrator and can manage policies and skills.
Set model routing to **System default** or **Ollama** and leave the model blank
or set it to exactly `qwen3:1.7b`. Hosted provider/model selections fail in
private mode rather than falling back to an external service.

This profile uses local email/password authentication. No verification email
or emailed password-reset link is sent. Change your password from account
settings while signed in. An owner recovering a lost account must perform a
controlled offline reset or restore a trusted backup; do not enable a public
password-reset bypass. Token purchases are disabled; gateway billing is off,
while configured traffic limits still apply.

## Persistence and backups

The private Compose project uses separate named volumes for PostgreSQL, Redis,
model weights, and Caddy certificates. `docker compose down` retains them.
Do not use `down -v` unless you intend to erase the installation. Hosted API
keys and runtime prompts are not needed to download model weights.

Blocked audit content is omitted in private mode even if a policy requests
raw audit logging. Audit reasons and counts remain available. This does not
remove content you explicitly save as managed skill source, skill versions,
agent memory, or workspace policy: that application data remains in the local
database and requires the same access and backup protection as other user data.
Redacted audit details can still reveal operational metadata such as who used
a workspace and which rule triggered.

Keep periodic PostgreSQL backups encrypted and outside the VM; test restore
before depending on them. Free storage is finite, so choose retention limits
and include backup sizes in your cloud allowance. Docker service logs are
rotated by this profile, and Caddy request access logging is not enabled.
The optional `ENCRYPTION_KEY` setting elsewhere in the application now rejects
malformed Fernet keys during startup; this redacted-only profile leaves it
empty and does not retain raw blocked evidence.

No historical data is sanitized automatically. If importing an existing
database, inspect and remove or redact prior raw audit fields, skill rejection
excerpts, browser history, exported logs, and old backups before treating it
as a private installation. Existing intentionally saved skills and memory may
need a separate retention decision. Past data already sent to a hosted
provider cannot be recalled by changing this configuration.

## Updates and limits

Review dependency updates and cloud allowances regularly. Docker image pulls,
frontend builds, and model updates are explicit maintenance steps. To change
models, stop the runtime Ollama service, update `DEFAULT_MODEL`, run the setup
download, then restart/rebuild the stack. Stopping runtime inference avoids
two Ollama servers modifying the shared model directory simultaneously.
Keep the same model identifier in the downloaded model, API configuration,
and workspace policy.

Ordinary runtime has no Internet route, so external integrations and optional
uncached embedding downloads do not work. Enable a feature only after deciding
whether it fits the privacy requirements and evaluating its resource cost.
Do not rely on UptimeRobot pings to provide a hosting SLA or prevent Oracle
reclamation. Keep backups and a recovery plan for capacity shortages, account
issues, or an unavailable VM.
