#!/usr/bin/env python3
"""Pure contract checks for the refund-state consistency endpoint."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


class Meta:
    fields = {
        "custom_refundable",
        "custom_refund_requested",
        "custom_refund_requested_on",
        "custom_refund_status",
        "custom_refund_not_in_provider",
        "custom_refund_manual_ticket",
    }

    def has_field(self, name):
        return name in self.fields


class Doc:
    name = "LEAD-TEST"
    meta = Meta()

    def __init__(self, values=None):
        self.values = values or {}

    def check_permission(self, *_args):
        return None

    def get(self, key):
        return self.values.get(key)


def load_module(doc, writes):
    frappe = types.ModuleType("frappe")
    frappe._ = lambda value: value
    frappe.whitelist = lambda *args, **_kwargs: (
        args[0] if args and callable(args[0]) else lambda fn: fn
    )
    frappe.throw = lambda message, *_args, **_kwargs: (_ for _ in ()).throw(Exception(message))
    frappe.get_doc = lambda *_args: doc
    frappe.db = types.SimpleNamespace(
        set_value=lambda _doctype, _name, values, **_kwargs: writes.append(values)
    )
    sys.modules["frappe"] = frappe

    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: "NOW"
    sys.modules["frappe.utils"] = utils

    path = Path(__file__).resolve().parents[1] / "crm" / "api" / "refunds.py"
    spec = importlib.util.spec_from_file_location("refunds_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def main():
    writes = []
    doc = Doc({"custom_refund_status": "", "custom_refund_requested_on": None})
    refunds = load_module(doc, writes)

    refunds.set_refund_state("LEAD-TEST", not_in_provider=1)
    assert writes[-1] == {
        "custom_refund_not_in_provider": 1,
        "custom_refundable": 1,
        "custom_refund_status": "To Request",
    }

    refunds.set_refund_state("LEAD-TEST", manual_ticket=1)
    assert writes[-1] == {
        "custom_refund_manual_ticket": 1,
        "custom_refundable": 1,
        "custom_refund_not_in_provider": 1,
        "custom_refund_requested": 1,
        "custom_refund_requested_on": "NOW",
        "custom_refund_status": "Requested",
    }

    refunds.set_refund_state("LEAD-TEST", refundable=0)
    assert writes[-1] == {
        "custom_refundable": 0,
        "custom_refund_requested": 0,
        "custom_refund_requested_on": None,
        "custom_refund_status": "",
        "custom_refund_not_in_provider": 0,
        "custom_refund_manual_ticket": 0,
    }

    print("refund state: missing-provider, manual-ticket, remove invariants PASS")


if __name__ == "__main__":
    main()
