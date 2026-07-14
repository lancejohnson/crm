# InvestorLift ↔ Frappe CRM dispo integration — implementation plan

Branch `feature/investorlift-dispo` (worktree `../frappe-crm-il-dispo`). Companion
ops work lands in `../frappe-crm-deploy`. Design approved 2026-07-13 (see the
`investorlift-dispo-integration` memory for the 4 rounds of UI iteration); this doc
is the build plan.

## What we're building (recap of the approved design)

Everything lives **on the Lead page** — Groundwork runs the whole lifecycle on
`CRM Lead` (zero `CRM Deal` records). A property that's out for disposition gets:

1. **Marketing dashboard** in two places on the lead: a **header block** atop the
   Activity feed (styled like the To-do block) and a **sidebar card** (the
   `<XxxCard :lead>` pattern). Both show the InvestorLift marketing metrics
   (SMS/email sent · delivered · clicked · CTR · unsub) + an **admin listing link**.
2. **A "Dispo" tab** in the lead's own tab bar (Activity · Emails · … · **Dispo**).
   Clicking it turns the main area into the **buyer board for this property** — the
   stock `KanbanView` pointed at the buyer-relationship doctype, filtered to this
   lead, grouped by per-property **interest stage**. Columns via ⋯ → Edit Statuses,
   card fields via Kanban settings (nothing custom).
3. **Buyer page** = the same detail shell as a lead (LayoutHeader + tabs +
   Activities timeline, so buyer texts/calls/recordings render for free) with a
   buyer-shaped sidebar (identity + ＋Quo, profile card with type tags + deal
   history + verified, "Engaged deals" back-links).

## Verified technical facts (live, account 447403 / user 458450)

- **admin.investorlift.com = Laravel JSON API, JWT bearer.**
  `POST /api/auth/login {email,password}` → `{access_token (30-day JWT),
  token_type:"bearer", expires_in:2592000, session_id, codesAlmostUsed}`.
  Reads: `GET /api/properties?filter[account_id]=447403&with=notifications_stats;dispositions_manager`
  and `GET /api/properties/{id}?with=notifications_stats`. Admin link =
  `https://admin.investorlift.com/properties/{id}/edit`. Creds in gwk Infisical
  `INVESTORLIFT_USERNAME` / `INVESTORLIFT_PASSWORD` → mirror into prod site_config
  `investorlift_username` / `investorlift_password` (the quo_api_key / gemini pattern).
- **`notifications_stats` shape** = the admin "Marketing Metrics" panel 1:1:
  `{sms:{plan_count,count_delivered,count_clicked,count_clicked_unique,count_unsub,ctr},
  email:{...}, total:{...}, total_amount}`.
