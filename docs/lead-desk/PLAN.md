# Lead Desk — working plan

**Branch:** `feature/lead-desk` · **Worktree:** `~/crm-worktrees/lead-desk`
**Started:** 2026-08-14 · **Last updated:** 2026-08-14 (geo service live on the box; CRM client wired)

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
- [~] `geo/store.py` — written: properties/parcels/sweeps tables, upserts,
      `properties_near`, `parcels_in_bbox`, `unparcelled_near` enrich queue.
      **NOT VERIFIED** — never run against live PostGIS. This laptop has Postgres
      14 while Homebrew PostGIS targets 17/18, and the Docker daemon is down.
      Next session: `brew install postgresql@17` on a spare port, or start Docker.
- [x] **Parcel enrichment — and the WAF cookie turned out to be unnecessary.**
      60 parcels at 6.6/s from the box with NO cookie: 59 polygons, 1 no-polygon,
      0 errors, zero 403s. lux's Playwright requirement does not apply at our
      rates. `enrich.py` is cookie-optimistic and stops cleanly on 403.
      Cost: ~45 min to fully enrich a dense 2-mile neighbourhood.
- [x] Deployed: `groundworkpro/groundwork-geo`, `/opt/groundwork-geo`,
      `geo-api.service` on 127.0.0.1:**8110** (8100 is Documenso), database
      `geo` on the native PostGIS. `store.py` verified live.
- [x] **CRM can reach the service.** A container reaches the host on its OWN
      bridge gateway — `frappe-crm_default` = **172.20.0.1**, not docker0's
      172.17.0.1. `bin/serve.sh` resolves it at start (compose subnets are
      dynamic). Verified: container gets 200, public IP refuses.
      **Never bind 0.0.0.0 there** — no firewall (ufw inactive, INPUT ACCEPT)
      on a public IP.
- [x] Enrich nearest-first, so the parcels around the subject land in seconds
      rather than after the full ~45 min. **Had to order on `geography`** — KNN
      on plain `geometry` sorts by DEGREES and was non-monotonic in metres
      (66m ahead of 53m). Same flaw fixed in `properties_near`.
- [x] **CRM client + warm-at-purchase hook** (`crm/api/geo.py`). Reuses
      `comps._subject_point` so nothing disagrees about a lead's location.
      Enqueued, never inline — an inline 75s sweep would hold the inbound
      webhook open until the vendor retries and duplicates the lead.
      Config-gated on `geo_service_url`; verified it no-ops when unset.
      Verified live from inside the container: Brooklyn lead -> 824 features.
      **Backfill excludes parked imports** — dry run said 876 (= 362 live + 514
      parked); now 362. NULL-safe `isnull() | != 1`.
- [x] **`geo_service_url` IS SET ON PROD (2026-08-15)** — the geo client is live,
      so every new lead warms its neighbourhood and enriches its block. The desk
      UI for it ships with the next deploy of this branch.
- [ ] Deploy (app code is committed, NOT yet built into an image)
- [x] **Frontend: neighbourhood on the desk map** — a "Nearby" toggle drawing
      every home around the subject as canvas dots, filled when we have a price
      and hollow when we do not (47% priced on the Chicago lead; that hollow
      majority IS the off-market universe, not missing data). Verified PASS.
- [x] **Frontend: parcels** — lot lines ride with the Nearby layer above zoom 16
      and follow the viewport. The service gained `/parcels` and `/enrich`, and a
      sweep now enriches its own inner 600m. See below.
- [ ] **verify_ui the desk page** (required before calling any of this done)
- [ ] Seed `crm-test` — it has **0 leads**, so UI work still uses the
      prod-backed dev server (`CRM_DEV_TARGET=... yarn dev`). crm-test is for
      telephony and writes, not for looking at leads.
- [ ] Parcel enrichment + cookie lifecycle
- [ ] CRM hook + backfill (stage it — 362 leads × ~3k parcels ≈ 1M rows)

### 2. Vue port of v17
- [~] **Slice 1: route + shell.** `/leads/:leadId/desk` -> `pages/LeadDesk.vue`,
      embedding the real `CompsView` (NOT the mockup's hand-rolled map -- 1,424
      lines of hard-won behaviour would be thrown away). `pageMode` deliberately
      not passed: underwriting belongs on the comps page, the desk computes the
      offer live.
      **Verified (desktop-chrome, 2 verifier runs + a targeted DOM check).**
      On CRM-LEAD-2026-00854: 76 price pills, 76 comp rows, filters, Subject pill,
      ring labels, clean console, 'Open lead' navigates.
      Worktree needed its own `node_modules` (472 MB).

      Two bugs the verification caught, both now fixed:
      1. Header read CRM Lead directly -> showed the seller's band 'YR 1900-1950'
         while the map pill said 1930. CompsView now **emits** the resolved
         subject facts; `get_lead_comps` is the only place that merges them
         best-first and labels the source. Emitting avoids a second call that
         re-geocodes and can hit a paid Zillow lookup.
      2. The fix's first cut guessed the payload as `{value, source}` objects. It
         is **flat scalars + sidecars** (`beds: 2.0`, `beds_label: "2"`,
         `beds_exact: true`, plus a sibling `source` map). Every lookup returned
         null and the badge row rendered EMPTY -- which reads as 'no data', not
         as a bug. Now uses `*_label`, with `*_exact` driving a
         '(range, not exact)' tooltip note.

      **Test-lead choice matters:** the first run used a Brooklyn lead and got
      zero comps. That was not a page bug -- `CRM Comp` has **0 rows for ZIP
      11230**. Use a lead with real coverage; Chicago 00854 has 561.
