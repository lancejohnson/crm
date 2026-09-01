#!/usr/bin/env python3
"""Focused filesystem regression for Practice read-during-recording recovery.

Runs without a Frappe site by stubbing only the import surface. The exercised
chunk helpers are the production functions from crm/api/practice.py.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path


def _identity_decorator(*args, **_kwargs):
    if args and callable(args[0]):
        return args[0]
    return lambda fn: fn


def load_practice(root: Path, site: Path):
    frappe = types.ModuleType("frappe")
    frappe._ = lambda value: value
    frappe.whitelist = _identity_decorator
    frappe.get_site_path = lambda *parts: str(site.joinpath(*parts))
    frappe.db = types.SimpleNamespace()
    sys.modules["frappe"] = frappe

    frappe_utils = types.ModuleType("frappe.utils")
    frappe_utils.flt = float
    frappe_utils.get_datetime = lambda value=None: value
    frappe_utils.get_fullname = lambda value=None: value or ""
    frappe_utils.now_datetime = lambda: None
    frappe_utils.time_diff_in_seconds = lambda *_args: 0
    sys.modules["frappe.utils"] = frappe_utils

    werkzeug_utils = types.ModuleType("werkzeug.utils")
    werkzeug_utils.send_file = lambda *_args, **_kwargs: None
    sys.modules["werkzeug.utils"] = werkzeug_utils

    comps = types.ModuleType("crm.api.comps")
    comps._guard = lambda: None
    comps.get_lead_comps = lambda *_args, **_kwargs: {}
    sys.modules["crm.api.comps"] = comps

    condition = types.ModuleType("crm.api.practice_condition")
    condition.pick_seller_note = lambda *_args, **_kwargs: ""
    sys.modules["crm.api.practice_condition"] = condition

    path = root / "crm" / "api" / "practice.py"
    spec = importlib.util.spec_from_file_location("practice_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="practice-chunks-") as tmp:
        site = Path(tmp)
        (site / "private" / "files").mkdir(parents=True)
        practice = load_practice(root, site)
        attempt, prop = "ATTEMPT", "PROPERTY"

        chunk0 = practice._chunk_path(attempt, prop, 0)
        with open(chunk0, "wb") as fh:
            fh.write(b"first")
        practice._write_chunk_manifest(attempt, prop, {"0": 5})

        # This is what _shape_attempt() does while recording: it asks for the
        # disk fallback after touch_property, before the recorder has stopped.
        url = practice._file_recording_url(attempt, prop)
        assert url.endswith("practice-ATTEMPT-PROPERTY.webm")
        assert os.path.exists(chunk0), "read-time shaping deleted active seq 0"
        with open(practice._dest_path(attempt, prop), "rb") as fh:
            assert fh.read() == b"first"

        # MediaRecorder produces another chunk after the shaped response.
        chunk1 = practice._chunk_path(attempt, prop, 1)
        with open(chunk1, "wb") as fh:
            fh.write(b"-tail")
        practice._write_chunk_manifest(attempt, prop, {"0": 5, "1": 5})

        dest, chunks = practice._assemble_recording_chunks(attempt, prop)
        assert chunks == [chunk0, chunk1]
        with open(dest, "rb") as fh:
            assert fh.read() == b"first-tail", "finish retained the partial assembly"

        # Only explicit successful finalization cleans the durable sequences.
        practice._cleanup_recording_chunks(attempt, prop, chunks)
        assert not os.path.exists(chunk0)
        assert not os.path.exists(chunk1)

    print("practice chunks: shape-during-recording + later tail + finish PASS")


if __name__ == "__main__":
    main()
