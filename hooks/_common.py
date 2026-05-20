"""Regex-agnostic scaffolding shared by the guard hooks.

The per-guard ``scan_text`` regex layers genuinely differ, but everything
beneath them is identical in shape: the directory walk that collects
``*.py`` files under the guard's scan roots, the read-text-and-scan step,
and the argv-driven CLI loop. Extracting that layer here keeps a third
guard from copying it a third time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

ScanText = Callable[[str], list[tuple[int, str]]]
Exempt = Callable[[Path], bool]

_SKIP_DIR_NAMES = frozenset(
    {"test_temp", "__pycache__", ".mypy_cache", ".pytest_cache"}
)


def _never_exempt(_: Path) -> bool:
    return False


def iter_python_files(
    roots: list[str],
    scan_roots: tuple[str, ...],
    *,
    exempt: Exempt = _never_exempt,
) -> list[Path]:
    """Return ``*.py`` files under any ``scan_roots`` subtree of ``roots``.

    A file root passes through when its resolved path lies under a
    ``scan_roots`` segment and is not ``exempt``. A directory root already
    under a ``scan_roots`` segment is walked directly; otherwise its
    ``scan_roots`` subdirectories are walked. Files inside a skip-dir or
    matching ``exempt`` are dropped.
    """
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in roots:
        root = Path(raw).resolve()
        if root.is_file():
            if (
                root.suffix == ".py"
                and any(part in scan_roots for part in root.parts)
                and root not in seen
                and not exempt(root)
            ):
                files.append(root)
                seen.add(root)
            continue
        if not root.is_dir():
            continue
        bases: list[Path] = []
        if any(part in scan_roots for part in root.parts):
            bases.append(root)
        else:
            bases.extend(
                root / sub for sub in scan_roots if (root / sub).is_dir()
            )
        for base in bases:
            for path in base.rglob("*.py"):
                if _SKIP_DIR_NAMES.intersection(path.relative_to(base).parts):
                    continue
                if path in seen or exempt(path):
                    continue
                files.append(path)
                seen.add(path)
    return files


def _scan(path: Path, scan_text: ScanText) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_text(text)


def run(
    argv: list[str],
    *,
    scan_roots: tuple[str, ...],
    scan_text: ScanText,
    diagnostic: str,
    hint: str,
    exempt: Exempt = _never_exempt,
) -> int:
    """Walk ``argv`` roots, scan each file, print diagnostics, return rc.

    Each forbidden hit prints ``path:line: <diagnostic> (<what>)`` followed
    by ``hint``. Returns ``1`` if any file had a hit, else ``0``.
    """
    roots = argv or ["."]
    failures = 0
    for path in iter_python_files(roots, scan_roots, exempt=exempt):
        for lineno, what in _scan(path, scan_text):
            print(f"{path}:{lineno}: {diagnostic} ({what})")
            print(hint)
            failures += 1
    return 1 if failures else 0
