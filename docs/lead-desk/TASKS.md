# Lead desk — tasks

Split from the v17 mockup. Design reference: `docs/lead-desk/mockup/v17.html`
(working copy also at `/Volumes/Projects/crm-mockups/today-leadzolo/v17.html`).

One CRM, one set of features. Today and Leads are different *shells* for the
same desk — a modal on Today, a page/modal on a lead — not two implementations.

## 1. AI price analyzer

Shows on Today. Leaves its reasoning on the comps map too.

## 1B. Repair range calculator

Formula from v17. Covers “really bad” vs in-between, not a single point estimate.

## 2. Comp map

Set up the way the mockup wants it. Same map on Today and Leads; only the
chrome around it differs.

## 3. Phone system (Telnyx)

Replaces Quo for live calling. Own project; unblocks streaming AI.

## 4. Streaming AI

Live copilot on the call. Blocked on Telnyx media streaming.

## 5. Revamped Today

Look like the mockup. Incorporate 1–4 rather than growing a third surface.

## How we ship these

Work a feature branch → deploy to **staging** (`ENV=staging FORK=…`) → merge
to `groundwork` → deploy prod. Staging is prod’s schema and statuses; only
the leads (LeadZolo) and the branch under test differ.
