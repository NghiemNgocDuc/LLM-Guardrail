# Web app screenshots

These images show the actual React dashboard rendered locally at 1440 × 1000
using the synthetic workspace in `tests/frontend/fixtures.ts`. Names, usage
figures, prompts, and identifiers are test data, not a live customer account.

## Overview

![Request overview with traffic and policy signals](images/dashboard.png)

## Skill Guard

![Skill Guard workspace with scanning and managed skill tools](images/skill-guard.png)

## Policies

![Workspace policy editor and guardrail controls](images/policy.png)

## Refresh the images

From the repository root, install Node.js 22 and the frontend dependencies:

```bash
npm ci
npx playwright install chromium
npm run test:frontend -- tests/frontend/all-views.spec.ts --project=desktop --workers=1
```

No API server or real credentials are needed. On Windows with Edge installed,
set `$env:PW_CHANNEL="msedge"` before running the tests.

After the tests pass, copy these generated files:

| Generated file | Committed image |
| --- | --- |
| `test-results/previews/dashboard-light-desktop.png` | `docs/images/dashboard.png` |
| `test-results/previews/skills-light-desktop.png` | `docs/images/skill-guard.png` |
| `test-results/previews/policy-light-desktop.png` | `docs/images/policy.png` |

Inspect every image before committing it. Use synthetic data and keep raw keys,
private email addresses, real prompts, and browser account details out of images.
