"""Tests for hooks/check_mockito.py — repo-agnostic mockito-only guard.

Regex behavior is exercised against in-memory strings via ``scan_text``;
the directory-walking layer gets one on-disk integration test rooted in
``/tmp`` so pytest's basetemp can't re-collect the synthetic fixtures.
"""

from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stdout
from importlib import util as importlib_util
from pathlib import Path
from types import ModuleType


def _load_check_mockito() -> ModuleType:
    repo_root = Path(__file__).resolve().parent.parent
    module_path = repo_root / "hooks" / "check_mockito.py"
    spec = importlib_util.spec_from_file_location("_hooks_check_mockito", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_check_mockito()


# ── Regex behavior (pure, no filesystem) ──────────────────────────────────────


def test_flags_from_unittest_mock_import() -> None:
    hits = guard.scan_text("from unittest.mock import patch\n")
    assert hits == [(1, "unittest.mock import")]


def test_flags_import_unittest_mock() -> None:
    hits = guard.scan_text("import unittest.mock\n")
    assert hits == [(1, "unittest.mock import")]


def test_flags_from_unittest_import_mock() -> None:
    hits = guard.scan_text("from unittest import mock\n")
    assert hits == [(1, "unittest.mock import")]


def test_flags_from_unittest_import_mock_in_list() -> None:
    hits = guard.scan_text("from unittest import TestCase, mock\n")
    assert hits == [(1, "unittest.mock import")]


def test_flags_from_unittest_import_mock_aliased() -> None:
    hits = guard.scan_text("from unittest import mock as M\n")
    assert hits == [(1, "unittest.mock import")]


def test_permits_from_unittest_import_testcase() -> None:
    assert guard.scan_text("from unittest import TestCase\n") == []


def test_flags_bare_import_mock() -> None:
    hits = guard.scan_text("import mock\n")
    assert hits == [(1, "mock import")]


def test_flags_from_mock_import() -> None:
    hits = guard.scan_text("from mock import patch\n")
    assert hits == [(1, "mock import")]


def test_flags_monkeypatch_setattr() -> None:
    call = "monkeypatch.setattr(o, 'a', 1)"  # mockito-allow: regex fixture
    body = "def f(monkeypatch):\n    {0}\n".format(call)
    hits = guard.scan_text(body)
    assert hits == [(2, "monkeypatch.setattr")]


def test_permits_monkeypatch_safe_attrs() -> None:
    body = (
        "def f(monkeypatch):\n"
        "    monkeypatch.setenv('K', 'V')\n"
        "    monkeypatch.delenv('K', raising=False)\n"
        "    monkeypatch.setitem({}, 'k', 'v')\n"
        "    monkeypatch.delitem({}, 'k', raising=False)\n"
        "    monkeypatch.syspath_prepend('/tmp')\n"
        "    monkeypatch.chdir('/tmp')\n"
    )
    assert guard.scan_text(body) == []


def test_allowlist_with_reason_silences() -> None:
    body = "monkeypatch.setattr(o, 'a', 1)  # mockito-allow: legacy\n"
    assert guard.scan_text(body) == []


def test_allowlist_empty_reason_still_fails() -> None:
    body = "monkeypatch.setattr(o, 'a', 1)  # mockito-allow:\n"
    assert guard.scan_text(body) == [(1, "monkeypatch.setattr")]


def test_allowlist_whitespace_reason_still_fails() -> None:
    body = "monkeypatch.setattr(o, 'a', 1)  # mockito-allow:   \n"
    assert guard.scan_text(body) == [(1, "monkeypatch.setattr")]


# ── Trailing-comment edge cases ───────────────────────────────────────────────


def test_mock_word_in_trailing_comment_not_flagged() -> None:
    assert guard.scan_text("from unittest import TestCase  # uses mock\n") == []


def test_setattr_in_trailing_comment_not_flagged() -> None:
    line = "x = 1  # monkeypatch.setattr(o, 'a', 1)\n"  # mockito-allow: regex fixture
    assert guard.scan_text(line) == []


def test_flags_setattr_when_hash_is_inside_a_string_arg() -> None:
    body = 'monkeypatch.setattr(d, "#k", 1)'  # mockito-allow: regex fixture
    assert guard.scan_text(body) == [(1, "monkeypatch.setattr")]


# ── Diagnostic format (CLI surface) ───────────────────────────────────────────


def test_main_emits_path_line_what_and_hint() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        target = root / "tests" / "fixture.py"
        target.parent.mkdir(parents=True)
        target.write_text("from unittest.mock import patch\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = guard.main([str(target)])
    out = buf.getvalue()
    assert rc != 0
    assert f"{target}:1: forbidden mocking pattern (unittest.mock import)" in out
    assert "hint:" in out
    assert "when(" in out
    assert "mockito-allow" in out


# ── Walker (single on-disk integration test) ──────────────────────────────────


def test_only_walks_tests_dir_skips_src() -> None:
    """Walker only inspects files under ``tests/`` — ``src/`` is ignored."""
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        offender = root / "src" / "x.py"
        offender.parent.mkdir(parents=True)
        offender.write_text("from unittest.mock import patch\n")
        rc = guard.main([str(root)])
    assert rc == 0
