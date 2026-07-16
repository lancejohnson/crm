"""Two-way CRM Buyer <-> Quo (OpenPhone) contact sync.

Leads already sync one-way to Quo contacts via the ops "Quo Contact Sync"
server script; buyers had nothing, so the team hand-typed buyer contacts in
Quo ("Manny - Chicago Buyer") to see names on calls/texts. This module makes
CRM Buyer the peer of a Quo contact:

- **Push** (buyer -> Quo): on buyer create/edit, create or update the linked
  Quo contact (name, phone, email, tags) so every buyer's number shows their
  name in the Quo apps. Existing hand-made Quo contacts are ADOPTED by phone
  match instead of duplicated.
- **Pull** (Quo -> buyer): a 10-min scheduled reconcile (`sync_all`) pages the
  whole contact list and pulls team edits back — names, and the "Contact"
  multi-select custom field (the team's tags, renamed from "Tags"), which
  mirrors two-way with `CRM Buyer.quo_tags`. A Quo contact tagged or named
  "buyer" that matches no CRM buyer is pulled IN as a new CRM Buyer.
- Engaged property addresses are pushed one-way into the Quo "Property"
  multi-select so the team sees which deals a buyer is on.

API gotchas (learned the hard way, see the Quo Bruno QUIRKS.md):
- A PATCH replaces `defaultFields` WHOLESALE; a customFields-only PATCH
  returns 200 but wipes the phone numbers and the contact is then garbage-
  collected (every later GET 404s). Every PATCH here sends the full, merged
  `defaultFields` with item `id`s stripped (re-sending ids can 400).
- Multi-select custom-field values are free-form via the API; the field key
  is resolved per-workspace from /v1/contact-custom-fields.

Config: `quo_api_key` in site_config (already set for agreement notifications).
Fields (ops `setup_buyer_quo_sync.py`): CRM Buyer.quo_contact_id /
quo_synced_at / quo_tags. Everything no-ops until they exist.
"""

import json
import re
import time

import requests

import frappe
from frappe.utils import convert_utc_to_system_timezone, get_datetime, now_datetime

BUYER_DOCTYPE = "CRM Buyer"
API = "https://api.openphone.com/v1"
PAGE_SIZE = 49  # /v1/contacts rejects larger pages
THROTTLE = 0.13  # OpenPhone: 10 req/s

# the team's tag field was created as "Tags" and renamed "Contact" (same key)
TAG_FIELD_NAMES = ("contact", "tags")
PROPERTY_FIELD_NAMES = ("property", "properties")

# fields whose change should push the buyer to Quo
PUSH_FIELDS = ("buyer_name", "first_name", "last_name", "phone", "email", "quo_tags")

BUYER_WORD = re.compile(r"\bbuyer\b", re.I)


# --------------------------------------------------------------------------- #
# plumbing
# --------------------------------------------------------------------------- #
def _api_key():
	return (frappe.conf.get("quo_api_key") or "").strip()


def _enabled():
	return bool(
		_api_key()
		and frappe.db.exists("DocType", BUYER_DOCTYPE)
		and frappe.db.has_column(BUYER_DOCTYPE, "quo_contact_id")
	)


def _headers():
	# raw key, no Bearer; Cloudflare rejects the default python UA
	return {"Authorization": _api_key(), "User-Agent": "curl/8.1.0"}


def _req(method, path, **kwargs):
	kwargs.setdefault("timeout", 25)
	resp = requests.request(method, f"{API}{path}", headers=_headers(), **kwargs)
	time.sleep(THROTTLE)
	resp.raise_for_status()
	return resp.json() if resp.text else {}


def _data(payload):
	d = payload.get("data") if isinstance(payload, dict) else None
	return d if d is not None else payload


def _last10(number):
	return "".join(ch for ch in (number or "") if ch.isdigit())[-10:]


def _e164(number):
	d = "".join(ch for ch in (number or "") if ch.isdigit())
	if len(d) == 10:
		return "+1" + d
	if len(d) == 11 and d.startswith("1"):
		return "+" + d
	return ""


def _utc_to_sys(iso):
	"""OpenPhone UTC ISO timestamp -> naive system-tz datetime (Frappe style)."""
	if not iso:
		return None
	return convert_utc_to_system_timezone(get_datetime(iso.replace("Z", "+00:00"))).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# contact shaping
