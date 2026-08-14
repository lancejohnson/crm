# Lead Desk — working plan

**Branch:** `feature/lead-desk` · **Worktree:** `~/crm-worktrees/lead-desk`
**Started:** 2026-08-14 · **Last updated:** 2026-08-14 (geo service scaffolded + sweep proven)

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

- [x] Repo created: `~/Projects/Groundwork/groundwork-geo` (own git repo)
- [x] **Adaptive quadtree sweep** — replaces lux's fixed 8x8. Subdivides only
      where saturation is observed, so rural costs 1 call and dense pays for
      the depth it needs. `SATURATION=1400`, `MAX_DEPTH=5`, circle-trimmed.
- [x] **Measured payoff (2 mi radius):** Indianapolis naive 1,832 -> **17,287**
      (49 calls, depth 3) = **9.44x**; the naive call was missing 94% of the
      neighbourhood. Olivia 1,007 -> 997 in **1 call, depth 0** (fewer because
      the circle trim drops bbox corners reaching 2.83 mi — correct).
- [x] `/health`, `/warm`, `/properties` verified: 139 GeoJSON features around
      the demo lead, guards return 422/501 correctly.
- [x] Coverage confirmed partial and normal: Indy 17,287 homes, only **41%
      priced**. Pills must render without a price.
- [x] Timing: dense 2-mi sweep ~75s / 49 calls — proves prefetch is mandatory,
      this can never run on page load.
- [ ] `geo/store.py` — PostGIS persistence (`/properties` currently 501s
      without `live=true`)
- [ ] Parcel enrichment + WAF cookie lifecycle on a headless box
- [ ] systemd unit + deploy to `/opt/groundwork-geo`
- [ ] Parcel enrichment + cookie lifecycle
- [ ] CRM hook + backfill (stage it — 362 leads × ~3k parcels ≈ 1M rows)

### 2. Vue port of v17
- [ ] Shell + panes against real `CompsView`
- [ ] Offer math, repair matrix, 2x2 (reuse `first_call.py`)
- [ ] Save determination (needs schema)
- [ ] Shortcuts + palette contributions

### 3. Telnyx migration — its own project, bigger than the lead desk
Replaces Quo/OpenPhone entirely. Unblocks the live copilot.

**Media Streaming** (verified 2026-08-14)
- `stream_url` wss + `stream_track: both_tracks` — rep and seller on **separate
  tracks**, so speaker separation is free. Today `call_transcript.py` infers it
  heuristically (`speaker` → `userId` → last-10-digit match).
