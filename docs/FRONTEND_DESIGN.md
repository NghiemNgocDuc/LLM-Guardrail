# Frontend design

The interface uses a restrained forest-green and warm-white palette, DM Sans
for text, and IBM Plex Mono for prompts and request metadata. Shared colors,
surfaces, typography, and interaction states live in `src/styles/global.css`
and `src/styles/theme.ts`. Each redesigned page has a scoped stylesheet.

The login page's illustrative preview reveals LLM output word by word. Users
can pause, replay, or switch between redaction and injection examples; reduced
motion shows the complete response immediately. The form stays usable while
the preview plays, and comes first in both visual and keyboard order on phones.

The workspace has grouped navigation, URL-backed views, a keyboard-accessible
page-jump dialog, light/dark themes, and a mobile drawer. Route-level lazy
imports keep dashboard charts and secondary views out of the initial login
bundle. Dashboard and playground data comes from existing application APIs;
preview requests and browser test fixtures are explicitly illustrative.

Design research:

- [Linear: a calmer interface](https://linear.app/now/behind-the-latest-design-refresh) informed navigation hierarchy and quieter supporting surfaces.
- [Vercel Geist typography](https://vercel.com/geist/typography) informed a consistent heading, body, and metadata scale.
- [W3C form labels](https://www.w3.org/WAI/tutorials/forms/labels/) informed associated labels and native form behavior.
- [W3C pause, stop, hide](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide) informed playback controls and stable motion.
- [USWDS forms](https://designsystem.digital.gov/components/form/) and [Carbon empty states](https://www.carbondesignsystem.com/building-blocks/core/patterns/empty-states) informed clear recovery and useful first-use states.

Run `npm run typecheck`, `npm run build`, and `npm run test:frontend` after
changes. The browser tests cover desktop/mobile flows and run automated
accessibility checks on the redesigned surfaces; manual review remains useful
for keyboard ergonomics, readable copy, and visual quality.
