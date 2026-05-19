"""Guard: forbid ``logging.basicConfig(`` under ``src/`` and ``tests/``.

Library code attaches a ``NullHandler`` only; test code lets pytest own log
capture. Any call to ``logging.basicConfig(...)`` in those trees would
install a root handler as a side-effect of import, leak stderr noise into
the suite, and break ``caplog`` assertions.

``tools/`` is exempt: standalone helper scripts legitimately configure
logging when invoked outside pytest. Files whose resolved path lives under
a ``tools`` segment are skipped. A trailing
``# basicconfig-allow: <non-empty-reason>`` on the offending line silences
the diagnostic case-by-case — same shape as the ``# mockito-allow:``
escape hatch on the sibling ``check-mockito`` guard.

Diagnostic format::

    path:line: forbidden basicConfig call (logging.basicConfig)
      hint: attach a NullHandler in library code; let pytest own log capture in tests

Mirrors :mod:`check_mockito`: ``scan_text`` is the pure regex layer,
``main`` is the argv-driven CLI entrypoint. Shipped as a standard
pre-commit hook (id ``check-no-basic-config``) via
``.pre-commit-hooks.yaml``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_FORBIDDEN = re.compile(r"(?<!#)\blogging\.basicConfig\s*\(")
_ALLOWLIST = re.compile(r"#\s*basicconfig-allow:\s*\S")
_EXEMPT_SEGMENT = "tools"
_HINT = (
    "  hint: attach a NullHandler in library code; "
    "let pytest own log capture in tests"
)


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return ``[(lineno, what), ...]`` for each ``logging.basicConfig(`` hit.

    Pure function — exposed for unit-testing without touching the
    filesystem. Lines whose first non-whitespace character is ``#`` are
    treated as fully commented out and skipped.
    """
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if _FORBIDDEN.search(line):
            if _ALLOWLIST.search(line):
                continue
            hits.append((lineno, "logging.basicConfig"))
    return hits


_SCAN_ROOTS = ("src", "tests")
_SKIP_DIR_NAMES = frozenset(
    {"test_temp", "__pycache__", ".mypy_cache", ".pytest_cache"}
)


def _is_exempt(path: Path) -> bool:
    return _EXEMPT_SEGMENT in path.resolve().parts


def _iter_target_files(roots: list[str]) -> list[Path]:
    """Return ``*.py`` files under ``src/``+``tests/`` reachable from ``roots``.

    Mirrors :func:`check_mockito._iter_test_files`: file roots pass straight
    through; directory roots either themselves live under ``src/``/``tests/``
    (walked directly) or are projects whose ``src/``/``tests/`` subdirs are
    walked. ``tools/`` paths are filtered out at the file level.
    """
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in roots:
        root = Path(raw).resolve()
        if root.is_file():
            if root.suffix == ".py" and root not in seen and not _is_exempt(root):
                files.append(root)
                seen.add(root)
            continue
        if not root.is_dir():
            continue
        bases: list[Path] = []
        if any(part in _SCAN_ROOTS for part in root.parts):
            bases.append(root)
        else:
            bases.extend(root / sub for sub in _SCAN_ROOTS if (root / sub).is_dir())
        for base in bases:
            for p in base.rglob("*.py"):
                if _SKIP_DIR_NAMES.intersection(p.relative_to(base).parts):
                    continue
                if p in seen or _is_exempt(p):
                    continue
                files.append(p)
                seen.add(p)
    return files


def _scan(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_text(text)


def main(argv: list[str]) -> int:
    roots = argv or ["."]
    failures = 0
    for path in _iter_target_files(roots):
        for lineno, what in _scan(path):
            print(f"{path}:{lineno}: forbidden basicConfig call ({what})")
            print(_HINT)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
