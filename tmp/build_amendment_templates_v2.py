#!/usr/bin/env python3
"""Rebuild the DocuSeal Amendment templates (v2, 2026-09-07, Lance's asks).

Changes vs the Jul-14 build (4996712 / 4996713, built from a Desktop DOCX):
  1. Buyer is "Groundwork Ventures Inc." everywhere — the old doc said
     "Groundwork Ventures Inc" up top and "Groundwork Ventures, LLC" at the
     signature block.
  2. Each amendment is OPTIONAL behind a checkbox: purchase price, closing
     date, or a free-text "Other" line pair.
  3. The Buyer block gets "Printed name: ____  Title: ____" like the Purchase
     Agreement's signature page — same field names (`Signer Name` / `Title`)
     so the CRM's buyer prefill works unchanged.

The PDF is DRAWN here with PyMuPDF (no DOCX round-trip), so every blank's
bbox is known at draw time and the field areas cannot drift from the page.
Flow after that is the PSA v2 script's: upload untagged -> set roles -> PUT
fields (with attachment_uuid — mandatory, see build_psa_templates_v2.py) ->
clone (dodges the fresh-template values-prefill 500) -> values-test the clone
-> archive the build original + the test submission.

The old live templates are left UNARCHIVED: `_resolve_template_ids` takes the
highest non-archived id per name, so the new clones win for new agreements and
in-flight submissions keep rendering as signed.

  python3 tmp/build_amendment_templates_v2.py --pdf-only   # just write the PDFs
  python3 tmp/build_amendment_templates_v2.py              # build on DocuSeal
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

import fitz  # PyMuPDF

API = "https://api.docuseal.com"
FOLDER = "Purchase Agreements"
OUT = "/Users/work/Projects/Groundwork/frappe-crm-app/tmp"
W, H = 612.0, 792.0
LM, RM = 72.0, 540.0  # left / right margin (x)
BODY = 11.0
LEAD = 12.65  # line height for 11pt body (matches the DOCX export)
BOLD, ROMAN = "tibo", "tiro"  # Times Bold / Times Roman (PDF base-14)
COMPANY = "Groundwork Ventures Inc."


# ----------------------------------------------------------------- drawing

class Page:
    """Cursor-driven writer that records every blank it draws as a bbox."""

    def __init__(self, page: fitz.Page):
        self.p = page
        self.y = 0.0  # baseline of the next line
        self.blanks: dict[str, tuple[float, float, float, float]] = {}

    @staticmethod
    def width(text, font=ROMAN, size=BODY):
        return fitz.get_text_length(text, fontname=font, fontsize=size)

    def text(self, x, text, font=ROMAN, size=BODY, y=None):
        y = self.y if y is None else y
        self.p.insert_text((x, y), text, fontname=font, fontsize=size)
        return x + self.width(text, font, size)

    def blank(self, x, name, chars, y=None, size=BODY, pad=0.0):
        """Draw an underscore run and record its bbox for the field overlay."""
        y = self.y if y is None else y
        run = "_" * chars
        w = self.width(run, ROMAN, size)
        self.p.insert_text((x, y), run, fontname=ROMAN, fontsize=size)
        # bbox in PDF points, y from top; the field sits on the rule
        self.blanks[name] = (x + pad, y - size + 1.0, x + w, y + 2.5)
        return x + w

    def checkbox(self, x, name, y=None, side=10.0):
        """A printed square; the DocuSeal checkbox field overlays it exactly."""
        y = self.y if y is None else y
        r = fitz.Rect(x, y - side + 1.0, x + side, y + 1.0)
        self.p.draw_rect(r, color=(0, 0, 0), width=0.8)
        self.blanks[name] = (r.x0, r.y0, r.x1, r.y1)
        return r.x1

    def para(self, text, x=LM, right=RM, font=ROMAN, size=BODY, lead=LEAD):
        """Word-wrap a paragraph; leaves the cursor on the line AFTER it."""
        words, line = text.split(), ""
        for w in words:
            trial = (line + " " + w).strip()
            if self.width(trial, font, size) > right - x and line:
                self.text(x, line, font, size)
                self.y += lead
                line = w
            else:
                line = trial
        if line:
            self.text(x, line, font, size)
            self.y += lead

    def rule(self, y=None):
        y = self.y if y is None else y
        self.p.draw_line((LM, y), (RM, y), color=(0, 0, 0), width=1.0)

    def gap(self, pts):
        self.y += pts


def draw(two: bool) -> tuple[fitz.Document, dict]:
    doc = fitz.open()
    pg = Page(doc.new_page(width=W, height=H))
    sellers_label = "Sellers:" if two else "Seller:"

    # Title
    pg.y = 50.0
    title = "AMENDMENT TO PURCHASE AND SALE AGREEMENT"
    tw = pg.width(title, BOLD, 14)
    pg.text((W - tw) / 2, title, BOLD, 14)

    # Parties
    pg.y = 96.0
    x = pg.text(LM, "Buyer: ", BOLD)
    x2 = pg.text(x, COMPANY)
    pg.p.draw_line((x, pg.y + 1.5), (x2, pg.y + 1.5), width=0.6)
    pg.gap(26)
    x = pg.text(LM, sellers_label + " ", BOLD)
    pg.blank(x, "Seller Name(s)", 58)
    pg.gap(26)
    x = pg.text(LM, "Property: ", BOLD)
    pg.blank(x, "Property Address", 55)
    pg.gap(26)

    # Recital — the Binding Agreement Date blank sits mid-sentence, so that
    # line is laid by hand and the rest wraps.
    pg.para("In consideration of the mutual covenants herein and other good and "
            "valuable consideration, the receipt and sufficiency of which is hereby "
            "acknowledged, the parties agree to amend that certain Purchase and")
    x = pg.text(LM, "Sale Agreement with a Binding Agreement Date of ")
    x = pg.blank(x, "Binding Agreement Date", 14)
    pg.text(x, ", and any incorporated addenda,")
    pg.gap(LEAD)
    pg.para("exhibits, or prior amendments (collectively referred to herein as the "
            "\"Agreement\") for the purchase and sale of the real property specified "
            "above as follows (check all that apply):")
    pg.gap(8)

    # The amendments — each optional behind a checkbox.
    IND = LM + 18.0      # checkbox x
    TX = IND + 18.0      # text x after the box
    pg.checkbox(IND, "Amend Purchase Price")
    x = pg.text(TX, "Buyer and Seller hereby mutually agree to amend the purchase price to $")
    x = pg.blank(x, "Amended Purchase Price", 12)
    pg.text(x, ".")
    pg.gap(20)
    pg.checkbox(IND, "Amend Closing Date")
    x = pg.text(TX, "Buyer and Seller hereby mutually agree to amend the closing date to ")
    x = pg.blank(x, "Amended Closing Date", 13)
    pg.text(x, ".")
    pg.gap(20)
    pg.checkbox(IND, "Amend Other")
    pg.text(TX, "Buyer and Seller hereby mutually agree to the following additional amendment(s):")
    pg.gap(LEAD + 3)
    # Two ruled lines; ONE text field spans both so a sentence can wrap.
    top = pg.y - BODY + 1.0
    pg.blank(TX, "_other1", 66)
    pg.gap(LEAD + 3)
    pg.blank(TX, "_other2", 66)
    x1 = pg.blanks.pop("_other2")[2]
    pg.blanks.pop("_other1")
    pg.blanks["Other Amendments"] = (TX, top, x1, pg.y + 2.5)
    pg.gap(20)

    pg.para("This Amendment shall become binding when signed by all parties and shall "
            "be incorporated into the Agreement, and all other terms and conditions "
            "of the Purchase and Sale Agreement shall remain in full force and effect.")
    pg.gap(6)
    pg.rule()
    pg.gap(20)

    # BUYER block (mirrors the PSA signature page: signature / printed name + title / date)
    pg.text(LM, "BUYER", BOLD)
    pg.gap(LEAD)
    pg.text(LM, "The party(ies) below have signed and acknowledge receipt of a copy.")
    pg.gap(22)
    x = pg.text(LM, "Buyer: ", BOLD)
    x2 = pg.text(x, COMPANY)
    pg.p.draw_line((x, pg.y + 1.5), (x2, pg.y + 1.5), width=0.6)
    pg.gap(27)
    x = pg.text(LM, "Signature: ", BOLD)
    pg.blank(x, "Buyer Signature", 38)
    pg.gap(22)
    x = pg.text(LM, "Printed name: ", BOLD)
    x = pg.blank(x, "Signer Name", 30)
    x = pg.text(x + 14, "Title: ", BOLD)
    pg.blank(x, "Title", 22)
    pg.gap(22)
    x = pg.text(LM, "Date: ", BOLD)
    pg.blank(x, "Buyer Date Signed", 26)
    pg.gap(12)
    pg.rule()
    pg.gap(20)

    # SELLER block(s)
    def seller_block(prefix):
        pg.text(LM, "SELLER", BOLD)
        pg.gap(LEAD)
        pg.text(LM, "The party(ies) below have signed and acknowledge receipt of a copy.")
        pg.gap(22)
        x = pg.text(LM, "Seller: ", BOLD)
        pg.blank(x, f"{prefix} Name", 40)
        pg.gap(27)
        x = pg.text(LM, "Signature: ", BOLD)
        pg.blank(x, f"{prefix} Signature", 38)
        pg.gap(22)
        x = pg.text(LM, "Date: ", BOLD)
        pg.blank(x, f"{prefix} Date Signed", 26)

    if two:
        seller_block("Seller 1")
        pg.gap(12)
        pg.rule()
        pg.gap(20)
        seller_block("Seller 2")
    else:
        seller_block("Seller")

    if pg.y > H - 36:
        raise SystemExit(f"layout overflows the page: last baseline {pg.y:.1f}")
    return doc, pg.blanks


# ----------------------------------------------------------------- DocuSeal

def token() -> str:
    inf = os.path.expanduser("~/.claude/skills/api-call/scripts/inf-secret")
    return subprocess.check_output([inf, "DOCUSEAL_API_KEY"], text=True).strip()


_TOKEN = None


def api(method, path, body=None, timeout=90):
    global _TOKEN
    _TOKEN = _TOKEN or token()
    data = None
    headers = {"X-Auth-Token": _TOKEN}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} {method} {path}: {e.read().decode()[:800]}") from e


DATE = {"format": "MM/DD/YYYY"}
SIG_LIFT = 10.0  # signature boxes get room above the rule


def area(bbox, attachment, lift=0.0):
    x0, y0, x1, y1 = bbox
    y0 -= lift
    return {
        "x": round(x0 / W, 6), "y": round(y0 / H, 6),
        "w": round((x1 - x0) / W, 6), "h": round((y1 - y0) / H, 6),
        "page": 0, "attachment_uuid": attachment,
    }


def fields_for(blanks, by_role, two, attachment):
    buyer = by_role["Buyer"]

    def f(name, ftype, uuid, required=False, prefs=None, lift=0.0):
        return {
            "name": name, "type": ftype, "required": required, "submitter_uuid": uuid,
            "preferences": prefs or {}, "areas": [area(blanks[name], attachment, lift)],
        }

    out = [
        f("Seller Name(s)", "text", buyer),
        f("Property Address", "text", buyer),
        f("Binding Agreement Date", "date", buyer, prefs=DATE),
        f("Amend Purchase Price", "checkbox", buyer),
        f("Amended Purchase Price", "text", buyer),
        f("Amend Closing Date", "checkbox", buyer),
        f("Amended Closing Date", "date", buyer, prefs=DATE),
        f("Amend Other", "checkbox", buyer),
        f("Other Amendments", "text", buyer),
        f("Buyer Signature", "signature", buyer, required=True, lift=SIG_LIFT),
        f("Signer Name", "text", buyer, required=True),
        f("Title", "text", buyer),
        f("Buyer Date Signed", "date", buyer, required=True, prefs=DATE),
    ]
    roles = [("Seller 1", by_role["Seller 1"]), ("Seller 2", by_role["Seller 2"])] if two \
        else [("Seller", by_role["Seller"])]
    for prefix, uuid in roles:
        out += [
            f(f"{prefix} Name", "text", uuid),
            f(f"{prefix} Signature", "signature", uuid, required=True, lift=SIG_LIFT),
            f(f"{prefix} Date Signed", "date", uuid, required=True, prefs=DATE),
        ]
    return out


def write_pdfs():
    paths = {}
    for two in (False, True):
        doc, blanks = draw(two)
        tag = "two" if two else "one"
        path = f"{OUT}/amendment-v2-{tag}.pdf"
        doc.save(path)
        doc[0].get_pixmap(dpi=110).save(f"{OUT}/amendment-v2-{tag}.png")
        # preview: boxes where the fields will land
        pv = fitz.open(path)
        for name, (x0, y0, x1, y1) in blanks.items():
            lift = SIG_LIFT if "Signature" in name else 0.0
            pv[0].draw_rect(fitz.Rect(x0, y0 - lift, x1, y1), color=(1, 0, 0), width=0.6)
        pv[0].get_pixmap(dpi=110).save(f"{OUT}/amendment-v2-{tag}-fields.png")
        paths[two] = (path, blanks)
        print(f"wrote {path} ({len(blanks)} blanks)")
    return paths


def build(two: bool, path: str, blanks: dict):
    kind = "two" if two else "one"
    canonical = f"Amendment - {'Two Sellers' if two else 'One Seller'}"
    build_name = f"AMD BUILD v2 - {kind}"  # never starts with "Amendment" -> can't win the resolver
    roles = ["Buyer", "Seller 1", "Seller 2"] if two else ["Buyer", "Seller"]
    print(f"\n=== {kind}: upload {build_name} ===")
    pdf_b64 = base64.b64encode(open(path, "rb").read()).decode()
    status, created = api("POST", "/templates/pdf", {
        "name": build_name, "folder_name": FOLDER,
        "documents": [{"name": canonical, "file": pdf_b64}],
    }, timeout=120)
    tid = created.get("id")
    print("uploaded", status, tid)
    api("PUT", f"/templates/{tid}", {"name": build_name, "folder_name": FOLDER, "roles": roles})
    _, tmpl = api("GET", f"/templates/{tid}")
    by_role = {s["name"]: s["uuid"] for s in tmpl["submitters"]}
    doc_uuid = (tmpl.get("documents") or [{}])[0].get("uuid")
    if not doc_uuid:
        raise SystemExit("no document uuid on the uploaded template")
    fields = fields_for(blanks, by_role, two, doc_uuid)
    status, put = api("PUT", f"/templates/{tid}", {"fields": fields})
    print("fields put", status, "n", len(put.get("fields") or fields))

    print(f"=== {kind}: clone -> {canonical} ===")
    status, cloned = api("POST", f"/templates/{tid}/clone", {"name": canonical, "folder_name": FOLDER})
    cid = cloned.get("id")
    api("PUT", f"/templates/{cid}", {"name": canonical, "folder_name": FOLDER})
    _, clone = api("GET", f"/templates/{cid}")
    print("cloned", status, cid, clone.get("name"), "folder", clone.get("folder_name"))
    orphan = [f["name"] for f in clone.get("fields") or []
              if not (f.get("areas") or [{}])[0].get("attachment_uuid")]
    if orphan:
        raise SystemExit(f"clone {cid} has fields with no attachment_uuid: {orphan}")
    print("clone fields", [(f["name"], f["type"], f.get("required")) for f in clone.get("fields") or []])

    print(f"=== {kind}: values-prefill test ===")
    buyer_values = {
        "Seller Name(s)": "Jane Doe" + (" and John Doe" if two else ""),
        "Property Address": "123 Main St, Dallas, TX 75201",
        "Signer Name": "Lance Johnson",
    }
    submitters = [{"role": "Buyer", "name": "Lance Johnson",
                   "email": "amd-test-buyer@noreply.groundworkpro.com",
                   "send_email": False, "values": buyer_values}]
    if two:
        submitters += [
            {"role": "Seller 1", "name": "Jane Doe", "email": "amd-test-s1@noreply.groundworkpro.com",
             "send_email": False, "values": {"Seller 1 Name": "Jane Doe"}},
            {"role": "Seller 2", "name": "John Doe", "email": "amd-test-s2@noreply.groundworkpro.com",
             "send_email": False, "values": {"Seller 2 Name": "John Doe"}},
        ]
    else:
        submitters.append({"role": "Seller", "name": "Jane Doe",
                           "email": "amd-test-seller@noreply.groundworkpro.com",
                           "send_email": False, "values": {"Seller Name": "Jane Doe"}})
    status, sub = api("POST", "/submissions", {
        "template_id": cid, "send_email": False, "order": "preserved", "submitters": submitters,
    })
    if isinstance(sub, list):
        sid = sub[0].get("submission_id") if sub else None
        print("submission OK", status, "id", sid, "buyer link",
              [s.get("embed_src") for s in sub if s.get("role") == "Buyer"])
    else:
        sid = sub.get("id")
        print("submission OK", status, "id", sid)

    print(f"=== {kind}: archive BUILD original {tid} ===")
    api("DELETE", f"/templates/{tid}")
    if sid and not os.environ.get("KEEP_TEST_SUBMISSION"):
        print(f"=== {kind}: archive test submission {sid} ===")
        api("DELETE", f"/submissions/{sid}")
    return cid, sid


def main():
    paths = write_pdfs()
    if "--pdf-only" in sys.argv:
        return
    one, one_sid = build(False, *paths[False])
    two, two_sid = build(True, *paths[True])
    print("\nOld live templates 4996712 / 4996713 left UNARCHIVED on purpose.")
    print("DONE one=", one, "two=", two, "test submissions:", one_sid, two_sid)


if __name__ == "__main__":
    main()
