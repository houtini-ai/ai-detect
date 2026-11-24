"""Every file that states the version must agree (see scripts/release_check.py)."""

import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _release_check():
    spec = importlib.util.spec_from_file_location(
        "release_check", os.path.join(ROOT, "scripts", "release_check.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_version_numbers_agree():
    found = _release_check().versions()
    assert len(set(found.values())) == 1, found


def test_package_version_matches_module():
    import ai_detect
    found = _release_check().versions()
    assert found["ai_detect/_version.py"] == ai_detect.__version__