# --------------------------------------------------------------------------- #
def _all_contacts():
	out, token = [], None
	while True:
		params = {"maxResults": PAGE_SIZE}
		if token:
			params["pageToken"] = token
		body = _req("GET", "/contacts", params=params)
		out += body.get("data") or []
		token = body.get("nextPageToken")
		if not token:
			return out


def _custom_field_keys():
	"""{tag_key, property_key} for this workspace (either may be None)."""
	keys = {"tag": None, "property": None}
	try:
		rows = _data(_req("GET", "/contact-custom-fields")) or []
	except Exception:
		return keys
	for f in rows:
		if f.get("type") != "multi-select":
			continue
		name = (f.get("name") or "").strip().lower()
		if name in TAG_FIELD_NAMES and not keys["tag"]:
			keys["tag"] = f.get("key")
		elif name in PROPERTY_FIELD_NAMES and not keys["property"]:
			keys["property"] = f.get("key")
	return keys


def _contact_phones(contact):
	df = contact.get("defaultFields") or {}
	return [p.get("value") for p in df.get("phoneNumbers") or [] if p.get("value")]


def _contact_display(contact):
	df = contact.get("defaultFields") or {}
	return " ".join(x for x in ((df.get("firstName") or "").strip(), (df.get("lastName") or "").strip()) if x)


def _junk_name(display):
	"""The May-2026 bulk import left ~300 contacts literally named '*- *-'."""
	return not (display or "").replace("*-", "").strip()


def _contact_tags(contact, tag_key):
	if not tag_key:
		return []
	for cf in contact.get("customFields") or []:
		if cf.get("key") == tag_key:
			return [str(v).strip() for v in cf.get("value") or [] if str(v).strip()]
	return []


def _clean_default_fields(contact):
	"""Full defaultFields for a safe PATCH: item ids stripped, empties dropped."""
	df = contact.get("defaultFields") or {}

	def items(rows):
		return [
			{k: v for k, v in (it or {}).items() if k != "id"}
			for it in rows or []
			if (it or {}).get("value")
		]

	return {
		"firstName": df.get("firstName") or "",
		"lastName": df.get("lastName") or "",
		"company": df.get("company"),
		"role": df.get("role"),
		"phoneNumbers": items(df.get("phoneNumbers")),
		"emails": items(df.get("emails")),
	}


def _split_tags(raw):
	return [t.strip() for t in (raw or "").split(",") if t.strip()]


def _join_tags(tags):
	seen, out = set(), []
	for t in tags or []:
		k = t.strip().lower()
		if k and k not in seen:
			seen.add(k)
			out.append(t.strip())
	return ", ".join(out)


def _buyer_properties(buyer_name):
	"""Engaged property labels for the one-way Quo 'Property' field push."""
	if not frappe.db.exists("DocType", "CRM Lead Buyer"):
		return []
	labels = []
	for rel in frappe.get_all("CRM Lead Buyer", filters={"buyer": buyer_name}, fields=["lead"]):
		info = frappe.db.get_value("CRM Lead", rel.lead, ["property_address", "lead_name"], as_dict=True)
		if info:
			labels.append(info.property_address or info.lead_name or rel.lead)
	return sorted(set(labels))


# --------------------------------------------------------------------------- #
# push: buyer -> Quo
# --------------------------------------------------------------------------- #
def _buyer_row(name):
	fields = ["name", "buyer_name", "first_name", "last_name", "phone", "email", "modified"]
	for f in ("quo_contact_id", "quo_synced_at", "quo_tags"):
		if frappe.db.has_column(BUYER_DOCTYPE, f):
			fields.append(f)
	return frappe.db.get_value(BUYER_DOCTYPE, name, fields, as_dict=True)


def _buyer_first_last(b):
	first = (b.get("first_name") or "").strip()
	last = (b.get("last_name") or "").strip()
	if not first and not last:
		first = (b.get("buyer_name") or b.get("name") or "").strip()
	return first, last