- Codecs: PCMU/PCMA/G722/OPUS/AMR-WB/**L16 16 kHz**. L16 is the one Telnyx calls
  out for AI — no transcoding overhead. Chunks 20ms–30s. 1 bidirectional RTP
  stream per call.
- Telnyx ships reference integrations for **Deepgram** and **OpenAI
  speech-to-speech** (`team-telnyx/demo-node-telnyx/websocket-demos`).

**Frappe CRM already has a telephony FRAMEWORK — use it, don't reinvent**
- `crm/integrations/api.py` — `telephony_medium` abstraction,
  `_get_recording_credentials(medium)`, `is_call_integration_enabled()`.
- **`CRM Telephony Agent`** doctype = per-user default calling medium.
- `components/Telephony/CallUI.vue` (generic) + `TwilioCallUI.vue` (provider skin);
  `composables/twilio.js`; `Settings/Telephony/*`.
- `twilio/api.py` `generate_access_token()` → **browser softphone over WebRTC**.
  Telnyx's `@telnyx/webrtc` fits the same slot.
- Ships with **twilio + exotel only — there is NO Telnyx provider**. We write it.
- **Our Quo integration bypasses this framework entirely** (own doctype, own
  webhooks, own UI). Moving to Telnyx along these seams pulls us back toward
  upstream, which helps future rebases off frappe/crm.
- The framework covers **calls only**. SMS stays ours — just repointed.

**Surface to migrate (measured)**
- **30+ app files**, **20+ ops files**, `Quo Message` = **4,357 rows**.
- Heaviest: `quo_contacts.py` (92 refs), `activity_progress.py` (26), `sms.py` (25).
- Categories: SMS inbox + per-lead threads + bulk text + buyer texts · call logs ·
  recordings · transcripts · AI review · call classification · contact two-way sync ·
  activity report · standup · intraday pulse · do-not-contact · agreement notifications.

**Non-obvious dependencies that WILL break if forgotten**
- `investorlift_2fa.py` — the IL scraper captures its 2FA codes from **inbound SMS**
  through the Quo webhook. Losing it silently breaks the InvestorLift sync.
- `agreement_notify.py` — sends from a dedicated "Notifications" line
  (+1 952 395 3833), not a rep line.
- `do_not_contact.py` — opt-out keyword detection runs on `Quo Message` after_insert.
- Sequence texts + `sequence_drain.py`.
- `User.custom_quo_number` — per-user sending line, threaded through many surfaces.
- The `caller` → `receiver` → `custom_quo_number` attribution chain is shared by
  `activity_progress.py`, `today_pulse.py` and `lead_owner_backfill.py`. They must
  keep agreeing about whose call it was.
- **Direction matters**: `userId` is the dialer on OUTGOING calls but the LINE owner
  on INCOMING. Any Telnyx mapping must preserve that distinction (gw303).

**Strategy**
- `CRM Call Log` is already the stable interface — the Quo mirror writes into it and
  everything downstream reads it. Keep that boundary; swap what fills it.

**CUTOVER: DECIDED 2026-08-14 — run parallel, port numbers in later.**
New Telnyx numbers stand up alongside Quo; existing numbers port afterwards.
This avoids a porting window where texts silently drop, at the cost of two live
systems for a period.

Parallel running turns three things from "nice" into **mandatory, before any
Telnyx traffic exists**:

1. **Do-not-contact must be provider-agnostic FIRST.** This is compliance, not
   tidiness. Today opt-out detection is bound to `Quo Message` after_insert
   (`hooks.py:187`) and the flag lives on `CRM Buyer.do_not_contact`. If someone
   replies STOP to a Quo number and we then text them from Telnyx, we have texted
   a person who asked us to stop. The check in `bulk_text.send_buyer_text` must
   run for every provider, and inbound opt-out detection must fire on Telnyx
   inbound too. **Build this before the first Telnyx send.**
2. **Every report must union both providers or it silently under-counts.** The
   activity report, standup, intraday pulse and `lead_owner_backfill` all share
   the `caller` → `receiver` → `custom_quo_number` chain. During parallel, half
   the calls are invisible to it. This is the same failure family as the
   `reference_doctype` trap and the incoming-`userId` trap — no error, just a
   wrong number that looks plausible.
3. **`User.custom_quo_number` is single-valued and must become per-provider.** A
   rep will hold a Quo line AND a Telnyx line simultaneously. Rename/replace with
   a mapping (e.g. `CRM Telephony Agent` already exists upstream for exactly this
   — per-user calling medium — so extend it rather than adding another field).

**Free seam discovered 2026-08-14:** `CRM Call Log.telephony_medium` already
exists and **every one of the 4,102 rows is `"Manual"`** — it carries no
information today. Telnyx writes `"Telnyx"`, re-stamp the Quo mirror as `"Quo"`,
and every downstream reader gets a discriminator for free, no schema change.
SMS has no equivalent yet: `Quo Message` needs a `provider` column (cheaper than
renaming a doctype with 4,357 rows).

- [ ] Provider-agnostic do-not-contact (**blocks all Telnyx sending**)
- [ ] `provider` column on Quo Message; re-stamp `telephony_medium` on Call Log
- [ ] Per-provider line mapping (extend `CRM Telephony Agent`)
- [ ] Union both providers in every report before Telnyx carries real traffic
- [ ] `crm/integrations/telnyx/` + `TelnyxCallUI.vue` + settings doctype
- [ ] Exit condition for the parallel period

### 4. Test environment — DECIDED: second Frappe site
Prod is currently the only backend — the Vite dev server proxies to it. Fine for
pure-frontend work, **not** fine for telephony (real calls, real money) or a data
service that writes.

**Shape:** `crm-test.groundworkpro.com` as a second site inside the *existing*
containers. Frappe is natively multi-site, so this costs one MariaDB database and
an nginx vhost — not six more containers on a box with ~4 GB free.
- Telnyx test numbers point their webhooks here. **Never at prod.**
- Tradeoff, accepted: shares the worker/scheduler pool with prod, so a runaway
  test job competes with real work. If that bites, next step is a separate box.
- Run `docker system prune` first — **~20 GB is reclaimable** (16.5 GB build cache).
- [ ] `bench new-site`, nginx vhost, TLS
- [ ] Decide data: fresh, or a sanitised prod copy (phone numbers scrubbed so a
      test cannot text a real seller)

**NOTE — this reverses a standing instruction.** `CLAUDE.md` says the local backend
mirror was removed 2026-06-19 and "one should not be recreated." That was correct
when this was frontend-only work against prod data. It stops being correct once we
place real calls and write parcel data. Amend that line with the reason when the
test site lands, rather than silently contradicting it.

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
5. **Does the live copilot run on the Telnyx stream, or on the CRM?** The websocket
   consumer has to live somewhere reachable by Telnyx. Candidate: the geo service
   grows a sibling, or its own small service.
6. **Thread boundary during parallel** — proposal: existing conversations stay on
   Quo (the seller has that number saved and will reply to it), new leads start on
   Telnyx. Clean, testable, no mid-thread number switch. Confirm before building.
7. **When does parallel end?** Needs an explicit exit condition, or it becomes
   permanent and we pay for both forever.

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
- Decided: Telnyx cutover runs **parallel**, port numbers in later.
- Approved: make do-not-contact provider-agnostic (**blocks Telnyx sending**).
- Built `groundwork-geo` — separate repo, adaptive sweep proven at 9.44x the
  naive call in Indianapolis. Service skeleton verified end to end.
