"""Mockito-only guard: flag forbidden mocking patterns in ``tests/``.

Forbidden patterns
------------------
* ``from unittest.mock ...`` / ``import unittest.mock ...``
* ``from unittest import mock`` (also when listed alongside other names)
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

from hooks._common import run

_FORBIDDEN: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^\s*from\s+unittest\.mock\b"), "unittest.mock import"),
    (re.compile(r"^\s*import\s+unittest\.mock\b"), "unittest.mock import"),
    (re.compile(r"^\s*from\s+unittest\s+import\s+.*\bmock\b"), "unittest.mock import"),
    (re.compile(r"^\s*from\s+mock\b"), "mock import"),
    (re.compile(r"^\s*import\s+mock\b"), "mock import"),
    (re.compile(r"\bmonkeypatch\.setattr\s*\("), "monkeypatch.setattr"),
)

_ALLOWLIST = re.compile(r"#\s*mockito-allow:\s*\S")

_HINT = (
    "  hint: use when(real_module).attr(...).thenReturn(...) "
    "or add `# mockito-allow: <reason>`"
)


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


def main(argv: list[str]) -> int:
    return run(
        argv,
        scan_roots=("tests",),
        scan_text=scan_text,
        diagnostic="forbidden mocking pattern",
        hint=_HINT,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
