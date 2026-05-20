"""Tests for hooks/_common.py — the shared walker + CLI runner.

The two guards share this regex-agnostic layer; it is exercised here
directly with a marker-word ``scan_text`` stub so the cases do not depend
on either guard's real regexes. On-disk fixtures live under ``/tmp`` so
pytest's basetemp cannot re-collect them.
"""

from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from hooks import _common


def _flag_marker(text: str) -> list[tuple[int, str]]:
    """Stub scanner: flag every line containing the word ``OFFENDER``."""
    return [
        (lineno, "marker")
        for lineno, line in enumerate(text.splitlines(), start=1)
        if "OFFENDER" in line
    ]


def test_file_root_under_scan_root_is_included() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        target = Path(raw) / "tests" / "fixture.py"
        target.parent.mkdir(parents=True)
        target.write_text("ok\n")
        found = _common.iter_python_files([str(target)], ("tests",))
    assert found == [target.resolve()]


def test_file_root_outside_scan_root_is_excluded() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        stray = Path(raw) / "elsewhere" / "fixture.py"
        stray.parent.mkdir(parents=True)
        stray.write_text("ok\n")
        found = _common.iter_python_files([str(stray)], ("tests",))
    assert found == []


def test_directory_root_walks_scan_root_subdirs() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        (root / "src").mkdir()
        (root / "src" / "a.py").write_text("ok\n")
        (root / "tests").mkdir()
        (root / "tests" / "b.py").write_text("ok\n")
        (root / "other").mkdir()
        (root / "other" / "c.py").write_text("ok\n")
        found = _common.iter_python_files([str(root)], ("src", "tests"))
    names = sorted(p.name for p in found)
    assert names == ["a.py", "b.py"]


def test_skip_dir_names_are_pruned() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        (root / "tests" / "__pycache__").mkdir(parents=True)
        (root / "tests" / "__pycache__" / "stale.py").write_text("ok\n")
        (root / "tests" / "real.py").write_text("ok\n")
        found = _common.iter_python_files([str(root)], ("tests",))
    assert [p.name for p in found] == ["real.py"]


def test_exempt_predicate_drops_matching_files() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        (root / "src").mkdir()
        keep = root / "src" / "keep.py"
        keep.write_text("ok\n")
        drop = root / "src" / "drop.py"
        drop.write_text("ok\n")
        found = _common.iter_python_files(
            [str(root)], ("src",), exempt=lambda p: p.name == "drop.py"
        )
    assert [p.name for p in found] == ["keep.py"]


def test_same_file_reached_twice_is_deduplicated() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        root = Path(raw)
        (root / "tests").mkdir()
        target = root / "tests" / "dup.py"
        target.write_text("ok\n")
        found = _common.iter_python_files([str(root), str(target)], ("tests",))
    assert found == [target.resolve()]


def test_run_reports_hits_and_returns_nonzero() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        target = Path(raw) / "tests" / "fixture.py"
        target.parent.mkdir(parents=True)
        target.write_text("clean\nOFFENDER here\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = _common.run(
                [str(target)],
                scan_roots=("tests",),
                scan_text=_flag_marker,
                diagnostic="bad thing",
                hint="  hint: stop it",
            )
    out = buf.getvalue()
    assert rc == 1
    assert f"{target}:2: bad thing (marker)" in out
    assert "hint: stop it" in out


def test_run_returns_zero_on_clean_tree() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as raw:
        target = Path(raw) / "tests" / "fixture.py"
        target.parent.mkdir(parents=True)
        target.write_text("all clean\n")
        rc = _common.run(
            [str(target)],
            scan_roots=("tests",),
            scan_text=_flag_marker,
            diagnostic="bad thing",
            hint="  hint: stop it",
        )
    assert rc == 0