def _apply_contact_patch(contact, buyer, keys, set_name=True):
	"""PATCH the contact from the buyer (merge, never wipe). Returns the id."""
	cid = contact["id"]
	df = _clean_default_fields(contact)
	if set_name:
		first, last = _buyer_first_last(buyer)
		df["firstName"], df["lastName"] = first, last

	e164 = _e164(buyer.get("phone"))
	if e164 and _last10(e164) not in {_last10(p["value"]) for p in df["phoneNumbers"]}:
		df["phoneNumbers"].append({"name": "primary", "value": e164})
	if buyer.get("email") and not df["emails"]:
		df["emails"].append({"name": "primary", "value": buyer["email"]})

	body = {"defaultFields": df}
	if not contact.get("externalId"):
		body["externalId"] = buyer["name"]

	custom = []
	if keys.get("tag") is not None and frappe.db.has_column(BUYER_DOCTYPE, "quo_tags"):
		custom.append({"key": keys["tag"], "value": _split_tags(buyer.get("quo_tags"))})
	if keys.get("property"):
		props = _buyer_properties(buyer["name"])
		if props:
			custom.append({"key": keys["property"], "value": props})
	if custom:
		body["customFields"] = custom

	_req("PATCH", f"/contacts/{cid}", json=body)
	return cid


def _create_contact(buyer, keys):
	first, last = _buyer_first_last(buyer)
	e164 = _e164(buyer.get("phone"))
	if not e164:
		return None  # a Quo contact without a phone gets GC'd — don't create one
	df = {
		"firstName": first,
		"lastName": last,
		"phoneNumbers": [{"name": "primary", "value": e164}],
	}
	if buyer.get("email"):
		df["emails"] = [{"name": "primary", "value": buyer["email"]}]
	body = {"defaultFields": df, "externalId": buyer["name"], "source": "public-api"}
	custom = []
	tags = _split_tags(buyer.get("quo_tags"))
	if keys.get("tag") and tags:
		custom.append({"key": keys["tag"], "value": tags})
	props = _buyer_properties(buyer["name"]) if keys.get("property") else []
	if props:
		custom.append({"key": keys["property"], "value": props})
	if custom:
		body["customFields"] = custom
	created = _data(_req("POST", "/contacts", json=body)) or {}
	return created.get("id")


def _stamp(buyer_name, cid):
	vals = {"quo_synced_at": now_datetime()}
	if cid:
		vals["quo_contact_id"] = cid
	vals = {k: v for k, v in vals.items() if frappe.db.has_column(BUYER_DOCTYPE, k)}
	if vals:
		frappe.db.set_value(BUYER_DOCTYPE, buyer_name, vals, update_modified=False)


def _find_contact_for_buyer(buyer, contacts=None):
	"""Resolve the buyer's Quo contact: stored id -> externalId -> phone adopt."""
	cid = buyer.get("quo_contact_id")
	if cid:
		try:
			return _data(_req("GET", f"/contacts/{cid}"))
		except requests.HTTPError as e:
			if e.response is not None and e.response.status_code == 404:
				frappe.db.set_value(BUYER_DOCTYPE, buyer["name"], "quo_contact_id", "", update_modified=False)
			else:
				raise
	found = _req("GET", "/contacts", params={"externalIds": buyer["name"], "maxResults": 2})
	rows = found.get("data") or []
	if rows:
		return rows[0]
	last10 = _last10(buyer.get("phone"))
	if not last10:
		return None
	if contacts is None:
		contacts = _all_contacts()
	for c in contacts:
		ext = c.get("externalId") or ""
		if ext.startswith("CRM-LEAD") or ext.startswith("deleted-"):
			continue  # lead-owned / tombstoned — never adopt
		if any(_last10(p) == last10 for p in _contact_phones(c)):
			return c
	return None