- [x] Right rail: offer math, repair matrix, 2x2 (reuse `first_call.py`)
- [ ] Left rail: copilot (blocked on the Telnyx decision)
- [x] **Save determination** — `crm/api/price_determination.py`, the two CRM Lead
      fields, and the activity rail. See SESSION 3 below.
- [~] Shortcuts: `S` saves, `]` toggles the activity rail (registered as
      `activeDetailPanel`, so `]` keeps one meaning app-wide). Palette
      contributions still to do.

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

- [x] **`provider` column on Quo Message** (live on prod, 4,403 rows backfilled
      to "Quo"). **Calls needed NOTHING and the plan above was wrong about which
      field**: measured before writing anything, all 4,192 CRM Call Log rows are
      `medium = "Quo"` / `telephony_medium = "Manual"` — the ops webhook has
      written `medium` since the mirror was built, so the discriminator already
      exists, is 100% populated and is correct. Telnyx writes `medium = "Telnyx"`.
      Re-stamping `telephony_medium` would have replaced a right field with a
      duplicate one.
- [x] **Per-provider line mapping** — `CRM Telephony Agent.custom_telnyx_number`
      (live), read through `telephony.user_lines()` / `sending_line()`.
      `User.custom_quo_number` stays authoritative for Quo; the agent row is
      where the SECOND line lives, because a rep will hold both at once.
- [x] **One attribution chain, provider-wide** — `crm/api/telephony.py` (new).
      `activity_progress`, `today_pulse` and `sms` now share `line_owners()`
      instead of each building their own map, and `_workspace_lines()` unions the
      live Quo list with every configured line so a rep-to-rep call over Telnyx
      is still "internal" rather than outreach to a stranger.
      **Verified equivalent on prod before/after**: 3 days of the Team Activity
      report and the SMS sender map byte-identical, the pulse identical except
      its clock-derived line, and 0 of 2,896 calls over 30 days change hands.
- [x] **Provider-agnostic do-not-contact** (was blocking all Telnyx sending).
      `record_inbound_opt_out()` takes plain values, not a Quo Message doc, so any
      provider's inbound handler calls the same rule; `check_inbound_opt_out` is
      now a thin Quo adapter and `hooks.py` is untouched. Added
      `is_blocked_number()` — a flag is a statement about a PERSON, and with two
      providers live the same human can exist as more than one row. Verified on
      prod read-only: blocks `(602) 320-1169`, `6023201169`, `+16023201169`,
      `1-602-320-1169`; passes an unrelated number. 10 buyers flagged.
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
- [x] **`crm-test.groundworkpro.com` created** — second site in the existing
      containers, crm app installed. Cost: one MariaDB database, no new
      containers.
- [x] **Fresh, not a prod copy** — and that turned out to be the whole safety
      story. Every integration is gated on a per-site `site_config` key
      (`quo_api_key`, `mattermost_token`, `gemini_api_key`, `docuseal_api_token`,
      `investorlift_*`, `rapidapi_*`, `google_sa_json`, `contract_parser_url`).
      A fresh site has **none** of them, so nothing can text a seller, post to
      Mattermost, sign a document or spend an API credit. Verified: the config
      holds only db/dev keys.
- [x] Safety posture: `pause_scheduler: 1`, `mute_emails: 1`, `developer_mode: 1`.
      Frappe also disables the scheduler on a new site by default — belt and
      braces, because `sequence_drain.drain_due` is on `* * * * *` and
      `today_board.run_today_sync` on `*/5`, and those send real texts.
- [x] Prod verified unaffected (876 leads, unchanged) and reachable as before.
- [x] Reclaimed **16.5 GB** of docker build cache first: 39 GB -> 51 GB free.
      **Build cache only** — `docker system prune -a` would delete the older
      `crm:gw*` images, which are the rollback targets.
- [ ] **DNS record needed**: `crm-test.groundworkpro.com` does not resolve, so
      there is no browser access and no TLS yet. Until then reach it with a Host
      header against the backend upstream, or an SSH tunnel:
          ssh -L 8090:127.0.0.1:8090 groundwork-apps
          curl -H 'Host: crm-test.groundworkpro.com' localhost:8090/api/method/ping
      Verified working: returns `{"message":"pong"}`.
