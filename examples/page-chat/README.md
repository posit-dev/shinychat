# `page_chat()` examples

These paired R and Python Shiny apps demonstrate `page_chat()` without an LLM
provider, API key, or other configuration. Each app responds locally so the
layout and controls can be explored immediately.

| Example | What it covers |
| --- | --- |
| [`navigation/`](navigation/) | Home-scoped and global toolbars, navigation pages, sidebar modes, and responsive mobile navigation. |
| [`artifact-controls/`](artifact-controls/) | Initial artifact content and the show, update, clear, hide, and toggle server controls. |

From a repository checkout, run a Python example after creating the development
environment:

```sh
uv sync --all-extras --all-groups
uv run shiny run --reload examples/page-chat/navigation/app.py
```

Run the R counterpart after installing its development dependencies:

```sh
cd pkg-r && Rscript -e "pak::local_install_dev_deps()"
Rscript -e 'devtools::load_all("pkg-r"); shiny::runApp("examples/page-chat/navigation")'
```

Replace `navigation` with `artifact-controls` to run the other pair. To inspect
the responsive behavior, open the app menu in a narrow browser window: the
navigation and toolbar controls move into that menu while retaining their
existing state.
