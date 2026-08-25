# Comp analyzer — mockup

`v1.html` is the AI price analyzer as it lands on the **Today modal's Comps
pane** — deliberately the tightest of the three hosts (the comps page has ~800px
of pane, a phone has ~260px), because that is where the layout either works or
does not.

Open it in a browser. It is interactive: **Photos / Analysis** swaps the rail,
and switching back to Analysis replays the idle → running → done states.

- `?scroll=N` pre-scrolls the rail (for screenshots of the half below the fold)
- `?cot=1` opens the full reasoning

Design language is inherited from the lead-desk `v17.html`, which already
settled the voice ("How I comped it") and the condition grades. The one thing
this deliberately does NOT inherit is v17's `arv = avgPsf × sqft` — see below.

## Why the ARV is not average $/sf

Measured on our own 92,693 comps (400-trial simulation, comp set = the 12
nearest in ZIP):

| | |
|---|---|
| marginal / average $/sf | **0.55** median (p10 0.26, p90 0.94) |
| size-independent share of a median home's price | **44%** |
| subjects >5% bigger than their comp set | **40%** |
| naive $/sf tops every comp in its own set, when subject is bigger | **29%** |
| median abs error vs the subject's real price | naive **14.4%** → size-aware **11.0%** |

So the rail shows the naive number struck through, names the marginal rate, and
caps at the best comparable sale. The cap did **not** improve median accuracy
(11.0% either way) — it is a credibility guard against telling a seller their
tired 3/1 is worth more than the nicest flip on the street, not a better
estimator, and it is presented that way.
