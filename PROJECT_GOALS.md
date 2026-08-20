# Project Goals & Architectural Specification

## Primary Objectives
1. **Antigravity SDK Integration:** Build robust, policy-driven AI agent runtime pipelines using `google-antigravity`.
2. **Strict Compliance & Standards:** Maintain clean code health adhering to modern Rust-backed Python tools (`uv`, `ruff`, `pyright`).
3. **Advanced Python Idioms:** Leverage metaclasses, higher-order functions, and decorators without sacrificing static type safety or IDE completion.

## Development Workflows
- **Target Selection Style:** Avoid redundant logic calls in conditionals (`if x: f(A) else: f(B)`). Prefer isolating data state prior to execution (`A = B if x else C; f(A)`).
- **Environment Parity:** Managed via `uv` lockfiles across operating systems (Windows development -> Linux runtime).