- [ ] nginx vhost + cert once DNS exists

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
- Made do-not-contact provider-agnostic + number-keyed; verified against prod.
- Wrote `geo/store.py` (PostGIS). **Unverified** — no working PostGIS target on
  this machine. That is the first thing to fix next session.

---

## BatchData comps fallback — SHIPPED (gw336), one module

`CRM Comp` only covers iSpeedToLead ZIPs. Sampling the 45 most recent leads,
**18% land on an empty map** — Brooklyn 11230 holds 0 rows. When nothing of ours
is in radius we buy a small set from BatchData. Automatic (Lance's call).

### TWO AGENTS BUILT THIS INDEPENDENTLY — read this before touching it

`batchdata_comps.py` (kept) and `comps_batchdata.py` (deleted) existed at once,
near-identical names, incompatible config keys and cache fields. The in-flight
check exists to prevent exactly this and did not, because the other agent's work
was on an unpushed branch on the MBP.

**`batchdata_comps.py` won**, and the deciding reason was not style: it sets
`selected` / `hidden` / `recency_days` on every comp, so the map's hide-use
buttons and recency fade keep working. The deleted one did not — its comps would
have rendered as un-hideable pills that never faded.

Ported in from the deleted one:
- **`DEFAULT_TAKE = 25`.** Not affordability. The response is NOT
  relevance-ordered, so `take` decides how much there is to CHOOSE from.
  Measured, Brooklyn lead (3bd/1444sf/1930), best-6 after ranking:
  take=10 -> mean score 1.91, median 0.85mi, median $788/sf;
  take=25 -> mean score 1.19, median 0.59mi, median $919/sf.
  **Five of the best six were invisible at take=10** and the median $/sf moved
  **17%** — a different ARV, not tidier comps.
- **`MAX_MILES = 2.0`, dropping not padding.** `compAddress` has no radius
  control and has been seen matching to ~3mi.
- **Shape ranking** (distance dominant, sqft/beds/year adjust). The provider
  returns no similarity score. A missing fact is never scored as a bad match, or
  every sparse row sinks.

### Names — one of each, the orphans are gone
    config     batchdata_comps_api_key        (site_config)
    cache      CRM Lead.batchdata_comps       {"t": ..., "comps": [...]}
    stamp      CRM Lead.batchdata_comps_fetched_at
    TTL        90d hit / 14d miss
`batchdata_comps_key` and `batchdata_comps_at` were mine and have been dropped
from prod. **The two modules stored different JSON shapes in the same field** —
a bare list vs `{"t","comps"}` — so a payload written by the deleted module is
unreadable by the survivor. Verified 0 remain.

### Traps, all paid for
- **`geoLocation`/`radiusMiles` is SILENTLY IGNORED.** HTTP 200, properties from
  other states. Only `compAddress` constrains geography.
- **`sale.lastSaleDate` accepts `minDate`/`maxDate` ONLY.** min/max, start/end,
  from/to, gte/lte and ISO datetimes all fail "Invalid Date", and an
  unrecognised key is silently ignored — paying for stale rows, never told.
- **Prices are `sale.lastSale.price`, NOT `deedHistory`** (this token returns no
  deedHistory at all). Reading deedHistory makes every comp look $0.
- **Two tokens, 21x apart**: `BATCHDATA_COMPS_API_KEY` $0.030/row vs
  `BATCHDATA_API_KEY` $0.640/row. Billing is **per row returned**, verified by
  wallet-balance deltas — not per request, which a rate-limit header wrongly
  suggested.

### Live, verified on prod
`{'source':'batchdata','used':True,'count':6,'basis':'last 2 years'}` — six
Brooklyn comps 0.21-0.75mi, all 3bd against a 3bd subject, 1248-1727sf against
1444, none over the cap, hide/select/recency populated. ~$0.75/lead, cached.

## Deploy readiness (2026-08-14)

**The branch now contains prod's code.** This nearly went wrong:

`docker image inspect ghcr.io/frappe/crm:v1.67.0-gw333 --format '{{json .Config.Labels}}'`
reports `org.opencontainers.image.revision = 2ae06c50` — prod was built from
**feature/kanban-modal**, NOT groundwork. `feature/lead-desk` was based on
groundwork and so was missing eight live commits (dispo-buyer badges, national
buyer lookup, lead quick view, kanban hover-chip colours, the Today modal's real
comps map). `build_image.sh` replaces rather than merges, so deploying would have
deleted all of it — green build, passing smoke test, gw258 all over again.

Fixed by merging 2ae06c50 into the branch. **Clean.** `git merge-tree` had
flagged `CompsView.vue` as "changed in both", which means overlap rather than
conflict — my nine added lines (the subject emit) sat away from their edits.
Verified after: emit present, DispoBuyerBadges / LeadQuickViewModal /
dispo_buyers.py present, `yarn build` passes, and the desk still renders 76 pills
with BD 2 / BA 1 / SQFT 876 / YR 1908 agreeing with the Subject pill.

**Two corrections to an earlier alarm in this file:** `feature/kanban-modal` was
already on origin, and the MBP's `4f964773` was already merged into groundwork.
Neither was ever at risk. The stale base was the real problem.

**Always check the image revision before deploying.** One command, and it is the
difference between shipping and silently deleting a fortnight of someone's work.

- [ ] Deploy: `cd ../frappe-crm-deploy && git pull && ./scripts/build_image.sh FORK=~/crm-worktrees/lead-desk`
- [ ] Then BatchData go-live (setup script + `batchdata_comps_key`)

---

# SESSION 2 END STATE (2026-08-14) — start here

**Launch a new session from:** `~/crm-worktrees/lead-desk` (branch
`feature/lead-desk`, clean, pushed). This file is the memory; read it first.

Other repos this project touches:
    ~/Projects/Groundwork/frappe-crm-deploy   ops: deploy, envs, setup scripts
    ~/Projects/Groundwork/groundwork-geo      the geo microservice
    ~/Projects/Groundwork/frappe-crm-app      main checkout — has Lance's
                                              UNCOMMITTED in-flight work; leave it

## Production right now

    gw336 @ 098ca26c (clean)   smoke: all green   drift: PASS
    Live: lead desk route, geo client, provider-agnostic DNC, BatchData fallback

`groundwork` contains both feature branches. `feature/lead-desk` = groundwork +
the desk page + the offer rail, and is NOT deployed.

## Done this session, beyond the BatchData section above

- **Lead desk slice 1+2.** `/leads/:leadId/desk` -> `pages/LeadDesk.vue`, which
  embeds the real `CompsView` (not the mockup's map) and `OfferRail.vue`.
  Verified live: 76 comps, header facts agreeing with the Subject pill, and ARV
  $48,000 = $55/sf x 876sf with a correct $0 offer + warning.
  `CompsView` gained two emits: `subject` and `picked`.
- **Geo service deployed**: `geo-api.service`, 127.0.0.1 -> the CRM's bridge
  gateway, `/warm` persists to PostGIS, `/properties` serves the store.
- **Staging box**: Hetzner `crm-staging` 87.99.154.150 (cpx21, ubuntu 24.04,
  **devproppy** project). DNS live. Nothing installed on it yet.
- **Deploy is env-parameterised**: `envs/prod.env` / `envs/staging.env`,
  `ENV=staging ./scripts/build_image.sh`. Default is prod, byte-identical to
  before. Parameterising found three HARDCODED prod site names in the standby
  health probe and cache-clear — a staging deploy would have hit prod.

## Traps learned the hard way this session — do not re-earn these

- **`crm-test.groundworkpro.com` shares production's APP CODE.** Frappe
  multi-site is one bench, one codebase, many sites. It isolates DATA, not code,
  so it CANNOT be used to test a branch. That is why the staging BOX exists.
- **Check the image revision before every deploy.**
  `docker image inspect <tag> --format '{{json .Config.Labels}}'` ->
  `org.opencontainers.image.revision`. Prod was built from `feature/kanban-modal`
  (2ae06c50), not groundwork — deploying a groundwork-based branch would have
  deleted eight live commits. `build_image.sh` has its own clobber guard which
  correctly refused; **`FORK=` must be an ENV VAR, not an argument**, or it
  silently reads the main checkout.
- **A `-dirty` revision in the build banner means somebody's uncommitted work
  just shipped.** gw335 shipped Lance's in-flight `hooks.py` (tracked) but NOT
  his untracked `daily_outreach.py` — `git stash create` skips untracked files —
  leaving prod with a scheduler hook pointing at an absent module. gw336 is the
  same commit rebuilt clean.
- **`nc_dns.py` was dangerous and is now fixed** (`~/.claude/api-helpers/`,
  **not in any git repo — worth versioning**). Three bugs, all in the same
  family: Namecheap `getHosts` returns `Name`/`Type` but `setHosts` expects
  `HostName`/`RecordType`, so every exported record had a blank name; `setHosts`
  is a FULL REPLACE, so applying that would have erased all 34 records while the
  diff looked clean (broken compared against broken); and addresses come back
  XML-escaped, so a CAA value `0 issue &quot;x&quot;` was written back literally
  and rejected. Now: correct field mapping, XML-unescape, a refuse-on-blank
  guard, and domain-based account routing (groundworkpro.com -> Servant account,
  egress 5.161.68.223 via groundwork-apps).
  **If `apply` was ever run on a WBG domain, check that zone.**

## Next, in order

1. ~~Bootstrap staging~~ — done, see SESSION 3. **crm-staging.groundworkpro.com
   is live**, TLS, running `feature/lead-desk` against a scrubbed copy of prod.
2. ~~Desk slice 3~~ — done, see SESSION 3.
3. Telnyx — its own project, bigger than the desk. See the section above.
   Copilot stays blocked until it lands. The three prerequisites that must exist
   BEFORE any Telnyx traffic are still open: the `provider` column on Quo Message
   + re-stamping `telephony_medium`, per-provider line mapping, and unioning both
   providers in every report. Two decisions are still unanswered (open questions
   6 and 7): the thread boundary during parallel running, and its exit condition.

## Open, needing a human

- Deploying `feature/lead-desk` to prod: small (226 lines) but `CompsView` is
  used by `TodayLeadModal`, `CompDetailModal` and `Comps.vue` — all live.
- Lance's four uncommitted files in the main checkout.
- Orphan cleanup is DONE (`batchdata_comps_key` / `batchdata_comps_at` dropped).

---

# SESSION 3 (2026-08-15) — desk slice 3: the saved determination

**Launch from** `~/crm-worktrees/lead-desk`. Prod is still **gw336 @ 098ca26c**;
this session's work is committed but **NOT deployed**.

## What shipped

- **`crm/api/price_determination.py`** (new) — `save_price_determination` /
  `get_price_determination`.
  - **The snapshot keeps the INPUTS and the CONSTANTS**, not just the offer.
    "We said $35,300" is unusable three weeks later without the comps, the $/sf
    and the repair level. `margin` and `fee` ride along because constants change:
    move the fee from $10k to $12k and a snapshot holding only inputs would
    silently re-derive to a number nobody ever said out loud.
  - **The server re-derives and REFUSES a mismatch** — not to impose today's
    formula (it uses the snapshot's own constants) but to catch a client whose
    offer does not follow from its own inputs. That failure is silent and it is
    a number a rep read to a seller.
  - **Comps are COPIED, not referenced.** `CRM Comp` is a projection of a feed
    that re-syncs nightly, and a BatchData fallback comp has no CRM row at all,
    so a determination resolving comps by name would drift or empty out.
  - **The field is the current price; the TIMELINE is the history.** Every save
    also posts a Comment, so re-pricing after a repair walkthrough never erases
    what was said before. Best-effort — a timeline write never fails the click.
  - `modified` is deliberately allowed to move (unlike the Zillow/BatchData
    caches): this is a person pricing a deal, not the machine remembering.
- **`OfferRail.vue`** — Save / Re-save with a drift line ("Saved 2:32 pm at
  $58,000 — changed since."). Comparison excludes the server-stamped
  `by`/`at`/`source`, or every save would look instantly stale.
- **`LeadDesk.vue`** — the real `Activities.vue` as a `]`-toggled overlay,
  mounted lazily on first open and kept mounted after; `S` saves.
- Ops: **`scripts/setup_price_determination.py`** — RUN ON PROD ALREADY
  (`price_determination`, `price_determination_at` on CRM Lead). Every write is
  column-guarded, so the app was safe to deploy before it: with the fields absent
  the save still lands on the timeline and the rail says "recorded on the
  timeline only" rather than showing a saved state that vanishes on reload.

## Traps this session paid for

- **A `z-20` overlay LOSES to Leaflet.** `.leaflet-container` creates no stacking
  context and its panes carry z-index 400–700, so the map PAINTED over the left
  ~100px of the activity panel (the heading read "y") while the panel still
  hit-tested underneath — clicks landing where nothing was visible. Any overlay
  near this map needs `z-[1000]`.
- **CompsView does not fit a fixed-height host.** It was built as a full page:
  filter card + map + list is ~1,010px against the desk's 726px, so only 62px of
  the 320px property list was reachable and the wheel could not get to the rest.
  New **`fill` prop** (default off, so the three live surfaces are untouched):
  filters fold behind a "Filters (N)" toggle, map and list share the height and
  scroll themselves. Measured after: centre pane scrollHeight == clientHeight at
  1280×800.
- **PostHog's "Report a problem" tab sits ON the rail.**
  `button.ph-survey-widget-tab`, in a shadow root, `position:fixed`, 35px, right
  edge, vertically CENTRED — it landed on "Max offer", the one number said out
  loud. Shadow DOM means our CSS cannot move it and disabling feedback on the
  screen reps live in is the wrong trade, so the rail is 340px with a 40px right
  gutter (same ~288px of content as before). Verified: rail content ends at 1240,
  tab starts at 1245.
- **TOASTS NEVER RENDERED UNDER `yarn dev`, app-wide, and nothing said so.**
  frappe-ui's toast state is module-level; pre-bundling inlines it into
  `.vite/deps/frappe-ui.js` while `FrappeUIProvider.vue` (a .vue file, always
  served raw) imports `../Toast/index` directly — two instances, so every
  `toast.success()` pushed to an array no mounted `<Toasts>` was rendering.
  Production was always fine, which is the dangerous part: **all UI verification
  happens on the dev server, and an error toast that cannot appear reads as "no
  error"**. Fixed with `optimizeDeps.exclude: ['frappe-ui']`; verified by
  triggering CompsView's own "Comp hidden" toast before and after.
- **`verify_ui` can be killed mid-run** (exit 143) and then writes no report —
  but its screenshots survive in `.pi/verification/<ts>/` and were enough to
  finish the verdict. Check them before paying for a re-run.

## Verified

Backend on prod via `bench execute`, rolled back: fields present, `stored: true`,
`get_after: true`, an inconsistent offer refused, an unknown repair level
refused. UI at a real 1280×800: no page scroll, nothing clipped, ARV/offer
arithmetic correct, save → toast + "Saved 2:37 pm · offer $54,400", **the line
survives a full reload**, drift wording correct, panel overlays without the map
reflowing (identical rect before/while/after), all three hit-tests inside the
panel, and the determination visible in the timeline.

Everything written to prod lead **CRM-LEAD-2026-00854** during verification was
undone (2 comments deleted, `comps_hidden` / `comps_selected` /
`price_determination*` cleared); `verify_no_drift.py` PASSes.


---

# STAGING IS LIVE (2026-08-15)

    https://crm-staging.groundworkpro.com    87.99.154.150 (Hetzner cpx21, ash)
    v1.67.0-stg1 @ c62d089d (feature/lead-desk)
    Administrator password: crm-staging:/opt/frappe-crm/.env

**It is a LEADZOLO-ONLY box (2026-08-15, Lance's call), NOT a copy of prod.** It
was seeded from a scrubbed clone first; that was the wrong shape. His test leads
come from LeadZolo and Quo is not going on it at all, so the site was wiped:
**0 leads, 0 Server Scripts, and no `tabQuo Message` table at all.**
`scripts/provision_staging_leadzolo.sh` adds back only the intake path — 20 CRM
Lead custom fields, the Lead Webhook Log doctype, the `Leadzolo` lead source and
the `leadzolo-leads` script. The clone script still exists for when a data-shaped
box is wanted; it is simply not what this one is.

Two scripts in the ops repo, both idempotent:

    ./scripts/bootstrap_staging.sh          bare Ubuntu -> TLS-served CRM
    ./scripts/clone_prod_to_staging.sh      prod's data, sanitised on arrival
    ENV=staging FORK=<worktree> ./scripts/build_image.sh     deploy a branch

**The scrub is a mechanism, not a habit.** It runs inside the clone pipeline
before anything starts against the new data, and there is no mode that restores
prod unscrubbed. Phones become unroutable `+1555…` derived from the row's own
name (so records that shared a number still share one), contact emails become
`@example.invalid`, per-user sending lines are cleared, and the email queue is
emptied. Verified after the first clone: 876 leads, 593 buyers, 4,192 call logs,
4,403 texts, **0 real numbers**.

**Staging carries NO integration keys** and that is the whole safety story: every
integration is gated on a per-site `site_config` key, and a site created fresh
has none. The scheduler is disabled by default — enabling it is a deliberate act,
because `sequence_drain.drain_due` runs every minute.

## Traps the bootstrap paid for (they are all in the scripts now)

- **`docker compose run/exec -T` inside a heredoc-fed ssh script eats the REST OF
  THE SCRIPT**, because stdin *is* the script. It silently swallowed
  `mute_emails`, the seqdrain config and `up -d` on the first run, leaving a box
  with only db and redis up — and no error anywhere. Redirect `</dev/null`.
- **The `seqdrain` queue must be declared in `common_site_config`** or
  drain-worker crash-loops on "Queue should be one of short, default, long".
  `bench set-config -g workers.seqdrain.background_workers 1` does **not** create
  the nested dict: it writes nothing and reports nothing. Write the JSON.
- **nginx inside the frontend container caches `backend:8000`'s IP at startup**,
  so a backend started after it answers 504 until reloaded — exactly what a fresh
  bootstrap looks like.
- **`build_image.sh` had the prod tag pattern hardcoded** even after the env
  parameterisation, so `ENV=staging` would have read an empty CURRENT, computed
  `v1.67.0-gw1` and sed'd nothing: a no-op deploy reporting success. It also
  rewrote this repo's compose pin regardless of target, which would have shipped
  a staging tag back to prod.
- **A 4.2GB database is mostly one table.** `tabError Log` is 3.9GB of it (148
  rows), so the clone restores it — and the other log-shaped tables — as empty
  structure and moves ~250MB instead.


---

# TELNYX PREREQUISITES — DONE (2026-08-15)

All three prerequisites the plan called mandatory-before-any-Telnyx-traffic are
built, live on prod where they need schema, and verified equivalent. What is left
is Telnyx itself, which is blocked on two DECISIONS, not on code (open questions
6 and 7): the thread boundary during parallel running, and the exit condition.

## `crm/api/telephony.py` — the one place that knows whose line is whose

There were **NINE** separate `_last10`/`_digits` helpers in this app and they did
not agree. `activity_progress` and `today_pulse` matched a user's line by EXACT
STRING against `custom_quo_number`, so a line stored as `+16125551234` would
never have matched a call log carrying `6125551234`. It happens to work today
because both sides are E.164 — measured, 0 of 2,896 calls change attribution —
but that is luck, and Telnyx will not necessarily store numbers the way Quo does.

## Corrections to this file's own plan, both found by measuring first

- **`CRM Call Log.medium` is the discriminator, not `telephony_medium`.** Every
  one of the 4,192 rows already says `Quo`. No migration, no re-stamp.
- **Texts genuinely needed a column**, and it is backfilled — but the app treats
  a BLANK provider as Quo (`telephony.LEGACY_PROVIDER`), so a site that never
  runs the backfill still counts all 4,357 texts. A missing migration must not
  make history disappear.

## Trap

**`bench mariadb` runs in SAFE UPDATE MODE.** An `UPDATE ... WHERE provider IS
NULL` touches no KEY column, so it is refused with ERROR 1175 and exits 1 — and
with stderr hidden that is indistinguishable from a successful no-op. The backfill
reported "done" while 4,403 rows stayed NULL. Always `SET SQL_SAFE_UPDATES=0;`
first, and always read back the row counts.

## Ops

`scripts/setup_provider_columns.py` (run on prod) + the backfill it prints.


## Staging: LeadZolo-only, and what the round trip taught (2026-08-15)

**Which custom fields get installed is DERIVED FROM THE WEBHOOK**, not
hand-listed: a field is installed only if `leadzolo_webhook.py` references it (20
of the 43 in `site/custom_fields.json`). That is the rule that keeps the box to
one purpose as the export grows — the file also carries `User.custom_quo_number`,
`CRM Lead.quo_contact_id` and three CRM Call Log transcript fields, all
telephony, plus refund-pool fields for a feature deleted in gw226. A
hand-maintained exclude list would silently let the next one through.

Three failures that a "200 OK" check would have missed, all now handled by the
provisioning script:

- **Server Scripts are OFF unless `common_site_config` says
  `server_script_enabled`.** The script installs fine, is enabled, and simply
  never runs; the endpoint 417s with `ServerScriptNotEnabled`.
- **A missing master record is a HARD failure, not a blank field.** The first
  fire died with `Could not find Source: Leadzolo` — *after* the raw payload had
  been logged, which is exactly what the Lead Webhook Log exists for.
- **`CRM Lead Source` autonames on `source_name`, not `lead_source`.** Posting
  the wrong key returns "Source Name is required".

`sync_server_scripts.py`, `setup_lead_webhook_log.py` take their target from the
environment now (`CRM_SSH_HOST` / `CRM_SITE` / `CRM_BASE` /
`CRM_ADMIN_PASSWORD`), defaulting to prod. 48 other `setup_*.py` scripts still
hardcode prod's URL — parameterise them as they are needed, not speculatively.

**Verified end to end**: a LeadZolo-shaped payload created `CRM-LEAD-2026-00001`
with address / beds / baths / sqft / year / campaign / vendor id all in the right
fields, and the payload logged. `lead_owner` is NULL because the round robin is
config-gated and staging has no roster — correct for a test box.

The scheduler is **paused** (`pause_scheduler: 1`); intake does not need it, and
`sequence_drain.drain_due` runs every minute when it is on.


## Neighbourhood layer on the desk (2026-08-15)

`crm.api.geo.get_neighborhood` now TRIMS and CAPS: 12 fields per home instead of
Redfin's whole record, `bbox` for what the rep is actually looking at, and
`MAX_FEATURES = 1500`. Measured on the Chicago lead: the full 2-mile radius is
1,806 homes / **384KB**, the same call with a ~450m bbox is 125 homes / **32KB**.
The response says `truncated` out loud, and the button reads
`Nearby (1500 of 1806)` when the cap bites — a count that does not match what is
on screen is worse than no count.

**Dots, not pills, and never comps.** Pill grammar means "comp" everywhere else
on this map, so the layer is grey canvas circles and every popup ends with
"Context, not a comp". Priced = filled, unpriced = hollow ring.

**Canvas, not markers** (`L.canvas`), because a warmed radius is ~1,800 points
here and 17,287 in Indianapolis — one DOM node each is the kanban's per-field
mistake, on a map somebody is dragging mid-call. Comp pills are markers
(pane z-600) and this is an overlay (z-400), so the answer stays above the
context with no per-layer reordering.

**Dot size follows zoom, and that is not cosmetic.** The desk opens at whatever
zoom fits the COMPS — zoom 12 on the test lead — where 28m/px turns 1.3km of
neighbourhood into a 50x50px smudge. First cut looked broken and was not: all
1,500 markers were drawing, correctly, into a blob. Radius now steps 1.5 → 3 → 5
→ 7 with zoom, re-applied on `zoomend`. Verified: 1 merged blob at default zoom
→ 33 resolvable dots at ~16px after three zoom clicks.

**Verified PASS** (desktop-chrome, 1280x800): default off, toggle on/off, pill
count unchanged at 83 throughout, comp popups still open, dot popups show
"no price on record" where there is none, zoom scales the dots, no console errors
from the layer.

### Still open

- **`geo_service_url` is NOT set on prod** — it was enabled only for this
  verification and turned off again. Setting it is the go-live act, and it does
  two things at once: it lets the desk read the neighbourhood, AND it arms
  `on_lead_insert` to warm every new lead (~75s of background sweep, real Redfin
  traffic). That is the intended design; it is a decision, not a deploy step.
- **`/parcels` returns 404** — never implemented in the service. Lot lines are
  the remaining half of workstream 1.
- The warmed radius on the test lead is only ~1.5km because the sweep was run
  at radius=800m during service bring-up, not the 2 miles the client asks for.

### Trap

**Cleaning up a docker-cp'd module deleted a file prod actually ships.**
`geo.py` is part of revision 098ca26c; `price_determination.py` is not. Removing
both "test" copies left production missing a module its lead-insert hook imports.
`verify_no_drift.py` caught it in the same minute — check whether a file belongs
to the deployed revision BEFORE deleting it from the container, and re-run the
drift check after any cleanup, not just after a deploy.


## Lot lines, and geo turned on (2026-08-15)

### The service grew the half it was missing

`/parcels` returned **404** — `crm/api/geo.get_parcels` had been calling it since
the client was written, and `store.parcels_in_bbox` had been ready the whole
time; only the route was missing. It takes a **bbox, not a radius**, because lot
lines are only legible zoomed in and what a caller wants is exactly the rectangle
on screen. 422 on a malformed, inverted or continent-sized box.

`/enrich` is separate from `/warm` **on purpose**: a sweep is ~75s, enriching
everything it finds is ~45 MINUTES at 6.6 parcels/sec. But nothing else called
it, so a warmed lead had dots and no boundaries — invisible until a rep zoomed in
mid-call to a bare map. **A sweep now enriches its own inner 600m
(`ENRICH_AFTER_SWEEP_M`)**: the block the house is ON is what gets looked at, and
the far edge of a two-mile radius is scraping nobody opens.

Measured: parcels **61 → 318 → 818 → 1,010**; `/parcels` 404 → 200 with 255
features carrying APN + FIPS; a fresh `/warm` produced its own enrich batch with
no second call.

### On the desk

Lot lines ride WITH the Nearby layer rather than getting their own toggle — same
question, one zoom level in — and only above **zoom 16**, where a 12m frontage is
~10px instead of ~5. Below it nothing is fetched: a request whose result cannot
be read is latency and scraping load for nothing. Debounced 400ms and keyed on
the rounded viewport, so panning back and forth does not re-fetch.

Thin, unfilled, slate: a lot line is a boundary, not an object, and filling it
would compete with the comp pills on the one screen where the pills are the
answer. Popup says **"Lot line · context, not a comp"**, same rule as the dots.

Verified live at zoom 16: **149 parcel paths** at exactly the intended style
(`#475569`, w1, o0.55) plus the 3 distance rings; zoom out to 15 → **0**; back to
16 → **149**; popup read `120 W 108th Pl · APN 25164090280000 · Lot line ·
context, not a comp`.

**GOTCHA — rapid zoom clicks are swallowed.** Five `.leaflet-control-zoom-in`
clicks in one tick advanced the map ONE level, which made the threshold look
broken while it was working. Leaflet's zoom animation eats clicks fired inside
it; pause ~700ms between them when driving the map from a script.

**GOTCHA — `performance.getEntriesByType('resource')` reported 0 calls to an
endpoint that had demonstrably run.** Its buffer caps at 250 entries and silently
drops the oldest — the same trap the kanban work hit. Count with a `fetch` wrapper
or trust the DOM.

### geo is ON in prod

`geo_service_url = http://172.20.0.1:8110` is now in prod's site_config, so
`on_lead_insert` warms every new lead and its block gets lot lines. Verified
through the DEPLOYED client: `warm_lead` on a real lead returned `queued: true`
and the sweep landed.

**Measured, and worth watching**: that one 2-mile warm returned **29,706 homes in
69 calls** (properties 2,213 → 30,113). At ~13 leads/day that is a few hundred
thousand rows a day, ~2.4GB/month at a rough 200 bytes a row, against 51GB free.
`save_properties` upserts on `property_id`, so overlapping neighbourhoods dedupe
rather than multiply — but this is the first thing to look at if the box gets
tight.
