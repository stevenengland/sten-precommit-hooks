"""Tests for hooks/check_no_basic_config.py — basicConfig guard.

Mirrors the shape of ``tests/test_check_mockito.py``: regex behaviour is
exercised in-memory via ``scan_text``; a single on-disk integration test
covers the CLI entrypoint and the ``tools/`` exemption.
"""

from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stdout
from importlib import util as importlib_util
from pathlib import Path
from types import ModuleType


def _load_guard() -> ModuleType:
    repo_root = Path(__file__).resolve().parent.parent
    module_path = repo_root / "hooks" / "check_no_basic_config.py"
    spec = importlib_util.spec_from_file_location(
        "_hooks_check_no_basic_config", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


# ── Regex behaviour (pure, no filesystem) ────────────────────────────────────


def test_flags_logging_basic_config_call() -> None:
    hits = guard.scan_text("logging.basicConfig(level=logging.INFO)\n")
    assert hits == [(1, "logging.basicConfig")]


def test_flags_logging_basic_config_with_whitespace() -> None:
    hits = guard.scan_text("    logging.basicConfig()\n")
    assert hits == [(1, "logging.basicConfig")]


def test_does_not_flag_commented_out_basic_config() -> None:
    assert guard.scan_text("# logging.basicConfig()\n") == []


def test_does_not_flag_bare_basic_config_call() -> None:
    """Only ``logging.basicConfig`` is forbidden; aliased imports are out of scope."""
    assert guard.scan_text("basicConfig(level=20)\n") == []


def test_does_not_flag_unrelated_code() -> None:
    assert guard.scan_text("logger = logging.getLogger(__name__)\n") == []


def test_allowlist_with_reason_silences() -> None:
    body = "logging.basicConfig()  # basicconfig-allow: standalone script\n"
    assert guard.scan_text(body) == []


def test_allowlist_empty_reason_still_fails() -> None:
    body = "logging.basicConfig()  # basicconfig-allow:\n"
    assert guard.scan_text(body) == [(1, "logging.basicConfig")]


def test_allowlist_whitespace_reason_still_fails() -> None:
    body = "logging.basicConfig()  # basicconfig-allow:   \n"
    assert guard.scan_text(body) == [(1, "logging.basicConfig")]


def test_reports_line_number_for_offender_among_clean_lines() -> None:
    body = (
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "logging.basicConfig(level=logging.WARNING)\n"
    )
    assert guard.scan_text(body) == [(3, "logging.basicConfig")]


# ── CLI entrypoint + tools/ exemption (on-disk integration) ──────────────────


def test_main_exits_nonzero_when_src_file_has_basic_config() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        offender = root / "src" / "pkg" / "module.py"
        offender.parent.mkdir(parents=True)
        offender.write_text("logging.basicConfig()\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = guard.main([str(offender)])
    assert rc != 0
    assert "logging.basicConfig" in buf.getvalue()


def test_main_exits_nonzero_when_tests_file_has_basic_config() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        offender = root / "tests" / "test_x.py"
        offender.parent.mkdir(parents=True)
        offender.write_text("logging.basicConfig()\n")
        rc = guard.main([str(offender)])
    assert rc != 0


def test_main_exits_zero_when_tools_only_has_basic_config() -> None:
    """``tools/`` files are exempt: standalone scripts may configure logging."""
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        legit = root / "tools" / "standalone.py"
        legit.parent.mkdir(parents=True)
        legit.write_text("logging.basicConfig(level=logging.INFO)\n")
        rc = guard.main([str(legit)])
    assert rc == 0


def test_main_walks_src_and_tests_when_given_directory_root() -> None:
    """Directory root → walk ``src/`` and ``tests/`` subtrees, skip ``tools/``."""
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        (root / "src" / "pkg").mkdir(parents=True)
        (root / "src" / "pkg" / "lib.py").write_text("logging.basicConfig()\n")
        (root / "tests").mkdir()
        (root / "tests" / "test_x.py").write_text("logging.basicConfig()\n")
        (root / "tools").mkdir()
        (root / "tools" / "script.py").write_text("logging.basicConfig()\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = guard.main([str(root)])
    out = buf.getvalue()
    assert rc != 0
    assert "src/pkg/lib.py" in out
    assert "tests/test_x.py" in out
    assert "tools/script.py" not in out


def test_main_exits_zero_on_clean_files() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        clean = root / "src" / "ok.py"
        clean.parent.mkdir(parents=True)
        clean.write_text("import logging\nlogger = logging.getLogger(__name__)\n")
        rc = guard.main([str(clean)])
    assert rc == 0
