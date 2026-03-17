# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is shinychat, an AI Chat UI component for Shiny applications, supporting both Python and R implementations. The project is structured as a monorepo with three main packages:

- **js/**: TypeScript/JavaScript source for the chat UI components (built with Lit)
- **pkg-py/**: Python package for Shiny for Python
- **pkg-r/**: R package for Shiny for R

## Architecture

The JavaScript components are built and then copied to both Python and R packages as web assets:
- JS builds to `js/dist/`
- Assets are copied to `pkg-r/inst/lib/shiny/` and `pkg-py/src/shinychat/www/`
- Both packages depend on the built JS components for their web UI

For a deep dive on how message content flows from server to client rendering (the HAST pipeline, innerHTML islands, Shiny binding protection, etc.), see [`memory-bank/content-rendering.md`](memory-bank/content-rendering.md).

## Common Development Commands

### JavaScript (js/)
- **Setup**: `cd js && npm install`
- **Build**: `cd js && npm run build` (lint + bundle)
- **Lint**: `cd js && npm run lint` (TypeScript check + ESLint)
- **Watch**: `cd js && npm run watch` (rebuild on file changes)
- **Fast build/watch**: Use `build-fast` and `watch-fast` targets (skip minification)

### Python (pkg-py/)
- **Setup**: `uv sync --all-extras`
- **Lint**: `uv run ruff check pkg-py --config pyproject.toml`
- **Format**: `uv run ruff check --fix pkg-py --config pyproject.toml && uv run ruff format pkg-py --config pyproject.toml`
- **Type check**: `uv run pyright`
- **Test**: `uv run pytest` (requires `uv run playwright install` first)
- **Build**: `uv build`
- **Coverage**: `uv run coverage run -m pytest && uv run coverage report`

### R (pkg-r/)
- **Setup**: `cd pkg-r && Rscript -e "pak::local_install_dev_deps()"`
- **Document**: `cd pkg-r && Rscript -e "devtools::document()"`
- **Check**: `cd pkg-r && Rscript -e "devtools::check(document = FALSE)"`
- **Test**: `cd pkg-r && Rscript -e "devtools::test()"`
- **Format**: `air format pkg-r/` (check with `air format --check pkg-r/`)

### Makefile Targets
The repository includes a comprehensive Makefile with prefixed targets:
- **js-\***: JavaScript tasks (`js-build`, `js-lint`, `js-setup`)
- **py-\***: Python tasks (`py-check`, `py-format`, `py-test`)
- **r-\***: R tasks (`r-check`, `r-format`, `r-test`)
- **docs**: Build all documentation
- Run `make help` to see all available targets

### Asset Distribution
**IMPORTANT**: After any TypeScript/SCSS changes in `js/`, you must rebuild (`cd js && npm run build`) and then copy the built assets to the package(s) you're testing:
- **R**: `make r-update-dist`
- **Python**: `make py-update-dist`

## Testing

### Python
- Main tests: `uv run pytest`
- Playwright browser tests included (requires `uv run playwright install`)
- Tox for multi-version testing: `uv run tox run-parallel` (Python 3.9-3.13)
- Snapshot updates: `uv run pytest --snapshot-update`

### R
- Tests: `cd pkg-r && Rscript -e "devtools::test()"`
- R CMD check: `cd pkg-r && Rscript -e "devtools::check(document = FALSE)"`

### JavaScript
- Linting includes TypeScript compilation check: `cd js && npm run lint`

## Documentation

### Python Docs
- Built with Quarto + quartodoc
- **Build API docs**: `cd pkg-py/docs && uv run quartodoc build`
- **Render docs**: `make py-docs-render` (uses Quarto)
- **Preview**: `make py-docs-preview`

### R Docs
- Built with pkgdown
- **Build**: `cd pkg-r && Rscript -e "pkgdown::build_site()"`
- **Preview**: `cd pkg-r && Rscript -e "pkgdown::preview_site()"`

## Key Files

- `pyproject.toml`: Python package configuration, dependencies, and tool settings
- `js/package.json`: JavaScript dependencies and build scripts
- `pkg-r/DESCRIPTION`: R package metadata and dependencies
- `Makefile`: Comprehensive build system with language-specific targets