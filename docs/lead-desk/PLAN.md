# Lead Desk — working plan

**Branch:** `feature/lead-desk` · **Worktree:** `~/crm-worktrees/lead-desk`
**Started:** 2026-08-14 · **Last updated:** 2026-08-14

> This file is the memory for a project that spans many days and two machines.
> Read it first. Update it at the end of every session — decisions, measured
> numbers, and what's next. A decision that isn't written here will be
> re-litigated in three weeks.

---

## What we're building

A single-screen desk a rep works a live seller call from: comps map, comp table
+ ARV, repair estimate, offer calculation, a persistent motivation/price 2x2, an
AI copilot, the activity timeline, and a saved price determination.

**Design is settled.** `~/crm-mockups/today-leadzolo/v17.html` is the reference —
layout, offer formula, the 2x2, keyboard shortcuts, command palette, Street View.
Do not redesign it; port it.

---

## Decisions already made (don't re-open without a reason)

| Decision | Why |
|---|---|
| **Offer = 90% ARV − 2×Repairs − Fee** | Repairs doubled deliberately: buffers overrun rather than trusting a cheat-sheet mid-call. |
| **ARV rounds to nearest $1,000** | False precision on a number the rep says out loud. |
| **Desktop only, `height:100vh`** | Laptops, no external monitor, ~1280×800 usable. |
| **Data conflicts are invisible** | Zillow silently wins over Leadzolo; every fact editable. |
| **One geo service, not several** | The Redfin WAF cookie + rate limit is a single shared resource; splitting it re-creates the problem it exists to solve. |
| **App/UI code stays in `frappe-crm-app`** | It's made of CRM Lead, CRM Comp, `comps.py`, `zillow.py`, `CompsView.vue`, the activity feed. A separate repo means duplication or a cross-app dependency. |
| **Geo service is separate** | Different lifecycle, different language runtime, and other Groundwork apps should be able to call it. |
| **Telnyx replaces Quo** | Unblocks the live copilot (see below). |

## Reversed decisions (kept so we don't loop)

- **2026-08-14 — "copilot should be live-but-not-listening for v1."** Reversed the
  same day. That was correct *for Quo*, whose webhooks are all `*.completed` —
  the transcript only arrives after the call ends. Telnyx Media Streaming
  provides live audio over websocket, so a genuinely live copilot is buildable.

---

## Measured facts (don't re-measure these)

**Redfin, via the lux method — free, unauthenticated for the property sweep**
- `/stingray/api/gis/avm?poly=` returns properties in an arbitrary polygon, **no cookie**.
- 1-mile radius: Olivia MN **971**, Chicago **1,498**, Indianapolis **1,874** homes in 2–5s.
- **The cap is ~1,900 and it fails SILENTLY.** Indianapolis: 0.25mi→340, 0.5mi→1,231,
  1.0mi→1,874, **2.0mi→1,778 (fewer than 1mi)**. No error, just an arbitrary subset.
  The `~350` figure in lux's docstring is stale. **Always tile** (`tile_bbox`, 4×4 min).
- Attribute coverage is partial: of 1,874, **627 have price, ~1,140 sqft/year**, and
  1,256 have no MLS status. That's the off-market universe — design pills for missing price.
- Parcel outlines: `/stingray/api/home/details/propertyParcelInfo?propertyId=` →
  APN, FIPS, and WKT `POLYGON`. Verified: APN `35-02420-00`, FIPS `27129`.
- That endpoint needs an `aws-waf-token`. **Playwright is not required** — minting it
  by loading a Redfin page in a real browser and calling with `credentials:'include'`
  works (verified, 390-char token). Bucket ≈4,200 tokens, ~70/s refill, 50 rps sustained.

**Server (`groundwork-apps`)**
- 4 CPU, 7.6 GB RAM (~4 GB available), **150 GB disk / 39 GB free (74%)**, load 0.65.
- **PostGIS 3.4.2 already installed** on the native Postgres at `127.0.0.1:5432`.
- `properties` DB (3.2 GB) is **devproppy's Zillow data** (4.58M rows), not lux.
  `lux` DB is 54 MB — no meaningful parcel head start.
- **~20 GB is reclaimable**: `docker system df` shows 16.5 GB build cache + ~5 GB
  in volumes/images. Prune before concluding there's no room.
- `/opt` convention: native venv + systemd/cron (istl-buyer, devproppy,
  hud-reference-data). Not everything is a container.

**Lead volume**
- **12.8 leads/day** average, 37 on the busiest day (last 28d).
- **362 unparked leads, all 362 already geocoded** (`property_lat/lng` populated) —
  prefetch needs no geocoding step, and the backfill has coordinates ready.

**Google Maps Embed key** (done, 2026-08-14)
- Project `claude-code-486305`, key name `CRM Street View (Maps Embed)`.
- Restricted to the Maps Embed API + referrers: `crm.groundworkpro.com/*`,
  `localhost:8080`, `localhost:8477`, the Tailscale share host.
