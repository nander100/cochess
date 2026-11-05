# CoChess design tokens

Source: the owner's Claude Design canvas "CoChess UI" (navy, baby blue, black and white). The original screen files are in `docs/design/source/`. Every value below is taken from those files except where marked **(proposed)**: those are needed by the spec but don't appear in the design, and the owner approves them at the v3 M1 checkpoint.

Implement these as CSS custom properties (e.g. `--color-bg`, `--space-4`) defined once. Components use the tokens, never raw values.

## Brand palette

| Name | Hex | Used for |
|---|---|---|
| Black | `#0A0A0A` | Header, light-mode text, dark-mode background, black pieces |
| White | `#FFFFFF` | Light-mode background, dark-mode text, white pieces |
| Navy | `#0B2F8F` | Light-mode primary buttons, links, labels; dark-mode feature cards |
| Navy hover | `#1846C7` | Link hover; current-move marker on the eval graph |
| Baby blue | `#A9D6F5` | Accent: logo tile, active nav item, dark-mode primary, "Analyzed" pill, coach avatar, dark board squares |
| Baby blue 2 | `#8EC3EC` | Light-mode input borders, eval-graph midline |
| Pale blue | `#CFE8FB` | Alternative board square color |
| Header text 2 | `#CFE6F8` | Secondary text in the header (player name) |
| Header control border | `#2F3A48` | Border of the theme toggle in the header |

## Theme colors

| Token | Light | Dark | Role |
|---|---|---|---|
| `bg` | `#FFFFFF` | `#0A0A0A` | Page background |
| `fg` | `#0A0A0A` | `#FFFFFF` | Main text |
| `muted` | `#3F4652` | `#B8C2CE` | Secondary text |
| `border` | `#D5E3F0` | `#26303D` | Card and control borders |
| `row-border` | `#E6EEF6` | `#1C2430` | Table row dividers |
| `tint` | `#EAF4FD` | `#0E1A2E` | Tinted panels (upload form, chat panel, table header) |
| `tint-border` | `#A9D6F5` | `#1E3A5F` | Border of tinted panels |
| `field` | `#FFFFFF` | `#111821` | Input and outline-button background |
| `field-border` | `#8EC3EC` | `#2F4A6B` | Input borders |
| `feature` | `#0A0A0A` | `#0B2F8F` | Feature cards (coach summary, top tendency, coach feedback) |
| `feature-muted` | `#E3E8EE` | `#D6E4F5` | Body text on feature cards |
| `primary` | `#0B2F8F` | `#A9D6F5` | Primary buttons, current step, user chat bubbles |
| `primary-fg` | `#FFFFFF` | `#0A0A0A` | Text on primary |
| `secondary-bg` | `#0A0A0A` | `#FFFFFF` | Secondary buttons ("Send", "Show the answer") |
| `secondary-fg` | `#FFFFFF` | `#0A0A0A` | Text on secondary |
| `link` | `#0B2F8F` | `#A9D6F5` | Links |
| `label` | `#0B2F8F` | `#A9D6F5` | Eyebrow labels ("YOUR GAMES", "Hint") |
| `track` | `#EAF4FD` | `#1C2430` | Progress-bar and tendency-bar tracks |
| `done-bg` | `#0A0A0A` | `#1C2430` | Completed step chips |
| `eval-border` | `#0A0A0A` | `#5B6676` | Eval bar outline |

The header is the same in both themes: background `#0A0A0A`, text `#FFFFFF`.

Note: the Games screen uses `#D6DCE4` for light-mode `feature-muted`, while the other screens use `#E3E8EE`. Use `#E3E8EE`.

