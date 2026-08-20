#!/usr/bin/env bash
set -euo pipefail

echo "==> 1. Building C-extension with maturin..."
uv run maturin develop

echo "==> 2. Running Ruff linter & formatting check..."
uv run ruff check
uv run ruff format --check

echo "==> 3. Running Mypy strict type checking..."
uv run mypy py_native_io

echo "==> 4. Checking Rust compilation & clippy..."
cargo check
cargo clippy -- -D warnings

echo "==> 5. Running Pytest (Native Mode)..."
uv run pytest

echo "==> 6. Running Pytest (Legacy Fallback Mode)..."
PY_NATIVE_IO_FORCE_LEGACY=1 uv run pytest

echo "✅ All checks passed successfully!"
