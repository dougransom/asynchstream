# Antigravity Agent Runtime

An advanced, compliant Python agent project built using the Google Antigravity framework, managed with `uv`.

## Features & Architecture

- **Tooling:** Uses `uv` for package management, `ruff` for ultra-fast linting/formatting, and `pyright` for strict type checking.
- **Higher-Order Metaprogramming:** Features custom metaclasses (`AgentRegistryMeta`) for dynamic tool auto-registration and decorator wrappers (`@TraceableAction`) using `typing.ParamSpec` and `typing.Concatenate`.
- **Code Style:** Enforces clean target-state selection patterns (`A = B if x else C; f(A)`) via Ruff's `SIM` and `C90` rules.
- **Git Hooks:** Includes pre-configured `pre-commit` hooks for automatic quality checks.

## Quickstart

```bash
# Sync virtual environment and dependencies
uv sync

# Install git pre-commit hooks
uv run pre-commit install

# Run static type checking
uv run pyright

# Run linter
uv run ruff check .

# Execute the compliance agent
uv run python -m src.agents
```
