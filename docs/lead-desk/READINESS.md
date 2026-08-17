# Lead desk — everything still needed before it is "ready"

**Status 2026-08-17.** The desk is deployed to PRODUCTION (`v1.67.0-gw337 @
88f4b10b`) and reachable at `/crm/leads/<id>/desk`, but **nothing links to it**,
so no rep can find it. That is deliberate for now: it means the deploy is inert
until we decide it is ready.

This file is the complete list. It is ordered by what blocks a rep from working a
live seller call, not by effort.

---

## 0. What crm-test IS — corrected 2026-08-17

**crm-test is production's build and schema with LeadZolo data only.** It is not
a reduced product. I had built it the other way — 20 custom fields and one server
script — which proves nothing about the site reps use, because a desk tested
against a site missing the comp inventory and half the doctypes is not the desk.

Fixed the same day:

- `provision_staging_full.sh` runs **every** `setup_*.py` against crm-test
  (41 of 44 applied; `setup_quo_webhooks` deliberately skipped — it would point
  production's telephony at the test box). 35 scripts had prod's URL hardcoded and
  now read `CRM_BASE` / `CRM_ADMIN_PASSWORD`, defaulting to prod.
- **69,440 `CRM Comp` rows copied** from prod. They are a projection of the
  iSpeedToLead feed with no seller PII, and without them the desk has nothing to
  price from.
- Same build deployed: **stg2 @ 36e2e1e0** against prod's gw337 @ 88f4b10b.
- LeadZolo leads already flow there (`crm_push` with `CRM_HTTP_BASE` set).

Still missing for true parity: `rapidapi_zillow_key`, `batchdata_comps_api_key`
(spends money — decide the ceiling), a geo service reachable from that box, and
the `CRM Sequence*` doctypes (2 setup scripts still fail on them).

## 0b. Where it gets tested — decide this first

The desk has only ever been exercised through the **prod-backed dev server**
(`CRM_DEV_TARGET=https://crm.groundworkpro.com yarn dev`), because it needs real
leads, real comps and real geocoding to mean anything.

- [ ] **Decide: staging or prod-backed dev.** crm-staging CANNOT host the desk
      today — 2 leads, **0 `CRM Comp` rows**, no `rapidapi_zillow_key`, no
      `batchdata_comps_api_key`, and no geo service reachable from that box (geo
      runs on the prod host, bound to the prod CRM's docker bridge).
- [ ] If staging: it needs a comps dataset (67k `CRM Comp` rows, or a ZIP-scoped
      subset), the two API keys, its own geo service + PostGIS, and lead data
      with real addresses. That is a project in itself, not a config change.
- [ ] **Rollback decision on gw337** — either roll prod back to gw336 and treat
      the desk as staging-only, or leave it deployed-but-unlinked. Both are
      defensible; drifting between them is not.

## 1. Nobody can reach it

**Corrected 2026-08-17 — the desk IS the Today card's screen.** Lance: "this is a
new screen for the cards for the Today modal", and the mockup said so all along
(v17 is a `<div class="modal">`; the folder is `today-leadzolo`). Building it as
a standalone page was the mistake; a rep works a QUEUE of cards, and a different
URL per card loses the queue.

- [x] **Desk pane in `TodayLeadModal`** — same `CompsView` (fill + neighbourhood)
      beside the same `OfferRail`, so page and modal share one implementation.
      Left rail hides on that pane, dialog widens to 7xl, card context (status,
      "Call N of M", why today) stays in the header. **Verified on crm-test**
      against a LeadMarket-pushed lead: card -> modal -> Desk, 8 comps + Subject
      pill, ladder notice, offer rail, and pane switching that keeps the map
      mounted (868x240 before and after a round trip through Activity).
- [ ] **The map is short in the modal** — 240px, its `fill`-mode minimum, because
      the modal body is 704px against the page's 800. Usable, but the list could
      give the map back some height here.
- [ ] **Entry point on the Lead page** (`Lead.vue` header row or More ▾) — still
      worth having for a lead not on today's board.
- [ ] **Resolve from the desk**: Done / Skip / outcome still live on the card
      behind the modal, so a rep who prices in the desk must close it to
      disposition.
- [ ] **Mobile decision.** `MobileLead.vue` is a separate page and has no path to
      the desk. The desk is desktop-only by design (h-screen, ~1280x800); say so
      explicitly rather than leaving a dead end on a phone.
- [ ] **Permissions**: today any user who can read a lead can open the desk.
      Decide whether that is right before it is linked.

## 2. It is not yet a CALL surface

- [ ] **Call / text controls on the desk.** v17 has "Start call"; today a rep
      would leave the screen to dial, which is the one thing this screen exists
      to prevent.
- [ ] **"They want" (the seller's ask)** and the gap against our offer. Already
      in the saved snapshot's schema (`ask`); not built.
- [ ] **Disposition after the call** — the desk cannot mark a Today card
      Done/Skipped, so working from it leaves the board stale.
- [ ] **Copilot** — blocked on Telnyx, and Telnyx is blocked on two decisions
      (thread boundary during parallel running, exit condition).

## 3. The comping method — the open design question

The current method is: **mean $/sf of the ticked comps x subject sqft, rounded to
$1,000**. Every item below is a real defect in that, not a refinement.

- [ ] **Mean vs median (or trimmed mean).** One outlier moves the ARV, and the
      comp sets here are wide.
- [ ] **No adjustments.** A 3/2 1,400sf comp and a 2/1 900sf comp contribute
      equally per square foot. Either adjust, or gate the ARV on the "similar"
      tier of the preset ladder and say which tier produced it.
- [ ] **BASIS IS MIXED, and this is the sharpest one.** Our pooled `CRM Comp`
      inventory is the **last ASK**; the BatchData fallback is a **recorded
      sale**. The same-looking ARV therefore means different things depending on
      which source filled the map, and nothing on screen distinguishes them.
- [ ] **Active listings sit in the same average as off-market rows** — "what
      someone wants" blended with "what left the market".
- [ ] **Subject sqft provenance is invisible.** When Zillow has no number it
      comes from a pick-list band ("1000 - 2000"), and the ARV silently inherits
      that uncertainty. The rail shows "$X/sf x Ysf" but not where Y came from.
- [ ] **Minimum comp count.** Nothing stops a rep pricing off one comp.
- [ ] **Decide whether ARV should be editable** with the derived number as the
      default, the way a human underwriter would override it.

## 4. Data coverage

- [ ] **`warm_backfill` for the 362 live leads.** Only leads warmed since geo went
      on have a neighbourhood; everything older shows an empty "Nearby". This is
      hours of background sweeping — stage it overnight and check the box after.
- [ ] **Parcels only cover the inner 600m** of a sweep (`ENRICH_AFTER_SWEEP_M`).
      Confirm that is the right trade before reps rely on lot lines.
- [ ] **18% of leads have ZERO pooled comps** and fall through to BatchData at
      ~$0.30-0.75 each. Decide the monthly ceiling and whether to alert on it.
- [ ] **Geo DB growth.** One 2-mile warm stored **29,706 rows**. At ~13 leads/day
      that is a few hundred thousand rows a day (~2.4GB/month against 51GB free).
      Needs a retention or pruning policy before it is a surprise.

## 5. Reliability and ops

- [ ] **geo-api runs on the SAME BOX as production**, with no healthcheck beyond
      systemd `Restart=` and no alerting if it dies or gets WAF-blocked. A dead
      geo service degrades the desk silently.
- [ ] **The geo PostGIS database is in no backup routine.**
- [ ] **Redfin WAF/rate limits**: `enrich_near` stops cleanly on a 403 and reports
      it, but nothing tells a human. If we get blocked, lot lines quietly stop
      appearing.
- [ ] **`maps_embed_key` has never moved into site_config** (it lives at
      `~/.config/groundwork/maps_embed_key`), so Street View cannot ship.

## 6. Product polish that is not optional for a live-call surface

- [ ] **Shortcuts are undiscoverable** — `S` save, `]` activity, `N` nearby, `D`
      details, `H` hide, `U` use all work and nothing says so. Command palette has
      no desk entries.
- [ ] **Empty states**: a lead with no coordinates, no comps, or no geo warm each
      need a sentence that says which of those it is, not a blank map.
- [ ] **Determination history** is only visible as timeline comments; there is no
      "what did we say last time, and what changed".
- [ ] **Street View** (v17 has it; key blocked as above).

## 7. Verification still owed

- [ ] **A real lead a rep is actually calling**, not the Chicago test lead
      (CRM-LEAD-2026-00854) that every check so far has used.
- [ ] **A lead with NO comps and NO geo**, to see the degraded desk end to end.
- [ ] **A rep walkthrough** — German or Exe on a live call, watching where they
      stall. Everything above is my model of the work, not theirs.


---

# What else is needed — beyond the list of 2026-08-17

Lance's list: comping method/tool (+ comp condition evaluation, + a short
explanation of the reasoning), Telnyx calling and texting, a parcel-line toggle
on the comp map, and a live-streaming chatbot with quick buttons and typed input.
Everything below is ADDITIONAL, and ordered by how badly it breaks the method if
it is missing.

## The sharpest gap: we do not hold SOLD data

The method described is "what sold recently and nearby, worked back into what
this would sell for fixed up". **Our pooled `CRM Comp` inventory is the last ASK,
not a sale** — an off-market row means "it left the market", not "it closed at
this price". The BatchData fallback IS recorded sales, but it only fires for
leads with zero pooled comps.

So the primary source does not contain what the method needs. Decide one:

- [ ] buy sold data for every lead (BatchData comparables at ~$0.30-0.75/lead,
      not just the empty ones);
- [ ] pull sold events per property from Zillow `priceHistory` (1 billed call per
      property, already proven for the subject);
- [ ] keep the ask-based index and apply an explicit, stated haircut.

Whichever, the ARV must **say which basis it used**. Same number, different
meaning, is the failure mode to design out.

## The offer is only half ARV

- [ ] **Repairs are a 3-button matrix** (Smooth / Shiver / Abandon + majors). For
      fix-and-flip that is the weakest input in the formula, and it is doubled.
      The condition tool wanted for COMPS is needed for the SUBJECT too.
- [ ] **Seller photos already land in Drive** (Photos card) — that is the obvious
      feed for a subject-condition read.
- [ ] **Subject facts are often wrong and the ARV inherits it silently.**
      Measured: seller said "1000-2000 sqft, 1970-1980"; Zillow says 924 sqft,
      built 1993, Manufactured. A confirm-the-facts step belongs in the call.

## Comp condition evaluation has a cost model

- [ ] Photos are ~1 billed Zillow call per comp plus a vision pass per comp.
      Twenty comps per lead is not free. Pre-compute for the shortlist only, cache
      like the Zillow facts (30 days), and decide the per-lead ceiling.

## The call does not end at the number

- [ ] **Disposition from the desk** — it cannot mark a Today card Done/Skipped,
      so a rep working here leaves the board stale.
- [ ] **Offer into a contract**: the DocuSeal purchase-agreement flow exists;
      the desk should hand it the price it just computed.
- [ ] **Task / follow-up** from the desk, or the cadence silently degrades.

## Copilot: the parts that are not the model

- [ ] **Grounding and refusal.** "Do not give wrong information" needs a
      mechanism: answer only from the desk's own data (comps, subject facts,
      transcript) and say so when it cannot.
- [ ] **Latency budget.** An answer 4s late in a live call is worse than none.
- [ ] **Where the media-stream consumer runs** — Telnyx needs a reachable
      websocket; that is a new always-on service (open question 5 in PLAN.md).
- [ ] **RECORDING CONSENT.** Live transcription in two-party-consent states is a
      legal question, not a technical one, and it applies the moment the stream
      is opened.
- [ ] **Cost per call**: Telnyx minutes + streaming STT + LLM tokens. Should be a
      known number before it runs on every call.
- [ ] **Kill switch** — per-user and global, without a deploy.

## Telnyx, beyond "calling and texting"

- [ ] The provider code itself (`crm/integrations/telnyx/`, `TelnyxCallUI.vue`,
      settings doctype). The three prerequisites are done: provider-agnostic DNC,
      the `provider`/`medium` discriminators, and the shared attribution chain.
- [ ] **Number porting plan** — sellers have our current numbers saved.
- [ ] **Parallel-running exit condition** (open question 7).
- [ ] Rebuild on Telnyx what Quo gives us today: recordings, transcripts,
      chapters, the AI call review, call classification.

## Everything must degrade without blocking a live call

- [ ] Zillow, BatchData, geo and Telnyx all sit in the desk's path. Each needs a
      timeout and a stated fallback, because the failure lands mid-sentence.

## How we will know it worked

- [ ] Offers made per call, time-to-offer, contract rate. Without them this is a
      screen we like rather than a screen that works.
- [ ] A rep walkthrough (German or Exe) on a live call before it is linked
      anywhere.
