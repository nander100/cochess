# CoChess design: screens

Source: the owner's Claude Design canvas "CoChess UI". Each screen's original file is in `docs/design/source/` and holds the exact layout and inline styles. These files are design references, not app code: they render only inside Claude Design, and their boards use Unicode pieces as stand-ins for chessground. Rebuild them as React components using the tokens in `tokens.md`.

**Where the design and the spec disagree, the spec wins.** Each conflict is listed below so the owner can confirm at the M0 checkpoint.

## Screen map

| Design file | Design title | App page (route) |
|---|---|---|
| `Main.dc.html` | Games | Games page; basis for the v3 dashboard (see below) |
| `Analysis.dc.html` | Game analysis + coach | Analysis board (`/games/:id`) |
| `Moment.dc.html` | Critical moment exercise | Critical-moment stepper |
| `Onboarding.dc.html` | Onboarding: 12-game assessment | Onboarding |
| `Profile.dc.html` | Profile | Profile (and appearance settings) |
| `Redeem.dc.html` | Redeem invite | Invite redemption |

All pages share the black header with nav: Games, Analysis, Critical moments, Assessment, Profile.

## Main.dc.html — Games

1. **Hero row:** eyebrow "YOUR GAMES", display headline "Upload a game. Learn one idea from it.", a lead paragraph; beside it, a tinted upload form (PGN textarea, color choice, "Analyze game" primary button).
2. **"What keeps coming up":** three cards in a responsive grid. The first is a feature card (top tendency); then the second tendency; then "Moments to practice" with a "Start practicing →" link.
3. **Recent games:** heading, a time-control filter, and a table: Opponent, Color (with swatch), Result, Time control, Accuracy, Status pill, Open link.

## Analysis.dc.html — Game analysis

1. Title row: "You vs [Opponent]", meta (color · time control · result), accuracy pill.
2. **Left column (board):** eval bar beside the board; navigation buttons (first, previous, next as primary, last, "Flip board"); eval graph card below.
3. **Right column (coach):**
   - Coach's summary feature card with a "Practice [N] critical moments" button.
   - Moves panel, collapsible, closed by default, with a summary like "6 moves · Show". Move buttons are highlighted for the current move (primary) and marked moves (baby blue).
   - Chat panel (tinted): "Ask your coach about this position", bubbles, input and "Send".

## Moment.dc.html — Critical moment

1. Step chips: "← Back to game", then Moment 1 (done), Moment 2 (current), Moment 3 (upcoming).
2. **Left:** side-to-move label and the board.
3. **Right:** eyebrow "CRITICAL MOMENT", title, instruction ("Move a piece on the board to try your answer"), tries-left counter, coach feedback feature card, hint panel (tinted), solution panel (primary outline, shown only after reveal), and buttons: "Get a hint" (outline), "Show the answer" (secondary), "Next moment →" (primary).

## Onboarding.dc.html — 12-game assessment

1. Hero: "Twelve games, one honest picture of your play." with a "Skip for now" link.
2. "Your 12 slots": four slot groups (White wins, White losses, Black wins, Black losses), each with three cells, plus "7 of 12 filled".
3. "Add games": tinted form with a multi-PGN textarea and "Check games"; a "Checked games" table (Players, Result, Date, Time control, I played, Slot) with a summary line and an "Add 3 games" button.
4. "Analyzing in your browser": progress bar, "Game 8 of 12 — move 14 of 38", and the resume note.
5. Baseline report card, locked until 12/12, with a disabled "Generate report · 7/12" button.

## Profile.dc.html — Profile

1. Avatar, name, and "Elo · time control · games analyzed".
2. **Form "About you":** display name, Elo (with help text), main time control as toggle buttons, "How you like to play" textarea with a 0/500 counter, Appearance (Light / Dark toggle), Cancel and Save.
3. **Side column:** baseline report card with "Read the report"; "Your tendencies" with bars ("Recent games count more than old ones").

## Redeem.dc.html — Invite

A centered card with three states: valid ("Invite accepted", next steps, "Set up my profile"), invalid/expired (with guidance to ask for a new link), and checking (progress bar).

## Conflicts with the spec (spec wins; confirm at M0)

1. **Color selector defaults to White.** On the Games form and in the onboarding table, the select shows White first and nothing forces a choice. SPEC_V3 §4.6 requires nothing selected, the color chosen *before* the PGN box, and the PGN box disabled until then. Build it as a two-option toggle ("I played White" / "I played Black") in the design's style, placed above the textarea.
2. **Tries per moment.** The design shows 3 tries; SPEC_V2 §8.2 reveals after the 2nd failed attempt. The owner picks one; it's a config value either way.
3. **"Get a hint" button.** In the spec, hints come with the coach's feedback after a failed try (lowest level first). The design adds a button to ask for one. Recommended: keep the button, but have it serve the next hint from `hints_allowed` and count it as using a hint, never revealing the move.
4. **Moment title gives away the answer type.** "Find the move that wins material" tells the user what the best move does before they try. Use a neutral title ("Find a better move") unless the text comes from an allowed hint.
5. **Default theme.** The design defaults to light; SPEC_V3 §4.1 said dark. The design wins here: light by default (the spec is updated to match).
6. **Settings.** The design puts Appearance in Profile, with no separate Settings page. Recommended: a "Settings" section on the Profile page, in the same style, holding everything from SPEC_V3 §4.3 (theme, coach detail level, playback speed, board colors, piece set, sounds, engine panel default, shortcut list).

## Not in the design (build in the same style)

- **Analysis page:** the Explain button, live engine panel, variations in the move list, mistake glyphs and eval-graph dots in the chess-meaning colors, coach arrows, line playback controls, and the walkthrough stepper.
- **Dashboard (SPEC_V3 §8.1):** the Games page already has the focus-area cards and recent games. Recommended: grow it into the dashboard by adding "Continue where you left off", the mistake-types chart, the accuracy-trend chart, and filters, rather than adding a separate page.
- **Nav items "Analysis" and "Critical moments"** need a game to show. Recommended: they open the most recent game (or its first unfinished moment), and show an empty state if there are no games yet.
- Baseline report page, keyboard-shortcut help overlay, toasts, empty and error states, loading skeletons, and the import review table.

New screens should reuse the header, cards, panels, buttons, and type styles above, and the owner reviews them at the checkpoint where they're built.
