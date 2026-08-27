# Mobile comps + Today — mockups

Six interactive phones. Open `index.html` in a browser.

Comps is the load-bearing surface. Today is the host that currently swallows it.

Every comps surface: **calculator above the map**, in flow. Hide folds it to one line. Nothing overlays the map (filters, photos, legend, and the calc all live in the column).

## The three bets (comps)

| | Idea | Under the map |
|---|---|---|
| **A · Photo strip** | Calc + map + horizontal photos | Peeking strip; tap a pin to snap |
| **B · One card** | Max map, inspect one pin | Single card, next/prev |
| **C · Vertical tray** | Closest to desktop | Scrolling photo rows |

A is the recommendation. C is the smallest change. B is for the on-the-phone-with-a-seller case.

## The three bets (Today)

| | Idea | What you open into |
|---|---|---|
| **A · Full screen** | Kill the Dialog chrome | Native page, tabs Call / Comps / Activity |
| **B · Board, then a page** | Keep the board; don't modal | Vertical list; tap → full-screen detail; comps is its own page |
| **C · Comps first** | Phone Today *is* pricing | Opens on the map; Qualify / Activity are tabs |}

A pairs with comps A. B if the board itself is the phone problem. C if setters open Today on a phone mainly to price.

## What is broken today (measured in the code, not guessed)

- Comps at 390px already *stacks*, but the map is a 26–32rem block *plus* a 28rem tray — you scroll the map off screen to see photos.
- Filters on page-mode stay open and wrap to ~8 rows between the rep and the map.
- TodayLeadModal is a `7xl` Dialog at `100vh-1rem` with a 42vh sidebar, a tab bar, and a Close footer. On a phone that is chrome, not a tool.
- Today board is three fixed-width columns with horizontal scroll. Not in these mockups except B, which replaces it.

## Skills used

- `frontend-design` for the mockups (CRM tokens, not a new aesthetic).
- Existing comps mockup language in `docs/comp-analyzer/mockup/` (pills, red/yellow/violet, Inter).
- No designer subagent in this harness; built here.

Do not implement until a version is picked.
