# Cloud Run deployment review

Reviewed 2026-10-15. This is a deployment proposal, not a deployed service or
a guarantee of a zero bill. The existing private VM deployment remains in
[PRIVATE_SELF_HOSTING.md](PRIVATE_SELF_HOSTING.md).

## Recommended layout to evaluate

```text
Browser -- HTTPS --> Cloud Run gateway + dashboard
                            |--> local Ollama sidecar, cloud features disabled
                            |--> local OPA sidecar
                            |--> existing durable PostgreSQL database
                            `--> durable shared rate-limit store
```

Keep the model beside the gateway. Only the gateway should receive ingress;
Ollama and OPA should communicate through loopback. Authenticate application
requests and preserve the existing private audit and streaming guarantees.
Cloud Run supports sidecars, but does not reproduce Docker Compose's isolated
internal network. Network isolation must be designed explicitly.
[Container contract](https://docs.cloud.google.com/run/docs/container-contract)

The project owner has confirmed a billing-enabled project. Its project ID,
region, existing database service, and available deployment access are still
needed. No cloud resources, service accounts, or billing settings have been
created or changed.

## Storage is the main constraint

Cloud Run's writable local filesystem uses instance memory and disappears
when that instance stops. PostgreSQL or SQLite stored there would lose data.
Redis in a local sidecar would also lose its counters when the instance is
replaced and would not coordinate multiple instances.
[Filesystem lifecycle](https://docs.cloud.google.com/run/docs/container-contract#file_system_access)

A Cloud Storage bucket mount is not a database disk: Cloud Storage FUSE lacks
file locking and full POSIX semantics. Do not place a live PostgreSQL or SQLite
database on that mount.
[Volume limitations](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts#limitations)

Prefer evaluating the app's existing PostgreSQL service before provisioning
anything new. Cloud SQL has ongoing instance and storage charges; its trial
does not provide permanent free PostgreSQL hosting.
[Cloud SQL pricing](https://cloud.google.com/sql/pricing),
[Google free offers](https://docs.cloud.google.com/free/docs/free-cloud-features)

An external database would receive account data, saved skills and memories,
and redacted audit metadata. Omitting blocked evidence does not make those
other application records anonymous. Access, region, retention, backups, and
transport security need to match the owner's requirements.

## Changes required before deployment

The current private profile deliberately accepts only local database and
Redis endpoints. It will reject an external database rather than quietly
weaken the boundary. A Cloud Run deployment needs an explicit configuration
for the selected storage services while keeping inference local and cloud
model fallbacks disabled.
Reduce the database connection pool to the selected provider's allowance.

Keep PostgreSQL as the source of truth for users, policies, exact skill
approvals, revisions, and audits. Do not replace that transactional model with
Firestore simply to obtain a different free allowance. Select a shared
rate-limit store whose persistence and connection method are supported.
Daily token-spend and deduplication counters also currently use process memory;
authoritative limits must survive instance replacement. One maximum instance
does not prevent resets during cold starts or revision changes.

Run database migrations as a controlled deployment step. The current
entrypoint runs migrations on every API startup; cold starts and revision
overlap require a migration strategy that avoids concurrent upgrades.
Verify sidecar readiness before serving inference, and test slow CPU inference
and private streaming on the actual allocation.
Package model weights in a versioned image or read-only model mount rather
than relying on the VM profile's persistent model volume. Prefer stateless
MCP POST initially because current SSE session state is instance-local.

## Free allowance and cost controls

For request-based Cloud Run billing, Google's current monthly free allowance
includes 180,000 vCPU-seconds and 360,000 GB-seconds. An illustrative total
allocation of 2 vCPU and 4 GB would consume both allowances after approximately
25 billable hours. This arithmetic is not a tested sizing recommendation;
other usage on the billing account also consumes allowances.
[Free-tier limits](https://docs.cloud.google.com/free/docs/free-cloud-features)

Start with request-based billing, minimum instances zero, restricted
concurrency, and a small maximum instance count. Startup and shutdown also
count toward billed usage. Builds, image/model storage, networking, database,
and rate-limit storage must be estimated separately.
[Billing settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings)

Alerts-only budgets notify rather than stop usage. Cloud Run now also supports
spend-cap budgets, which can pause workloads. These use gross estimated costs,
exclude credits, and do not enforce instantly; in-flight overages and costs
from other services can still be billed. Review the actual project-wide cost
estimate before setting a cap or deploying.
[Spend-cap behavior and limitations](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)

## Information needed to make this deployable

- Google Cloud project ID and preferred region.
- Existing PostgreSQL and rate-limit service names, if any.
- Deployment access through the owner's authenticated account.
- Whether reusing those services meets the privacy and cost requirements.

Share service names and project IDs only; keep passwords, tokens, and service
account keys out of chat and repository files. Once the storage choice is
known, prepare the concrete service configuration and cost estimate before
creating resources or moving live traffic.
