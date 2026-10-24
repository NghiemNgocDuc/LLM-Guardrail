# Frontend design

The interface uses a restrained forest-green and warm-white palette, DM Sans
for text, and IBM Plex Mono for prompts and request metadata. Shared colors,
surfaces, typography, and interaction states live in `src/styles/global.css`.
Each redesigned page has a scoped stylesheet.

Sign-in and Overview share a friendly, illustrated request journey: your message,
a quick check, and what happens next. Everyday questions, private details, and risky
instructions explain the product without requiring technical vocabulary.
`RequestJourney.tsx` owns the example and its scoped stylesheet. It makes no API
calls, and labels the outcomes as illustrative and dependent on workspace rules.
Overview keeps this introduction separate from actual activity and metrics.

The journey plays once, with a persistent pause/resume/replay button. Its short
sequence highlights the three stages while every explanation remains readable.
Reduced motion shows the complete static example immediately, including when
the system preference changes while the page is open. Scenario controls work
with a keyboard and retain focus. The sign-in form stays usable during playback
and comes first in both visual and keyboard order on phones.

The workspace has grouped navigation, URL-backed views, a keyboard-accessible
page-jump dialog, light/dark themes, and a mobile drawer. Route-level lazy
imports keep dashboard charts and secondary views out of the initial login
bundle. Dashboard and playground data comes from existing application APIs;
preview requests and browser test fixtures are explicitly illustrative.

The same components and tokens now cover every workspace view: security,
memory, observability, provenance, account, team, billing, administration, and
documentation. `src/components/ui.tsx` supplies labels, panels, tables, notices,
buttons, empty/loading states, and native modal dialogs. Dialogs keep keyboard
focus inside, return it on dismissal, and preserve their content while exiting.
Destructive actions use contextual confirmations; pending actions stay disabled.

Motion uses shared 120/220/320 ms durations and a consistent easing curve.
Page changes enter gently, metric groups appear in sequence, drawers move as a
single surface, and dialogs have coordinated backdrop/entry/exit motion.
Press feedback, theme icons, disclosure controls, result cards, and status
messages use brief transitions. Internal settings links scroll within the
workspace; changing a view resets scroll immediately. Reduced-motion users
receive immediate state changes and a complete static illustration.

Health displays actual endpoint checks, optional dependency configuration,
provider circuit states, and last-check times. It does not invent uptime history.
Billing displays the backend's one-time token packs and real purchase records.
Evidence metrics and downloadable reports remain in the documentation view,
with benchmark scope explicitly identified.

Design research:

- [Linear: a calmer interface](https://linear.app/now/behind-the-latest-design-refresh) informed navigation hierarchy and quieter supporting surfaces.
- [Vercel Geist typography](https://vercel.com/geist/typography) informed a consistent heading, body, and metadata scale.
- [W3C form labels](https://www.w3.org/WAI/tutorials/forms/labels/) informed associated labels and native form behavior.
- [Nielsen Norman Group: purposeful animation](https://www.nngroup.com/articles/animation-purpose-ux/) informed the request journey's explanation of cause and effect.
- [W3C clear content](https://www.w3.org/WAI/WCAG2/supplemental/objectives/o3-clear-content/) informed familiar words, short explanations, and the visual three-step introduction.
- [W3C pause, stop, hide](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide) informed playback controls and stable motion.
- [W3C animation preferences](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html) informed the complete static alternative and system preference support.
- [USWDS forms](https://designsystem.digital.gov/components/form/) and [Carbon empty states](https://www.carbondesignsystem.com/building-blocks/core/patterns/empty-states) informed clear recovery and useful first-use states.
- [Carbon motion](https://www.carbondesignsystem.com/building-blocks/foundations/motion/overview) and [choreography](https://www.carbondesignsystem.com/building-blocks/foundations/motion/choreography) informed shared timing and purposeful state transitions.
- [W3C modal dialogs](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) informed focus containment, Escape dismissal, and focus restoration.

Run `npm run typecheck`, `npm run build`, and `npm run test:frontend` after
changes. The browser tests cover desktop/mobile flows and run automated
accessibility checks on the redesigned surfaces; manual review remains useful
for keyboard ergonomics, readable copy, and visual quality.

The suite includes every authenticated view at 1440px and 375px in light and
dark themes, with WCAG-tagged axe checks and overflow assertions. Behavioral
tests cover scoped key creation/revocation, policy and Rego changes, skill
scan/upload/conflict review, account/security/password settings, pagination
and downloads, team membership, memory extraction and recall, live-feed
authentication/refetch, degraded health, and provenance evidence. All API
writes and payments in browser tests are synthetic, isolated fixtures.
