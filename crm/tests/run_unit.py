#!/usr/bin/env python3
"""Run the bench-free unit tests (`crm/tests/unit_test_*.py`).

    python3 crm/tests/run_unit.py            # all
    python3 crm/tests/run_unit.py talk       # files matching *talk*

There is no local bench, so these tests stub `frappe` (see frappe_shim.py) and
side-step the package `__init__`s that import the real thing: `crm.api`,
`crm.integrations` and `crm.tests` are registered as bare packages pointing at
their real directories, so `crm.api.talk` is the real module but
`crm/api/__init__.py` (bs4, phonenumbers, frappe.core…) never runs.

The `unit_test_` prefix is deliberate: bench's own runner discovers `test_*.py`,
and these must never load under a real Frappe — `install()` would replace it.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)


def _bare_package(name: str, path: str):
	module = types.ModuleType(name)
	module.__path__ = [path]
	module.__package__ = name
	sys.modules[name] = module
	return module


def bootstrap():
	spec = importlib.util.spec_from_file_location(
		"crm.tests.frappe_shim", os.path.join(ROOT, "crm", "tests", "frappe_shim.py")
	)
	shim_module = importlib.util.module_from_spec(spec)
	crm_pkg = _bare_package("crm", os.path.join(ROOT, "crm"))
	crm_pkg.__version__ = "1.67.0"
	_bare_package("crm.tests", os.path.join(ROOT, "crm", "tests"))
	_bare_package("crm.api", os.path.join(ROOT, "crm", "api"))
	_bare_package("crm.integrations", os.path.join(ROOT, "crm", "integrations"))
	sys.modules["crm.tests.frappe_shim"] = shim_module
	spec.loader.exec_module(shim_module)
	return shim_module.install()


def main(argv):
	bootstrap()
	pattern = f"unit_test_*{argv[0]}*.py" if argv else "unit_test_*.py"
	suite = unittest.defaultTestLoader.discover(
		os.path.join(ROOT, "crm", "tests"), pattern=pattern, top_level_dir=ROOT
	)
	result = unittest.TextTestRunner(verbosity=2).run(suite)
	return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