**Default theme: light** (the design's default). Dark and "match system" are options.

## Chess-meaning colors (proposed)

The design doesn't define these, but the move list, eval graph, arrows, and dashboard need them. Each passes WCAG AA as text on its theme's background, and each is always shown with a glyph or label, never color alone.

| Meaning | Glyph | Light | Dark |
|---|---|---|---|
| Best / good | ✓ | `#1B7F4B` | `#5FD39A` |
| Inaccuracy | `?!` | `#8A6100` | `#F2C94C` |
| Mistake | `?` | `#B54708` | `#F79009` |
| Blunder | `??` | `#B42318` | `#F97066` |
| Plan / idea | — | `#0B2F8F` (navy) | `#A9D6F5` (baby blue) |

Coach arrows (SPEC_V3 §6) use these: green = best/good, yellow = inaccuracy, red = mistake/blunder/threat, blue = plan.

## Board

| Token | Value |
|---|---|
| Light square | `#FFFFFF` (options: `#EAF4FD`, `#CFE8FB`) |
| Dark square | `#A9D6F5` (options: `#8EC3EC`, `#CFE8FB`) |
| Last-move highlight | `#CFE3FA` on light squares, `#6FAEE0` on dark squares |
| Coordinates | `#0B2F8F` on light squares, `#0A0A0A` on dark squares; bold, about 2% of board width |
| Frame | 2px solid `#0A0A0A`, radius 10px |
| Max board size | 600px |

The square-color options are the three "board color schemes" for Settings (SPEC_V3 §4.3). The design draws pieces with Unicode glyphs as a stand-in; the app uses chessground's piece set.

**Eval bar:** 22px wide, radius 6px, black for Black's share on top, white for White's share below, value in 10px bold at the bottom.

**Eval graph:** 120px tall, radius 6px, black fill for Black and white fill for White's win chance, a dashed `#8EC3EC` midline, a 3px `#1846C7` line at the current move, and a baby blue dot (black 2px outline, radius 6) at the selected point.

## Typography

Fonts (Google Fonts): **Space Grotesk** (500, 700) for headings, **Inter** (400, 500, 600) for everything else, `ui-monospace, Menlo, monospace` for PGN text.

| Style | Font | Size / line height | Weight | Letter spacing |
|---|---|---|---|---|
| Display (page hero) | Space Grotesk | 44px / 1.05 | 700 | -0.02em |
| Page title | Space Grotesk | 34px / 1.1 (moment), 30px (analysis) | 700 | -0.01em |
| Section heading | Space Grotesk | 22px | 700 | — |
| Card value | Space Grotesk | 22px | 700 | — |
| Panel heading | Space Grotesk | 18px | 700 | — |
| Logo wordmark | Space Grotesk | 20px | 700 | -0.01em |
| Lead text | Inter | 17px / 1.55 | 400 | — |
| Body | Inter | 15–16px / 1.6 | 400 | — |
| UI text, table, chat | Inter | 14px / 1.5 | 400–600 | — |
| Small heading | Inter | 15px | 600 | — |
| Eyebrow label | Inter | 13px | 600, uppercase | 0.08em |
| Pill | Inter | 12px | 600 | — |
| PGN input | Monospace | 13px | 400 | — |

Numbers in tables and accuracy use `font-variant-numeric: tabular-nums`.

## Spacing

The design uses 4, 6, 8, 10, 12, 14, 16, 20, 22, 24, 28, 32, 40, 56, and 64px. Normalize to this scale:

`4, 8, 12, 16, 20, 24, 32, 40, 56, 64`

- Page content: max width 1240px (1200px on the Games page), 24px side padding, 28–40px top padding.
- Gap between page sections: 20–32px.
- Card padding: 16–24px.
- Gap between the board column and the side panel: 24–28px. Board column flex basis 520px, side panel 380px.

## Radii

| Use | Radius |
|---|---|
| Nav item, logo tile, move-list button | 8px |
| Buttons, inputs, board | 10px |
| Small boxes (tries counter) | 12px |
| Cards, chat bubbles, tables | 14px |
| Large panels and forms | 16px |
| Pills and step chips | 999px |
| Chat bubble tail | User: 14 14 4 14. Coach: 14 14 14 4 |

## Elevation

Flat: no shadows anywhere. Separation comes from borders, tints, and the dark feature cards.

## Controls

- Height 44px for every button, input, and select (touch-friendly). Icon buttons are 44×44.
- **Primary button:** `primary` background, `primary-fg` text, no border, radius 10, 600 weight, 14–15px, 18–22px horizontal padding.
- **Secondary button:** `secondary-bg` / `secondary-fg`, no border.
- **Outline button:** `field` background, 1px `field-border` (or `border`), `fg` text.
- **Disabled:** keep the shape; reduce contrast and set `aria-disabled`.
- **Inputs:** `field` background, 1px `field-border`, radius 10, 12px horizontal padding, 14px text.
- **Icons:** inline stroke SVG, 18–20px, 2px stroke, round caps and joins. No emoji.

## Components

- **Header:** black bar, max width matching the page. Logo tile (34px, radius 8, baby blue, black knight) plus "CoChess" wordmark; nav links with the active one as a baby blue pill with black text; player name in `#CFE6F8`; theme toggle (44px icon button, sun/moon icon in baby blue).
- **Feature card:** `feature` background, white heading, `feature-muted` body, baby blue label or coach avatar.
- **Coach avatar:** 28–30px baby blue circle with a black bold "C".
- **Tinted panel:** `tint` background with a 1px `tint-border`. Used for the upload form, the chat panel, and table headers.
- **Status pill:** "Analyzed" is baby blue with black text; "Analyzing…" uses `secondary-bg` / `secondary-fg`.
- **Step chips (moments):** done = `done-bg` with a baby blue check icon; current = `primary`; upcoming = outline with `muted` text.
- **Chat bubbles:** user bubble right-aligned in `primary`; coach bubble left-aligned in `field` with a `tint-border` outline.
- **Tables:** inside a bordered 14px-radius box that scrolls sideways if needed; header row in `tint`; 12–14px × 16px cell padding.
- **Progress bar and tendency bars:** `track` background with a filled bar.
- **Color swatch:** 12px square, radius 3, outlined, shown next to "White" or "Black".
