# Python Coding Standards

## Formatting & Style
- Follow PEP 8. Line length: 100 chars max.
- Use `black` for formatting and `ruff` (or `flake8` + `isort`) for linting/import sorting.
- 4 spaces per indent level, never tabs.
- One blank line between methods, two between top-level classes/functions.
- Use double quotes for strings unless the string itself contains a double quote.

## Naming
- `snake_case` for functions, variables, and module names.
- `PascalCase` for classes and exceptions.
- `UPPER_SNAKE_CASE` for constants.
- Prefix internal/non-public attributes and functions with a single leading underscore (`_helper`).
- Avoid single-letter names except for trivial loop counters (`i`, `j`) or well-known math symbols.

## Type Hints
- All new functions and methods must have type hints on parameters and return values.
- Use `from __future__ import annotations` or PEP 604 syntax (`str | None`) instead of `Optional[str]` on Python 3.10+.
- Use `typing` generics (`list[str]`, `dict[str, int]`) instead of `List`/`Dict` on Python 3.9+.
- Run `mypy` (or `pyright`) in strict mode where practical; don't silently ignore type errors with bare `# type: ignore`.

## Docstrings & Comments
- Public modules, classes, and functions get a docstring (Google or NumPy style — pick one and stay consistent per project).
- Docstrings describe *why* and *contract* (params, returns, raises), not a restatement of the code.
- Inline comments only for non-obvious logic (workarounds, subtle invariants); don't narrate what the code already says.

## Project Structure
- Use `src/` layout for packages (`src/<package_name>/`).
- One class or tightly related group of functions per module; avoid god-modules.
- Group imports: standard library, third-party, local — separated by a blank line, alphabetized within each group.
- No wildcard imports (`from module import *`).
- No circular imports; if two modules need each other, extract a shared module.

## Functions & Classes
- Prefer small, single-responsibility functions. If a function needs a comment to explain a section, consider extracting that section.
- Prefer composition over inheritance; avoid deep inheritance hierarchies.
- Use `@dataclass` (or `pydantic.BaseModel` for validated/external data) instead of hand-written boilerplate classes.
- Avoid mutable default arguments (`def f(x, items=[])` — use `None` and default inside the function).
- Keep function signatures small; bundle related parameters into a dataclass when they grow past ~5.

## Error Handling
- Catch specific exceptions, never bare `except:`.
- Don't swallow exceptions silently — log or re-raise.
- Raise custom exceptions (subclassing a project-specific base exception) for domain errors instead of generic `Exception`.
- Use `raise ... from err` when re-raising inside an `except` block to preserve the traceback chain.
- Validate only at system boundaries (user input, external APIs, I/O); trust internal calls and type hints elsewhere.

## Testing
- Use `pytest` (not `unittest`) for new test suites.
- Test file layout mirrors source layout: `tests/test_<module>.py`.
- One behavior per test; descriptive test names (`test_<unit>_<scenario>_<expected>`).
- Use fixtures for shared setup; avoid global mutable test state.
- Mock/stub only external boundaries (network, filesystem, time) — don't mock internal logic under test.

## Dependencies & Environment
- Pin dependencies via `pyproject.toml` (Poetry, PDM, or `uv`) — avoid loose `requirements.txt` without pinned versions for production code.
- Use virtual environments; never install packages globally.
- Separate dev dependencies (test, lint, type-check tools) from runtime dependencies.

## Logging
- Use the `logging` module, never `print()`, for anything beyond throwaway scripts.
- Include context in log messages (IDs, relevant state); don't log secrets or PII.
- Configure log level via environment/config, not hardcoded in modules.

## Misc
- Prefer f-strings for string formatting; avoid `%`-formatting and `.format()` in new code.
- Use `pathlib.Path` instead of `os.path` string manipulation.
- Use context managers (`with`) for any resource that needs cleanup (files, locks, connections).
- Avoid global mutable state; pass dependencies explicitly (dependency injection over module-level singletons).
- No commented-out dead code — delete it; git history preserves it.
