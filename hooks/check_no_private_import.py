"""Guard: forbid absolute imports from ``_``-prefixed (private) submodules.

Python's single-underscore prefix on a module or package name (``_eval``,
``_internal``, ``_compat``) signals an implementation detail not covered by
the public API contract. Importing from such paths couples consumer code to
internals that may change or disappear without notice.

Flagged patterns
----------------
* ``from pkg._priv import X``
* ``from pkg._priv.sub import X``
* ``from _priv import X`` (top-level private package)
* ``import pkg._priv``
* ``import pkg._priv.sub``

**Not** flagged:

* Relative imports (``from ._priv import X``) — intra-package references
  to private siblings are a legitimate encapsulation pattern.
* Dunder modules (``from __future__ import annotations``,
  ``import __main__``) — these are public by convention.
* Private *names* from a public module (``from pkg import _helper``) —
  that is a name-level concern, not a module-boundary violation.

Escape hatch
~~~~~~~~~~~~
Trailing comment with a non-empty reason on the offending line::

    from _thread import start_new_thread  # private-import-allow: stdlib need

Empty or whitespace-only reasons after ``:`` still fail.

Diagnostic format::

    path:line: forbidden private-module import (private module: _priv)
      hint: import from the public API or add ``# private-import-allow: <reason>``

Shipped as a standard pre-commit hook (id ``check-no-private-import``) via
``.pre-commit-hooks.yaml``.
"""

from __future__ import annotations

import re
import sys

from hooks._common import run, strip_comment

_FROM_IMPORT = re.compile(r"^\s*from\s+([a-zA-Z_]\w*(?:\.\w+)*)\s+import\b")
_BARE_IMPORT = re.compile(r"^\s*import\s+([a-zA-Z_]\w*(?:\.\w+)*)")
_ALLOWLIST = re.compile(r"#\s*private-import-allow:\s*\S")

_HINT = (
    "  hint: import from the public API " "or add `# private-import-allow: <reason>`"
)


def _has_private_segment(module_path: str) -> str | None:
    """Return the first private segment if ``module_path`` contains one.

    A segment is private when it starts with a single underscore but not a
    double underscore (dunder modules like ``__future__`` are public).
    """
    for segment in module_path.split("."):
        if segment.startswith("_") and not segment.startswith("__"):
            return segment
    return None


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return ``[(lineno, what), ...]`` for each private-module import hit.

    Pure function — exposed for unit-testing without touching the
    filesystem. Each line is scanned with its trailing ``#`` comment
    stripped so a forbidden import mentioned in a comment does not trip
    the guard; the allowlist directive is still matched against the full
    line.
    """
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        code = strip_comment(line)
        mod_path: str | None = None

        m = _FROM_IMPORT.match(code)
        if m:
            mod_path = m.group(1)
        else:
            m = _BARE_IMPORT.match(code)
            if m:
                mod_path = m.group(1)

        if mod_path is None:
            continue

        priv = _has_private_segment(mod_path)
        if priv is None:
            continue
        if _ALLOWLIST.search(line):
            continue
        hits.append((lineno, f"private module: {priv}"))
    return hits


def main(argv: list[str]) -> int:
    return run(
        argv,
        scan_roots=("src", "tests"),
        scan_text=scan_text,
        diagnostic="forbidden private-module import",
        hint=_HINT,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
