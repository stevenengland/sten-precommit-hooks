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

from hooks._common import run, strip_comment

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
    filesystem. Each line is scanned with its trailing ``#`` comment
    stripped, so a fully or partly commented ``logging.basicConfig(`` does
    not trip the guard; the allowlist directive is still matched against
    the full line.
    """
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _FORBIDDEN.search(strip_comment(line)):
            if _ALLOWLIST.search(line):
                continue
            hits.append((lineno, "logging.basicConfig"))
    return hits


def _is_exempt(path: Path) -> bool:
    return _EXEMPT_SEGMENT in path.resolve().parts


def main(argv: list[str]) -> int:
    return run(
        argv,
        scan_roots=("src", "tests"),
        scan_text=scan_text,
        diagnostic="forbidden basicConfig call",
        hint=_HINT,
        exempt=_is_exempt,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
