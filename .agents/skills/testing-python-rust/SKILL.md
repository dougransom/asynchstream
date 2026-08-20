---
name: testing-python-rust
description: Ensures that any Python or Rust code written or modified in this repository is thoroughly tested with appropriate frameworks (pytest, cargo test, mypy, ruff) before declaring completion.
---

# Python & Rust Automated Testing Guidelines

This skill enforces strict automated testing practices whenever Python or Rust code is added, modified, or refactored.

## Core Rules & Workflow

1. **Master Pipeline Script (`./scripts/check.sh`)**:
   - Run `./scripts/check.sh` to execute the full verification suite (maturin build, ruff lint & format check, mypy strict type check, cargo check & clippy, and pytest in both Native & Fallback modes).

2. **Mandatory Test Coverage**:
   - Whenever writing new features, fixing bugs, or refactoring code in Python or Rust, write or update corresponding unit and integration tests.
   - For Python: place tests in the `tests/` directory following `test_*.py` naming conventions using `pytest`.
   - For Rust: write unit tests within modules (`#[cfg(test)] mod tests { ... }`) or integration tests in `tests/`.

3. **Individual Tool Execution**:
   - **Python Formatting & Linting**: `uv run ruff check` and `uv run ruff format --check`.
   - **Python Type Checking**: `uv run mypy py_native_io`.
   - **Rust Compilation & Clippy**: `cargo check` and `cargo clippy -- -D warnings`.
   - **Python & C-Extension Unit Tests**:
     - Native Mode: `uv run pytest`
     - Legacy Fallback Mode: `PY_NATIVE_IO_FORCE_LEGACY=1 uv run pytest`

4. **Git Pre-commit Hook & CI Integration**:
   - `.git/hooks/pre-commit` automatically runs `./scripts/check.sh` on `git commit`.
   - `.github/workflows/ci.yml` runs `./scripts/check.sh` on push and PR.

5. **Zero-Failure Enforcement**:
   - Never declare success or report completion without executing `./scripts/check.sh` and verifying zero failures.