def push_buyer(buyer):
	"""Create/update the Quo contact for one buyer (enqueued from hooks)."""
	if not _enabled():
		return
	b = _buyer_row(buyer)
	if not b:
		return
	try:
		keys = _custom_field_keys()
		contact = _find_contact_for_buyer(b)
		if contact:
			# if the Quo side changed since the last reconcile (tags the cron
			# hasn't pulled yet), union them in so this push can't wipe them;
			# otherwise trust CRM as-is so tag removals actually propagate
			quo_changed = not b.get("quo_synced_at") or (
				_utc_to_sys(contact.get("updatedAt")) or now_datetime()
			) > get_datetime(b.quo_synced_at)
			if quo_changed and keys.get("tag") and frappe.db.has_column(BUYER_DOCTYPE, "quo_tags"):
				merged = _join_tags(_contact_tags(contact, keys["tag"]) + _split_tags(b.get("quo_tags")))
				if merged != (b.get("quo_tags") or ""):
					frappe.db.set_value(BUYER_DOCTYPE, b.name, "quo_tags", merged, update_modified=False)
					b["quo_tags"] = merged
			cid = _apply_contact_patch(contact, b, keys)
		else:
			cid = _create_contact(b, keys)
		if cid:
			_stamp(b.name, cid)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Quo buyer push failed: {buyer}")


def enqueue_push(buyer):
	if not _enabled():
		return
	try:
		frappe.enqueue(
			"crm.api.quo_contacts.push_buyer",
			buyer=buyer,
			queue="short",
			job_id=f"quo-buyer-push-{buyer}",
			deduplicate=True,
		)
	except TypeError:  # older enqueue without deduplicate
		frappe.enqueue("crm.api.quo_contacts.push_buyer", buyer=buyer, queue="short")


# --------------------------------------------------------------------------- #
# CRM Buyer doc hooks (full-doc saves; db.set_value paths call enqueue_push
# explicitly — see crm.api.buyers / investorlift_ingest)
# --------------------------------------------------------------------------- #
def on_buyer_after_insert(doc, method=None):
	enqueue_push(doc.name)


def on_buyer_update(doc, method=None):
	if any(doc.has_value_changed(f) for f in PUSH_FIELDS if doc.meta.has_field(f)):
		enqueue_push(doc.name)


def on_buyer_trash(doc, method=None):
	"""Free the externalId (tombstone) so history stays but the link is severed.
	Mirrors the lead-side 'Quo Contact Unlink' server script."""
	if not _enabled():
		return
	try:
		cid = doc.get("quo_contact_id")
		if not cid:
			found = _req("GET", "/contacts", params={"externalIds": doc.name, "maxResults": 2})
			rows = found.get("data") or []
			cid = rows[0]["id"] if rows else None
		if cid:
			contact = _data(_req("GET", f"/contacts/{cid}"))
			_req(
				"PATCH",
				f"/contacts/{cid}",
				json={
					"externalId": f"deleted-{doc.name}",
					"defaultFields": _clean_default_fields(contact),
				},
			)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Quo buyer unlink failed: {doc.name}")


# --------------------------------------------------------------------------- #
# pull + reconcile: the 10-min scheduler
# --------------------------------------------------------------------------- #
def _pull_into_buyer(b, contact, tags, pull_name):
	"""Write Quo-side values onto the buyer. update_modified=False so a pull
	never looks like a CRM edit next cycle (no ping-pong)."""
	vals = {}
	df = contact.get("defaultFields") or {}
	if pull_name:
		first = (df.get("firstName") or "").strip()
		last = (df.get("lastName") or "").strip()
		display = _contact_display(contact)
		if display and display != (b.get("buyer_name") or ""):
			vals.update({"first_name": first or display, "last_name": last, "buyer_name": display})
	if tags is not None and frappe.db.has_column(BUYER_DOCTYPE, "quo_tags"):
		joined = _join_tags(tags)
		if joined != (b.get("quo_tags") or ""):
			vals["quo_tags"] = joined
	if not b.get("email"):
		for e in df.get("emails") or []:
			if e.get("value"):
				vals["email"] = e["value"].strip().lower()
				break
	if vals:
		frappe.db.set_value(BUYER_DOCTYPE, b.name, vals, update_modified=False)
		frappe.publish_realtime("crm_buyer_update", {"buyer": b.name}, after_commit=True)
	return bool(vals)