- Stored at `~/.config/groundwork/maps_embed_key`. Should move to site_config
  as `maps_embed_key` when the Vue port lands.
- `location=` accepts **lat,lng only** — an address string returns `Invalid 'location'`.
- Cold rural panoramas take **20–30s** to first paint. Fallback must say "Loading",
  not "could not load".
- Use `referrerpolicy="origin"` on the iframe — never full-URL, which would leak
  record IDs (and share access keys) to Google.

---

## Already exists — wire it up, don't rebuild

| Need | Where |
|---|---|
| Subject facts (beds/baths/sqft/year) | `crm/api/zillow.py`, 30-day cache |
| Comps → $/sf → ARV | `CRM Comp` (67,679 rows) + `crm/api/comps.py` |
| Comps map, pills, filters, ladder | `frontend/src/components/CompsView.vue` (1,424 lines) |
| Comp detail + photos | `CompDetailModal.vue` + `comps.get_comp_details` |
| Motivation/price 2x2 | `crm/api/first_call.py` + `utils/index.js firstCallRead()` |
| Activity timeline | `components/Activities/Activities.vue` |
| Command palette (⌘K) | `components/CommandPalette.vue` — extend, don't create |
| Shortcut composable | `composables/useKeyboardShortcuts.js` |
| Repair matrix, offer math | pure arithmetic — see v17 |
| Comp condition grading | `~/Projects/Groundwork/devproppy/wholesaling/` classifiers (unwired) |

**Keys already taken:** `⌘K` palette · `[` sidebar · `]` detail panel · `⌘,` settings ·
`d`/`h`/`u` on comps. The activity rail should register as `activeDetailPanel` so `]`
keeps one meaning app-wide.

---

## Workstreams

### 1. Geo microservice — `groundwork-geo`
Own repo, `/opt/groundwork-geo`, FastAPI + psycopg, own venv + systemd, database
`geo` in the existing native Postgres. Source-agnostic: it knows nothing about
CRM Lead.

```
POST /warm      {lat,lng,radius_m}   → enqueue sweep
GET  /properties?lat=&lng=&radius=   → GeoJSON FeatureCollection
GET  /parcels?bbox=                  → lot-line polygons
GET  /parcel/{property_id}           → single parcel detail
```

It owns the WAF cookie lifecycle and the rate limiter, so lux/devproppy/CRM can
never collectively get the egress IP banned. Prefetch is triggered at lead
purchase (open question: CRM `after_insert` vs earlier in `istl-buyer`).

- [ ] Repo + skeleton + systemd
- [ ] Tiled sweep (port `tile_bbox` from lux, fix the stale cap)
- [ ] `/warm` + `/properties`, measure on 10 Chicago/Indy leads
- [ ] Parcel enrichment + cookie lifecycle
- [ ] CRM hook + backfill (stage it — 362 leads × ~3k parcels ≈ 1M rows)

### 2. Vue port of v17
- [ ] Shell + panes against real `CompsView`
- [ ] Offer math, repair matrix, 2x2 (reuse `first_call.py`)
- [ ] Save determination (needs schema)
- [ ] Shortcuts + palette contributions

### 3. Telnyx migration
Replaces Quo/OpenPhone. Unblocks the live copilot.
- Media Streaming: `stream_url` wss + `stream_track: both_tracks` (separate rep/seller
  tracks — speaker separation free, unlike Quo where it's guessed).
- Codecs: L16 16 kHz recommended for AI (no transcoding overhead).
- Telnyx ships reference integrations for Deepgram + OpenAI speech-to-speech.
- [ ] Scope what depends on Quo today (big: sms.py, call logs, webhooks, contacts sync)

### 4. Test environment
Prod is currently the only backend — the Vite dev server proxies to it. That was
acceptable for pure-frontend work and is **not** acceptable for telephony (real
calls, real money) or a data service that writes.
- [ ] Decide shape (see open questions)

---

## Open questions

1. **Prefetch trigger** — CRM `after_insert`, or earlier at the actual purchase in
   `istl-buyer` (gains minutes of head start)?
2. **Test env shape** — Frappe is natively multi-site, so a second site in the
   *same* containers (`crm-test.`) is far lighter than a second stack. Needs a
   prune first. Alternative: separate box.
3. **Copilot scope for v1** — now that live is possible, how much of it is live
   transcription vs. screen-driven commands?
4. **Geo repo name/location** — `groundwork-geo`? Under `~/Projects/Groundwork/`.

---

## Session log

### 2026-08-14
- Settled v17 as the design reference; added shortcuts + command palette (audited
  existing bindings first, found `]` collision).
- Got a Google Maps Embed API key; Street View live in the mockup.
- Established Redfin/lux as the parcel source — **Regrid is not needed** (it would
  have been $375/mo and bills per parcel record, which is unaffordable for browsing).
- Confirmed Quo cannot do live transcription; confirmed Telnyx can.
- Created this branch + worktree.