- **2FA**: login *sometimes* SMS-challenges a code to Lance's Quo line
  **(651) 390-7073 = OpenPhone number id `PNBNmJTJgo`** (same workspace as our
  `quo_api_key`). Confirmed we can list that line's conversations/messages via the
  OpenPhone API → **the code is auto-retrievable, no human needed**. Extractor MUST
  scope to messages whose `updatedAt/createdAt` is *after* login was triggered
  (historical "Property Leads" texts on that line prove a naive "latest
  conversation / any digits" grab is wrong) and prefer messages matching
  `/code|verif|investorlift|otp/i`. Exact 2FA challenge/verify endpoint shape is
  still unknown (didn't fire on the validation login) → the client logs the full
  2FA response the first time it fires and we finalize the verify call then; until
  then it falls back to manual code entry in the UI.
- **Buyer board / message threads = investorlift.ai, RSC-only** (Next.js, no JSON
  API). This is the only piece that needs a **headless browser (Playwright)** — it's
  Tier 2, built last.

## Tier split

- **Tier 1 — clean API, cron, no browser**: property link + marketing dashboard +
  admin link + listing status. Fully server-side.
- **Tier 2 — RSC, needs a browser**: buyer cards (type tags, deal history, verified),
  buyer↔us message threads, buyer identity for Quo. Playwright worker.

## Data model (ops doctypes)

- **`CRM Buyer`** (global, one per person): `buyer_name`/`first_name`/`last_name`,
  `phone`, `email`, `buyer_type` (Small Text — comma tags: Cash Buyer/Realtor/…),
  `verified` (Check), `deal_history` (Data, e.g. "6 Flips 22 Holds"),
  `il_buyer_id` (unique), `last_active` (Datetime). Autoname by `il_buyer_id` else
  hash. Sales-role perms. Buyer page routes here.
- **`CRM Lead Buyer`** (the per-property relationship the Dispo kanban groups on):
  `lead` (Link CRM Lead), `buyer` (Link CRM Buyer), `interest_stage`
  (Select — the kanban columns: `New\nAttempted\nEngaged\nHot\nOffer\nPassed`),
  `direction` (Select Inbound/Outbound), `message_count` (Int), `last_active`
  (Datetime). Denormalize `buyer_name`/`buyer_type`/`phone`/`deal_history`/`verified`
  via `fetch_from` the buyer link so stock kanban card fields work with no custom code.
  Kanban = this doctype filtered to `lead == <this lead>`, group_by `interest_stage`.
- **Lead marketing fields** (custom fields on `CRM Lead`, mirror the tax-writeback
  pattern — read_only so they auto-hide until filled): `il_property_id` (Data),
  `il_status` (Data — available/pending/sold), `il_admin_url` (Data),
  `il_sms_sent`/`il_sms_delivered`/`il_sms_clicked`/`il_sms_unsub` (Int),
  `il_sms_ctr` (Percent), `il_email_sent`/`il_email_delivered`/`il_email_clicked`
  (Int), `il_marketing_synced_at` (Datetime). `il_property_id` set = "Active Dispo"
  (gates the header block, sidebar card, and Dispo tab).
- **`IL Connection`** (Single): `token` (Long Text), `token_expiry` (Datetime),
  `last_login_at`, `twofa_status` (Select ""/pending/failed), `twofa_requested_at`,
  `twofa_manual_code` (Data — Lance's fallback entry). App-code-owned auth state.
- *(Tier 2, later)* **`CRM Buyer Message`** — buyer↔us texts scraped from
  investorlift.ai, rendered in the buyer's Activities timeline like Quo Messages.

## App-code modules (this repo)

- **`crm/api/investorlift.py`** — the core. `_client()` returns a small IL API
  client: `login()` (handles 2FA via `_twofa` below, caches token on `IL Connection`),
  `get_token()` (cached-or-refresh), `list_properties()`, `get_property(id)`.
  Whitelisted endpoints: `search_properties(q)` (address search to link a lead),
  `link_property(lead, il_property_id)`, `sync_marketing(lead)` (on-demand refresh),
  `get_marketing(lead)` (read for the card/header), `get_connection_status()` +
  `submit_2fa_code(code)` (manual fallback). Scheduler `sync_all_marketing`
  (hourly/daily_long) loops linked leads → writeback + `crm_il_sync` realtime.
- **`crm/api/investorlift_2fa.py`** — `fetch_2fa_code(since_ts)`: poll OpenPhone
  line `PNBNmJTJgo` conversations updated after `since_ts`, pull their incoming
  messages, return the first code from a message matching `/code|verif|investorlift|otp/i`.
  Reused by `login()`. Manual fallback reads `IL Connection.twofa_manual_code`.
- **`crm/hooks.py`** — add `sync_all_marketing` to a scheduler bucket (remember the
  gw127/128 gotcha: a new scheduler hook needs `bench execute …sync_jobs` on prod).
- *(Tier 2)* **`crm/api/investorlift_ingest.py`** — `ingest_buyers(lead, buyers[])`,
  `ingest_messages(...)` upsert endpoints the Playwright worker POSTs to.

## Frontend (this repo)

- `components/InvestorLiftCard.vue` — sidebar marketing card (mirrors TaxInfoCard).
- `components/Activities/DispoHeaderBlock.vue` — the header-block dashboard
  (mirrors TaskTodoList's frame), shown atop the Activity feed when Active Dispo.
- `pages/Lead.vue` — mount the card + header block + a **Dispo tab** (visible when
  `il_property_id` set) whose panel renders the buyer `KanbanView` filtered to the lead.
- `components/Settings/InvestorLiftSettings.vue` — connection status + a **2FA
  code entry** field (the "see if it asked for 2FA" surface) + link-property tool.
- Buyer page: reuse the lead detail shell against `CRM Buyer` (later phase).

## Build phases (order of execution)

1. **Foundation (this repo, no prod writes)** — `investorlift.py` client +
   `investorlift_2fa.py`, verified read-only against live. ← starting here.
2. **Ops doctypes + site_config** — `setup_investorlift.py` (CRM Buyer, CRM Lead
   Buyer, lead marketing fields, IL Connection) + `bench set-config` the creds.
3. **Marketing dashboard (Tier 1 UI)** — sidebar card + header block + admin link +
   link-property tool + hourly sync + `crm_il_sync` realtime. Ship + verify live.
4. **Dispo tab + buyer board** — the stock kanban on CRM Lead Buyer, Dispo tab in
   Lead.vue. (Buyers seeded manually/by Tier 2.)
5. **Buyer page** — lead-shell detail view on CRM Buyer.
6. **Tier 2 scraper** — Playwright worker (ops) → `investorlift_ingest.py` upserts
   buyers + interest stages + message threads into the buyer Activities timeline.

## 2FA UX (Lance's "one big thing")

Cron token refresh runs every 30 days; only *then* can 2FA fire. When it does:
`login()` sets `IL Connection.twofa_status='pending'` + `twofa_requested_at`,
publishes `crm_il_2fa` realtime, and **auto-polls OpenPhone `PNBNmJTJgo` for the
code** (≤120s). If auto-retrieval succeeds the login completes silently. If it
fails, status stays `pending` and **Settings → InvestorLift shows a banner + a code
entry field**; Lance types the code from his phone, `submit_2fa_code()` resumes the
login. Either way, the system *always surfaces* that 2FA was asked for.
