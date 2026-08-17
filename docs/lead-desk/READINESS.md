# Lead desk — everything still needed before it is "ready"

**Status 2026-08-17.** The desk is deployed to PRODUCTION (`v1.67.0-gw337 @
88f4b10b`) and reachable at `/crm/leads/<id>/desk`, but **nothing links to it**,
so no rep can find it. That is deliberate for now: it means the deploy is inert
until we decide it is ready.

This file is the complete list. It is ordered by what blocks a rep from working a
live seller call, not by effort.

---

## 0. Where it gets tested — decide this first

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

- [ ] **Entry point on the Lead page** (`Lead.vue` header row or More ▾).
- [ ] **Entry point from the Today board** — the card, and/or "Open desk" in
      `TodayLeadModal`, which is where a rep actually starts a call.
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