def _adopt_or_create_buyer_from_contact(contact, tag_key, lead_last10s):
	"""A Quo contact tagged/named 'buyer' with no CRM match becomes a CRM Buyer."""
	display = _contact_display(contact)
	tags = _contact_tags(contact, tag_key)
	looks_buyer = bool(BUYER_WORD.search(display)) or any(BUYER_WORD.search(t) for t in tags)
	if not looks_buyer or _junk_name(display):
		return None
	phones = [p for p in _contact_phones(contact) if p]
	if not phones or any(_last10(p) in lead_last10s for p in phones):
		return None  # phoneless, or it's a seller-lead's number — not a buyer record

	from crm.api.investorlift_ingest import _upsert_buyer

	df = contact.get("defaultFields") or {}
	row = {
		"name": display,
		"first_name": (df.get("firstName") or "").strip() or display,
		"last_name": (df.get("lastName") or "").strip(),
		"phone": phones[0],
	}
	for e in df.get("emails") or []:
		if e.get("value"):
			row["email"] = e["value"]
			break
	buyer = _upsert_buyer(row)
	if tags and frappe.db.has_column(BUYER_DOCTYPE, "quo_tags"):
		frappe.db.set_value(BUYER_DOCTYPE, buyer, "quo_tags", _join_tags(tags), update_modified=False)
	return buyer


def sync_all():
	"""Scheduled (cron */10) full reconcile; also THE initial backfill:
	adopts the team's hand-made Quo buyer contacts by phone, creates contacts
	for unlinked buyers, pulls Quo-side name/tag edits back, and imports
	'buyer'-tagged Quo contacts that exist nowhere in the CRM."""
	if not _enabled():
		return {"ok": False, "reason": "not provisioned"}

	keys = _custom_field_keys()
	contacts = _all_contacts()
	by_id = {c["id"]: c for c in contacts}
	by_ext = {c["externalId"]: c for c in contacts if c.get("externalId")}
	by_phone = {}
	for c in contacts:
		ext = c.get("externalId") or ""
		if ext.startswith("CRM-LEAD") or ext.startswith("deleted-"):
			continue
		for p in _contact_phones(c):
			by_phone.setdefault(_last10(p), c)

	stats = {"pushed": 0, "created": 0, "pulled": 0, "adopted": 0, "imported": 0, "errors": 0}
	claimed = set()

	buyers = frappe.get_all(
		BUYER_DOCTYPE,
		fields=["name", "buyer_name", "first_name", "last_name", "phone", "email",
		        "modified", "quo_contact_id", "quo_synced_at",
		        *(["quo_tags"] if frappe.db.has_column(BUYER_DOCTYPE, "quo_tags") else [])],
		limit_page_length=0,
	)

	for b in buyers:
		try:
			contact = by_id.get(b.quo_contact_id) if b.quo_contact_id else None
			if b.quo_contact_id and not contact:
				# contact deleted in Quo — sever, and don't resurrect unprompted
				frappe.db.set_value(BUYER_DOCTYPE, b.name, "quo_contact_id", "", update_modified=False)
				continue
			first_link = False
			if not contact:
				contact = by_ext.get(b.name) or by_phone.get(_last10(b.phone))
				first_link = bool(contact)
			if not contact:
				cid = _create_contact(b, keys)
				if cid:
					_stamp(b.name, cid)
					stats["created"] += 1
				continue
			if contact["id"] in claimed:
				continue  # two buyers sharing a phone — first one wins this cycle
			claimed.add(contact["id"])

			quo_tags = _contact_tags(contact, keys.get("tag"))
			crm_tags = _split_tags(b.get("quo_tags"))
			display = _contact_display(contact)
			synced_at = get_datetime(b.quo_synced_at) if b.quo_synced_at else None
			quo_changed = not synced_at or (_utc_to_sys(contact.get("updatedAt")) or now_datetime()) > synced_at
			crm_changed = not synced_at or get_datetime(b.modified) > synced_at

			names_differ = display != (b.buyer_name or "")
			tags_differ = {t.lower() for t in quo_tags} != {t.lower() for t in crm_tags}

			if first_link:
				# adoption: the human-typed Quo name wins unless it's junk/empty
				pull_name = names_differ and not _junk_name(display)
				merged = _join_tags(quo_tags + crm_tags) if tags_differ else None
				if merged is not None or pull_name or not b.email:
					if _pull_into_buyer(b, contact, _split_tags(merged) if merged is not None else None, pull_name):
						stats["pulled"] += 1
					if merged is not None:
						b["quo_tags"] = merged
				_apply_contact_patch(contact, _buyer_row(b.name) or b, keys, set_name=not pull_name)
				_stamp(b.name, contact["id"])
				stats["adopted"] += 1
				continue

			if not (names_differ or tags_differ or (quo_changed and not b.email)):
				if quo_changed or crm_changed:
					_stamp(b.name, contact["id"])
				continue

			if quo_changed and not crm_changed:
				if _pull_into_buyer(b, contact, quo_tags if tags_differ else None, names_differ):
					stats["pulled"] += 1
			elif crm_changed and not quo_changed:
				_apply_contact_patch(contact, b, keys)
				stats["pushed"] += 1
			else:
				# both sides moved: team's Quo name wins; tags union both ways
				merged = _join_tags(quo_tags + crm_tags)
				if _pull_into_buyer(b, contact, _split_tags(merged) if tags_differ else None, names_differ and not _junk_name(display)):
					stats["pulled"] += 1
				if tags_differ:
					refreshed = _buyer_row(b.name)
					_apply_contact_patch(contact, refreshed or b, keys, set_name=False)
					stats["pushed"] += 1
			_stamp(b.name, contact["id"])
		except Exception:
			stats["errors"] += 1
			frappe.log_error(frappe.get_traceback(), f"Quo buyer sync failed: {b.name}")

	# import Quo-only contacts that are explicitly buyers (tag or name says so)
	linked_ids = claimed | {
		c["id"] for c in contacts if (c.get("externalId") or "").startswith("CRM-LEAD")
	}
	lead_last10s = set()
	for l in frappe.get_all("CRM Lead", fields=["mobile_no", "phone"], limit_page_length=0):
		for ph in (l.mobile_no, l.phone):
			d = _last10(ph)
			if d:
				lead_last10s.add(d)
	buyer_last10s = {_last10(b.phone) for b in buyers if _last10(b.phone)}
	for c in contacts:
		if c["id"] in linked_ids or (c.get("externalId") or "").startswith("deleted-"):
			continue
		if any(_last10(p) in buyer_last10s for p in _contact_phones(c)):
			continue  # already a buyer's number (claimed above or duplicate contact)
		try:
			buyer = _adopt_or_create_buyer_from_contact(c, keys.get("tag"), lead_last10s)
			if buyer:
				_stamp(buyer, c["id"])
				ext = c.get("externalId")
				if not ext:
					_req(
						"PATCH",
						f"/contacts/{c['id']}",
						json={"externalId": buyer, "defaultFields": _clean_default_fields(c)},
					)
				buyer_last10s |= {_last10(p) for p in _contact_phones(c)}
				stats["imported"] += 1
		except Exception:
			stats["errors"] += 1
			frappe.log_error(frappe.get_traceback(), f"Quo contact import failed: {c.get('id')}")

	frappe.db.commit()
	return {"ok": True, **stats, "contacts": len(contacts), "buyers": len(buyers)}


