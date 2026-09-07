# Next workspace — production rollout (Lance only)

The UI and APIs live on app branch `feature/next-workspace`. Ops scripts on
ops branch `feature/next-workspace`. Mattermost forwarder on
`feature/crm-sync-forwarder`. **Nothing is live until these steps run.** The
allowlist is the gate: everyone else keeps the classic layout.

## 0. Merge to `groundwork` (do not skip)

`build_image.sh` refuses a linked worktree unless `ALLOW_WORKTREE=1`. Prefer:

    cd /Users/work/Projects/Groundwork/frappe-crm-app
    git checkout groundwork
    git merge --no-ff feature/next-workspace

Then deploy from that checkout. Ops: merge `feature/next-workspace` there too.
Mattermost: merge `feature/crm-sync-forwarder` before enabling the forwarder.

## 1. Image

From `frappe-crm-deploy`:

    ./scripts/build_image.sh
    ./scripts/smoke_test.py

Frontend-only cache skip is fine if python didn't change since last build —
this change includes both.

## 2. Site schema (idempotent, on the prod backend)

    bench --site crm.groundworkpro.com execute frappe_crm_deploy path…

Practically, copy and run from the ops repo **on the host**, same as other
setup scripts:

    scripts/setup_talk.py
    scripts/setup_notification_types.py
    scripts/setup_phone_lines.py

Guarded: the app deploys before these exist (`has_column` / `exists`).

## 3. Site config (allowlist first)

    bench --site crm.groundworkpro.com set-config crm_next_users '["lance.johnson@groundworkpro.com"]' --parse

Generate and set `mattermost_sync_secret` (do **not** `set-config` the Pi
Mattermost token from a laptop — the host timer owns `mattermost_token`).
Per-rep PATs already live in `mattermost_user_tokens`.

Do **not** set anyone else's `crm_workspace_version`. Lance flips it from the
user menu once he sees the switch.

## 4. Telnyx — new "Groundwork CRM" resources, not the test ones

Do **not** repoint Quo numbers or `Groundwork CRM (test)` (+1 651 382 0252).
Provision a **new** call control app, messaging profile, credential connection,
outbound voice profile, and number named **Groundwork CRM**, webhooks:

    https://crm.groundworkpro.com/api/method/crm.integrations.telnyx.webhook.messaging
    https://crm.groundworkpro.com/api/method/crm.integrations.telnyx.webhook.voice

Then site_config the new ids (`telnyx_connection_id`, messaging profile, etc.).
A dedicated `scripts/provision_telnyx_prod.py` is still missing — do this by
hand against the Telnyx API / console until that script exists.

## 5. Mattermost forwarder (optional until Talk posts should round-trip)

On groundwork-apps, drop-in for `mm-pi-listener.service`:

    CRM_SYNC_URL=https://crm.groundworkpro.com/api/method/crm.integrations.mattermost.webhook.event
    CRM_SYNC_SECRET=<same as mattermost_sync_secret>

Off unless **both** are set. HMAC is hex SHA-256 of the raw body; header
`X-Groundwork-Signature` (bare hex or `sha256=` prefix both accepted).

## 6. Smoke (Lance only)

- A non-allowlisted user: classic sidebar, no phone dock, no Talk nav, no
  "Try the new workspace".
- Lance: menu shows the switch. Classic still works. "Try the new workspace"
  mounts Talk + phone dock.
- Talk lists seeded channels. A post from CRM appears in Mattermost; a post
  from Mattermost appears in Talk (once the forwarder is on).
- Live-one from the dock lands as a CRM notification + Talk DM + Mattermost DM.
- Dial / inbound / Join monitor→whisper→barge: seller hears no join beep; the
  rep hears the tone. Recording starts at bridge when the line says so.
- `?phonePreview=1` still loads the **fictional** mockup, not this backend.

## Rollback

    bench --site crm.groundworkpro.com set-config crm_next_users '[]' --parse

That hides next for Lance too. Image rollback is the previous `gwN` pin.
