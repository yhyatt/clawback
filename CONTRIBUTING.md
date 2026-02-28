# Contributing to ClawBack

Thanks for your interest! ClawBack welcomes contributions of all kinds — bug fixes, new features, parser improvements, and documentation.

## Before You Start

- Check [open issues](https://github.com/yhyatt/clawback/issues) to avoid duplication
- For significant changes, open an issue first to discuss the approach
- All contributions require passing CI (lint + typecheck + tests)

## Development Setup

```bash
git clone https://github.com/yhyatt/clawback.git
cd clawback
pip install -e ".[dev]"
```

## Running Tests

```bash
# Full suite (517 tests, no external calls)
pytest

# With coverage
pytest --cov=clawback --cov-report=term

# Oracle edge-case suite (130 cases, no LLM)
pytest -m oracle

# Oracle + LLM confirmation message validation (optional, requires ANTHROPIC_API_KEY)
# Never runs in CI — manual use only
pytest -m oracle --haiku
```

## Code Style

We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting, and [mypy](https://mypy.readthedocs.io/) for type checking.

```bash
ruff check src tests        # lint
ruff format src tests       # format
mypy src                    # type check
```

All three must pass before opening a PR. CI will enforce this.

## Pull Request Guidelines

- **One PR per concern** — keep changes focused
- **Write tests** — all new parser cases should have oracle coverage
- **Update oracle fixtures** if you're adding or changing parse behaviour
- **Squash commits** — we use squash merges; your commit history will be squashed
- **Branch naming** — `fix/...`, `feat/...`, `docs/...`, `chore/...`

## Parser Contributions

The parser (`src/clawback/parser.py`) is regex-based — intentionally no LLM. If you're adding a new language or currency:

1. Add the parse pattern to `parser.py`
2. Add oracle test cases to `tests/fixtures/oracle_cases.json`
3. Run `pytest -m oracle` to verify all cases pass

## Reporting Security Issues

Please **do not** open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree your code will be licensed under the [MIT License](LICENSE).