# --------------------------------------------------------------------------- #
# one-shot helpers (bench execute)
# --------------------------------------------------------------------------- #
def stamp_buyer_call_references(dry_run=1):
	"""Backfill: reference existing un-linked CRM Call Log rows to the buyer
	whose phone they match (leads keep priority — only reference-less rows)."""
	buyers = {}
	for b in frappe.get_all(BUYER_DOCTYPE, filters={"phone": ("is", "set")}, fields=["name", "phone"]):
		d = _last10(b.phone)
		if d:
			buyers.setdefault(d, b.name)
	stamped = 0
	for cl in frappe.get_all(
		"CRM Call Log",
		filters={"reference_docname": ("is", "not set")},
		fields=["name", "from", "to"],
		limit_page_length=0,
	):
		hit = buyers.get(_last10(cl.get("from"))) or buyers.get(_last10(cl.get("to")))
		if not hit:
			continue
		if not int(dry_run or 0):
			frappe.db.set_value(
				"CRM Call Log",
				cl.name,
				{"reference_doctype": BUYER_DOCTYPE, "reference_docname": hit},
				update_modified=False,
			)
		stamped += 1
	if not int(dry_run or 0):
		frappe.db.commit()
	return {"dry_run": bool(int(dry_run or 0)), "stamped": stamped}
