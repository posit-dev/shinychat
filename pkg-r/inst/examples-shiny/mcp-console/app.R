# Smoke-test app for MCP Console `send` results rendered as tool cards.
#
# Prerequisites:
#
# 1. The mcp-console server binary, built from a revision that attaches
#    `send` call metadata to results (posit-dev/mcp-console#215, not yet
#    merged -- check out that PR branch, `cargo build --release`, then
#    either put the binary on your PATH or point `MCP_CONSOLE_BIN` at it).
# 2. `ANTHROPIC_API_KEY` set for ellmer.
# 3. An mcptools version that forwards result `_meta` verbatim
#    (posit-dev/mcptools#137, not yet merged -- install the PR branch with
#    `pak::pak("posit-dev/mcptools#137")`).
#
# Run with:
#
#    shiny::runApp("pkg-r/inst/examples-shiny/mcp-console")
#
# Things to try:
#
# * "Plot a histogram of 1000 normal draws" -- the card should arrive open
#   with the plot front and center (request code collapsed behind details).
# * "Show me the first few rows of mtcars" -- a text/code result card.
# * Hover a card to reveal the fullscreen toggle (bottom-right corner);
#   scroll a long result and confirm the toggle stays anchored.
# * Use the copy button on the request/result code blocks.

library(ellmer)
library(shinychat)

binary <- Sys.getenv("MCP_CONSOLE_BIN", unset = Sys.which("mcp-console"))
if (!nzchar(binary)) {
  cli::cli_abort(c(
    "x" = "mcp-console binary not found.",
    "i" = "Build it from https://github.com/posit-dev/mcp-console (`cargo build --release`) and either put it on your {.envvar PATH} or set the {.envvar MCP_CONSOLE_BIN} environment variable to its location."
  ))
}

# mcptools reads server specs from an MCP config file; write one pointing at
# the resolved binary.
config <- tempfile(fileext = ".json")
jsonlite::write_json(
  list(mcpServers = list(console = list(command = binary, args = "serve"))),
  config,
  auto_unbox = TRUE
)

tools <- mcptools::mcp_tools(config)

client <- chat_anthropic(
  system_prompt = paste(
    "You have a `send` tool that executes R code in a persistent session.",
    "Always supply a short one-line `note` naming what the call produces."
  )
)
for (tool in tools) {
  client$register_tool(tool)
}

chat_app(client, title = "MCP Console send cards")
