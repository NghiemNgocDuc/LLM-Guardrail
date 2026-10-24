# Web app screenshots

These images show the actual React app rendered locally in a 1440 × 1000
desktop viewport; sign-in uses a full-page capture. Workspace views use the
synthetic data in `tests/frontend/fixtures.ts`. Names, usage
figures, prompts, and identifiers are test data, not a live customer account.

## Overview

![Request overview with traffic and policy signals](images/dashboard.png)

## Sign-in and interactive introduction

The sign-in and Overview pages share an illustrative request journey. The
capture uses reduced motion so the full example is visible in a still image.

![Sign-in page with a friendly three-step guardrail example](images/sign-in.png)

## Skill Guard

![Skill Guard workspace with scanning and managed skill tools](images/skill-guard.png)

## Policies

![Workspace policy editor and guardrail controls](images/policy.png)

## Help and getting started

The help dialog and beginner guide are also captured in
`docs/images/page-help.png` and `docs/images/getting-started.png`.

![Contextual help explains the current page and suggests a next step](images/page-help.png)

![Getting started guide with a plain-language introduction and task links](images/getting-started.png)

## Refresh the images

From the repository root, install Node.js 22 and the frontend dependencies:

```bash
npm ci
npx playwright install chromium
npm run test:frontend -- tests/frontend/all-views.spec.ts tests/frontend/help.spec.ts tests/frontend/request-journey.spec.ts --project=desktop --workers=1
```

No API server or real credentials are needed. On Windows with Edge installed,
set `$env:PW_CHANNEL="msedge"` before running the tests.

After the tests pass, copy these generated files:

| Generated file | Committed image |
| --- | --- |
| `test-results/previews/dashboard-light-desktop.png` | `docs/images/dashboard.png` |
| `test-results/previews/sign-in-desktop.png` | `docs/images/sign-in.png` |
| `test-results/previews/skills-light-desktop.png` | `docs/images/skill-guard.png` |
| `test-results/previews/policy-light-desktop.png` | `docs/images/policy.png` |
| `test-results/previews/help-light-desktop.png` | `docs/images/page-help.png` |
| `test-results/previews/getting-started-desktop.png` | `docs/images/getting-started.png` |

Inspect every image before committing it. Use synthetic data and keep raw keys,
private email addresses, real prompts, and browser account details out of images.
