# Requested CRM fixes — investigation (2026-09-01)

## Practice recording

- The Mattermost attachment is a 29.8-second bug-report video, not a backup recording.
- `PracticeRun.vue` allowed another property selection while `touch_property` and the previous recording rollover were still in flight. Responses could land out of order and replace the current per-listing clock with an older property response.
- `practiceRecorder.js` also allowed concurrent `beginPropertyRecording` calls to share and overwrite `recorder`, `propertyId`, `queue`, and `seq`.
- Window capture had been replaced by a current-tab-biased `getDisplayMedia` call (`preferCurrentTab`, `selfBrowserSurface: include`). Closing a shared Zillow tab ends that capture.
- The actual recoverable files are on the app server. Attempt `4hq25i5q59` has canonical recordings for `ri612pe0tg` (45,287,440 bytes) and `rn15bm8416` (90,174,031 bytes) even though their JSON result stamps are absent.
- Recovery exposed the final root cause: `finish_recording` inserted a Frappe `File` row for the assembled take. Frappe applies the site's 25 MB upload ceiling to that existing on-disk file, so 45–90 MB recordings failed after upload but before their JSON stamp. Playback already uses the guarded Range endpoint, so finalization must stamp the canonical path without creating a `File` row.

## Comps shortcut

`useKeyboardShortcuts` matches `e.key` without rejecting modifiers. Therefore Cmd+F and Ctrl+F match the Comps bare-F definition and toggle full-map mode before/alongside browser Find.

## Refund workflow

- The Refunds board includes only `custom_refundable=1`; status does not matter.
- Existing lead-page controls are discoverable only in the lost/refund-pool banner. A live Follow Up lead can be eligible but has no obvious refund action.
- No field distinguishes the normal provider refund form from a general support ticket filed because the lead was missing.
- Production examples:
  - John Somerville `CRM-LEAD-2026-00966`: refundable/requested, Waiting on us, three inbound Zendesk Communications, no draft/outbound email.
  - William Kellum `CRM-LEAD-2026-01102`: manually submitted, but still To Request.
  - David Smith `CRM-LEAD-2026-00988`: manually submitted while Follow Up; `custom_refundable=0`, so absent from Refunds.
  - Timothy Arter `CRM-LEAD-2026-01091`: manually submitted and later reconciled Complete, but had no manual-ticket marker.
- `EmailThread.vue` replaced individual `EmailArea` cards and omitted their Reply actions. `Activities.vue` auto-opens a composer only when `custom_refund_draft_json` exists, so John’s no-draft inbound thread cannot be answered.

## Task scheduling

The same `CRM Task` is created through four competing models: inline To-do, XL TaskModal, global Tasks, and telephony task panels. The record page duplicated inline add with New → Task and the Tasks-tab create button. Due chips silently created a generic “Follow up” if title was blank, while Enter created a task with no date. Task-title click renamed inline, while a hover-only icon opened scheduling details (not discoverable on touch). Modal-created record tasks defaulted to Backlog; inline tasks defaulted to Todo.

## Denise Curry Today error

The screenshot error is: `Outcome cannot be "Dead lead". It should be one of "", "Connected", "No Answer", "Left a Voicemail", "Booked an Appointment", "Other".` App validation correctly permits `Dead lead` for Skipped, but the custom DocType Select field contains only the original Done values. Frappe rejects the valid skip during `doc.save()`. The setup script also failed to update options on an existing field.

## Duplicate refund credit

Star Ma ticket 153380 produced two distinct completion emails five minutes apart (“money added” and “ticket refunded”). `refund_mail_poll.py` notifies for every message classified `complete`, even when `next_status()` returns no transition because the lead is already Complete. Gmail-message dedupe cannot prevent semantic duplicates across different messages; the notification must be gated on the transition to Complete.
