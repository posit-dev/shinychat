# AGENTS.md

This file provides guidance to coding agents working in this repository.

## Project Overview

This is shinychat, an AI Chat UI component for Shiny applications, supporting both Python and R implementations. The project is structured as a monorepo with three main packages:

- **js/**: TypeScript/JavaScript source for the chat UI components (built with React)
- **pkg-py/**: Python package for Shiny for Python
- **pkg-r/**: R package for Shiny for R

## Architecture

The JavaScript components are built and then copied to both Python and R packages as web assets:
- JS builds to `js/dist/`
- Assets are copied to `pkg-r/inst/lib/shiny/` and `pkg-py/src/shinychat/www/`
- Both packages depend on the built JS components for their web UI

For a deep dive on how message content flows from server to client rendering (the HAST pipeline, innerHTML islands, Shiny binding protection, etc.), see [`memory-bank/content-rendering.md`](memory-bank/content-rendering.md).

## CSS Naming

CSS identifiers for the chat use the `shiny-chat` prefix:

- Classes: `.shiny-chat-*`
- Custom properties: `--shiny-chat-*`
- Keyframes: `shiny-chat-*`

Do not introduce CSS identifiers with a `shinychat-` prefix.
The unhyphenated `shinychat` name remains appropriate for package names and
existing non-CSS integration identifiers, such as `data-shinychat-*` attributes,
and storage keys. New raw-HTML islands use `<shiny-chat-raw-html>`; preserve
`<shinychat-raw-html>` only as a legacy input until its compatibility window
closes.

## Development Workflow

Run `make help` from the repository root before choosing a development,
testing, build, or documentation command. Prefer the listed Make targets over
their underlying package-manager commands. Target help text documents supported
arguments, including test filters.

### Asset Distribution

**CRITICAL**: The Python and R packages serve JS/CSS from their own copy of the built assets, NOT from `js/dist/` directly. After ANY change to TypeScript or SCSS files in `js/`, you MUST rebuild and copy to packages with `make update-dist`.

If you skip this step, the packages will serve stale JS and your changes will not take effect at runtime. This applies to renaming, adding features, fixing bugs — any JS/SCSS change at all.

Commit source files indepentently of built asset updates. You can wait to commit asset updates until the end of a PR or work cycle.

## Key Files

- `pyproject.toml`: Python package configuration, dependencies, and tool settings
- `js/package.json`: JavaScript dependencies and build scripts
- `pkg-r/DESCRIPTION`: R package metadata and dependencies
- `Makefile`: Comprehensive build system with language-specific targets
