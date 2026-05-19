# sten-precommit-hooks

Repo-agnostic [pre-commit](https://pre-commit.com/) regex guards. Pure
stdlib, Python 3.11+, zero runtime dependencies.

## Usage

Add to your consumer repo's `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/stevenengland/sten-precommit-hooks
  rev: v0.1.0
  hooks:
    - id: check-mockito
    - id: check-no-basic-config
```

Always pin a version tag. Pinning to a branch (`main`, `HEAD`) is a
contract violation: upgrades are deliberate acts recorded in commit
history, not passive pulls.

## Hooks

### `check-mockito`

**Bans** these patterns under `tests/`:

- `from unittest.mock ...` / `import unittest.mock ...`
- `from mock ...` / `import mock` (PyPI `mock` shim)
- `monkeypatch.setattr(...)` calls

**Why.** Mockito-style tests express intent through `when(real).attr(...).thenReturn(...)`
against the real module. `unittest.mock` and `monkeypatch.setattr` patch
by name into arbitrary attribute namespaces, which silently rots when
the production import path moves and tends to assert on call shape
rather than observable behaviour.

Other `monkeypatch.*` attrs (`setenv`, `delenv`, `setitem`, `delitem`,
`syspath_prepend`, `chdir`, `context`) are permitted — they manipulate
test environment, not production collaborators.

**Escape hatch.** Trailing comment with a non-empty reason on the
offending line:

```python
monkeypatch.setattr(legacy_mod, "attr", value)  # mockito-allow: <reason>
```

Empty or whitespace-only reasons after the `:` still fail.

### `check-no-basic-config`

**Bans** `logging.basicConfig(` calls under `src/` and `tests/`. The
`tools/` segment is exempt: standalone helper scripts legitimately
configure logging when invoked outside pytest.

**Why.** Library code should attach a `NullHandler` only; test code
should let pytest own log capture. A stray `logging.basicConfig(...)`
installs a root handler at import time, leaks stderr noise into the
suite, and breaks `caplog` assertions.

**Escape hatch.** Trailing comment with a non-empty reason:

```python
logging.basicConfig(level=logging.INFO)  # basicconfig-allow: <reason>
```

Empty or whitespace-only reasons after the `:` still fail.

## Conventions for placement in this repo

A guard belongs here iff:

1. It is pure regex over file content.
2. It makes no per-repo assumption about directory names, logger
   names, or fixture conventions.
3. It is testable purely via `scan_text`-style in-memory fixtures.

Guards that depend on repo-specific runtime state (fixtures, conftest,
wrapper scripts) stay local to the consumer.

Hook IDs are kebab-case and prefixed `check-`. They are stable; renames
go through a major version bump and a deprecation period.

## Development

```bash
pip install pytest pre-commit
pytest
pre-commit run --all-files
```

To exercise the hooks end-to-end against a working tree without
publishing a tag:

```bash
pre-commit try-repo /path/to/sten-precommit-hooks --all-files
```

## License

MIT — see [LICENSE](LICENSE).
