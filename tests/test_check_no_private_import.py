"""Tests for hooks/check_no_private_import.py — private-module import guard.

Mirrors the shape of ``tests/test_check_no_basic_config.py``: regex behaviour
is exercised in-memory via ``scan_text``; on-disk integration tests cover
the CLI entrypoint and directory walking.
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
    module_path = repo_root / "hooks" / "check_no_private_import.py"
    spec = importlib_util.spec_from_file_location(
        "_hooks_check_no_private_import", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


# ── Regex behaviour (pure, no filesystem) ────────────────────────────────────


def test_flags_from_pkg_private_import() -> None:
    hits = guard.scan_text("from pkg._internal import Helper\n")
    assert hits == [(1, "private module: _internal")]


def test_flags_from_deep_private_import() -> None:
    hits = guard.scan_text("from pkg._internal.sub import thing\n")
    assert hits == [(1, "private module: _internal")]


def test_flags_from_private_in_middle() -> None:
    hits = guard.scan_text("from pkg.sub._impl import func\n")
    assert hits == [(1, "private module: _impl")]


def test_flags_import_pkg_private() -> None:
    hits = guard.scan_text("import pkg._internal\n")
    assert hits == [(1, "private module: _internal")]


def test_flags_import_pkg_private_dotted() -> None:
    hits = guard.scan_text("import pkg._internal.sub\n")
    assert hits == [(1, "private module: _internal")]


def test_flags_from_toplevel_private() -> None:
    hits = guard.scan_text("from _private_lib import util\n")
    assert hits == [(1, "private module: _private_lib")]


def test_flags_import_toplevel_private() -> None:
    hits = guard.scan_text("import _private_lib\n")
    assert hits == [(1, "private module: _private_lib")]


def test_does_not_flag_relative_import() -> None:
    assert guard.scan_text("from ._internal import Helper\n") == []


def test_does_not_flag_deep_relative_import() -> None:
    assert guard.scan_text("from .._internal import Helper\n") == []


def test_does_not_flag_dunder_module() -> None:
    assert guard.scan_text("from __future__ import annotations\n") == []


def test_does_not_flag_import_dunder() -> None:
    assert guard.scan_text("import __main__\n") == []


def test_does_not_flag_dunder_in_path() -> None:
    assert guard.scan_text("from pkg.__init__ import setup\n") == []


def test_does_not_flag_private_name_from_public_module() -> None:
    """Importing a private symbol from a public path is a different concern."""
    assert guard.scan_text("from pkg import _helper\n") == []


def test_does_not_flag_private_name_from_public_dotted() -> None:
    assert guard.scan_text("from pkg.sub import _internal_func\n") == []


def test_does_not_flag_normal_import() -> None:
    assert guard.scan_text("from pathlib import Path\n") == []


def test_does_not_flag_normal_dotted_import() -> None:
    assert guard.scan_text("import os.path\n") == []


def test_does_not_flag_commented_out_import() -> None:
    assert guard.scan_text("# from pkg._internal import X\n") == []


def test_does_not_flag_import_in_trailing_comment() -> None:
    body = "do_thing()  # from pkg._internal import banned\n"
    assert guard.scan_text(body) == []


def test_allowlist_with_reason_silences() -> None:
    body = "from _thread import lock  # private-import-allow: stdlib need\n"
    assert guard.scan_text(body) == []


def test_allowlist_empty_reason_still_fails() -> None:
    body = "from pkg._internal import X  # private-import-allow:\n"
    assert guard.scan_text(body) == [(1, "private module: _internal")]


def test_allowlist_whitespace_reason_still_fails() -> None:
    body = "from pkg._internal import X  # private-import-allow:   \n"
    assert guard.scan_text(body) == [(1, "private module: _internal")]


def test_flags_indented_import() -> None:
    hits = guard.scan_text("    from pkg._priv import X\n")
    assert hits == [(1, "private module: _priv")]


def test_reports_correct_line_numbers() -> None:
    body = (
        "import os\n"
        "from pathlib import Path\n"
        "from pkg._internal import Helper\n"
        "import foo._bar\n"
    )
    assert guard.scan_text(body) == [
        (3, "private module: _internal"),
        (4, "private module: _bar"),
    ]


def test_import_with_as_alias() -> None:
    hits = guard.scan_text("import pkg._internal as pi\n")
    assert hits == [(1, "private module: _internal")]


def test_from_import_with_as_alias() -> None:
    hits = guard.scan_text("from pkg._internal import Foo as Bar\n")
    assert hits == [(1, "private module: _internal")]


def test_private_segment_in_string_not_flagged() -> None:
    body = 'msg = "from pkg._internal import X"\n'
    assert guard.scan_text(body) == []


# ── CLI entrypoint (on-disk integration) ─────────────────────────────────────


def test_main_exits_nonzero_when_src_file_has_private_import() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        offender = root / "src" / "pkg" / "module.py"
        offender.parent.mkdir(parents=True)
        offender.write_text("from nextlabs_sdk._eval import run\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = guard.main([str(offender)])
    assert rc != 0
    assert "private module: _eval" in buf.getvalue()


def test_main_exits_nonzero_when_tests_file_has_private_import() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        offender = root / "tests" / "test_x.py"
        offender.parent.mkdir(parents=True)
        offender.write_text("import lib._internal\n")
        rc = guard.main([str(offender)])
    assert rc != 0


def test_main_exits_zero_on_clean_files() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        clean = root / "src" / "ok.py"
        clean.parent.mkdir(parents=True)
        clean.write_text("from pathlib import Path\nimport os\n")
        rc = guard.main([str(clean)])
    assert rc == 0


def test_main_exits_zero_with_allowlisted_import() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        allowed = root / "src" / "compat.py"
        allowed.parent.mkdir(parents=True)
        allowed.write_text("from _thread import lock  # private-import-allow: stdlib\n")
        rc = guard.main([str(allowed)])
    assert rc == 0


def test_main_walks_src_and_tests_when_given_directory_root() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        (root / "src" / "pkg").mkdir(parents=True)
        (root / "src" / "pkg" / "lib.py").write_text("from sdk._internal import run\n")
        (root / "tests").mkdir()
        (root / "tests" / "test_x.py").write_text("import lib._priv\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = guard.main([str(root)])
    out = buf.getvalue()
    assert rc != 0
    assert "src/pkg/lib.py" in out
    assert "tests/test_x.py" in out
