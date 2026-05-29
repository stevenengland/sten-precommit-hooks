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

CLI options
~~~~~~~~~~~
``--allow PREFIX`` (repeatable): permit own-package private imports
**only in files under ``src/``**. Tests always get the strict version —
they must exercise the public API. Third-party private imports are never
allowed regardless of this flag.

Example: ``--allow mypackage`` permits
``from mypackage._internal import X`` in ``src/mypackage/app.py`` but
still forbids it in ``tests/test_app.py``.

Diagnostic format::

    path:line: forbidden private-module import (private module: _priv)
      hint: import from the public API or add ``# private-import-allow: <reason>``

Shipped as a standard pre-commit hook (id ``check-no-private-import``) via
``.pre-commit-hooks.yaml``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from hooks._common import iter_python_files, strip_comment

_FROM_IMPORT = re.compile(r"^\s*from\s+([a-zA-Z_]\w*(?:\.\w+)*)\s+import\b")
_BARE_IMPORT = re.compile(r"^\s*import\s+([a-zA-Z_]\w*(?:\.\w+)*)")
_ALLOWLIST = re.compile(r"#\s*private-import-allow:\s*\S")

_HINT = (
    "  hint: import from the public API " "or add `# private-import-allow: <reason>`"
)

_SCAN_ROOTS = ("src", "tests")


def _has_private_segment(module_path: str) -> str | None:
    """Return the first private segment if ``module_path`` contains one.

    A segment is private when it starts with a single underscore but not a
    double underscore (dunder modules like ``__future__`` are public).
    """
    for segment in module_path.split("."):
        if segment.startswith("_") and not segment.startswith("__"):
            return segment
    return None


def _is_allowed(module_path: str, allowed_prefixes: tuple[str, ...]) -> bool:
    """Return True if ``module_path`` starts with any allowed prefix."""
    for prefix in allowed_prefixes:
        if module_path == prefix or module_path.startswith(prefix + "."):
            return True
    return False


def _is_under_src(path: Path) -> bool:
    """Return True if the resolved path contains a ``src`` segment."""
    return "src" in path.resolve().parts


def scan_text(
    text: str, *, allowed_prefixes: tuple[str, ...] = ()
) -> list[tuple[int, str]]:
    """Return ``[(lineno, what), ...]`` for each private-module import hit.

    Pure function — exposed for unit-testing without touching the
    filesystem. Each line is scanned with its trailing ``#`` comment
    stripped so a forbidden import mentioned in a comment does not trip
    the guard; the allowlist directive is still matched against the full
    line.

    ``allowed_prefixes`` are only meant to be passed for source files,
    never for test files.
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

        if allowed_prefixes and _is_allowed(mod_path, allowed_prefixes):
            continue

        priv = _has_private_segment(mod_path)
        if priv is None:
            continue
        if _ALLOWLIST.search(line):
            continue
        hits.append((lineno, f"private module: {priv}"))
    return hits


def _parse_args(argv: list[str]) -> tuple[tuple[str, ...], list[str]]:
    """Split ``--allow PREFIX`` pairs from file paths."""
    allowed: list[str] = []
    files: list[str] = []
    it = iter(argv)
    for arg in it:
        if arg == "--allow":
            try:
                allowed.append(next(it))
            except StopIteration:
                print("error: --allow requires a value", file=sys.stderr)
                sys.exit(2)
        elif arg.startswith("--allow="):
            allowed.append(arg[len("--allow=") :])
        else:
            files.append(arg)
    return tuple(allowed), files


def main(argv: list[str]) -> int:
    allowed_prefixes, files = _parse_args(argv)
    roots = files or ["."]
    failures = 0

    for path in iter_python_files(roots, _SCAN_ROOTS):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # --allow only applies to src/ files; tests are always strict.
        prefixes = allowed_prefixes if _is_under_src(path) else ()
        hits = scan_text(text, allowed_prefixes=prefixes)

        for lineno, what in hits:
            print(f"{path}:{lineno}: forbidden private-module import ({what})")
            print(_HINT)
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
