"""Mockito-only guard: flag forbidden mocking patterns in ``tests/``.

Forbidden patterns
------------------
* ``from unittest.mock ...`` / ``import unittest.mock ...``
* ``from mock ...`` / ``import mock`` (bare PyPI ``mock`` shim)
* ``monkeypatch.setattr(`` calls

Permitted ``monkeypatch.*`` attrs (env, items, sys.path, chdir, context) are
never flagged. A trailing ``# mockito-allow: <non-empty-reason>`` on the
offending line silences the diagnostic; an empty/whitespace-only reason
after ``:`` still fails.

Diagnostic format::

    path:line: forbidden mocking pattern (<what>)
      hint: use when(real_module).attr(...).thenReturn(...) or add ``# mockito-allow: <reason>``

Shipped as a standard pre-commit hook (id ``check-mockito``) via
``.pre-commit-hooks.yaml`` — invoke from a consumer with
``repo: https://github.com/stevenengland/sten-precommit-hooks`` and pin a
version tag.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_FORBIDDEN: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^\s*from\s+unittest\.mock\b"), "unittest.mock import"),
    (re.compile(r"^\s*import\s+unittest\.mock\b"), "unittest.mock import"),
    (re.compile(r"^\s*from\s+mock\b"), "mock import"),
    (re.compile(r"^\s*import\s+mock\b"), "mock import"),
    (re.compile(r"\bmonkeypatch\.setattr\s*\("), "monkeypatch.setattr"),
)

_ALLOWLIST = re.compile(r"#\s*mockito-allow:\s*\S")

_SKIP_DIR_NAMES = frozenset(
    {"test_temp", "__pycache__", ".mypy_cache", ".pytest_cache"}
)
_HINT = (
    "  hint: use when(real_module).attr(...).thenReturn(...) "
    "or add `# mockito-allow: <reason>`"
)


def _iter_test_files(roots: list[str]) -> list[Path]:
    """Return every ``*.py`` file under ``tests/`` reachable from any root."""
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in roots:
        root = Path(raw).resolve()
        if root.is_file():
            if root.suffix == ".py" and "tests" in root.parts and root not in seen:
                files.append(root)
                seen.add(root)
            continue
        if not root.is_dir():
            continue
        if "tests" in root.parts:
            base = root
        else:
            base = root / "tests"
            if not base.is_dir():
                continue
        for p in base.rglob("*.py"):
            rel_parts = p.relative_to(base).parts
            if _SKIP_DIR_NAMES.intersection(rel_parts):
                continue
            if p not in seen:
                files.append(p)
                seen.add(p)
    return files


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return ``[(lineno, what), ...]`` for forbidden hits in ``text``.

    Pure function — exposed for unit-testing without touching the
    filesystem. Allowlist comments on the matching line suppress the hit.
    """
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern, what in _FORBIDDEN:
            if pattern.search(line):
                if _ALLOWLIST.search(line):
                    break
                hits.append((lineno, what))
                break
    return hits


def _scan(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_text(text)


def main(argv: list[str]) -> int:
    roots = argv or ["."]
    failures = 0
    for path in _iter_test_files(roots):
        for lineno, what in _scan(path):
            print(f"{path}:{lineno}: forbidden mocking pattern ({what})")
            print(_HINT)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
