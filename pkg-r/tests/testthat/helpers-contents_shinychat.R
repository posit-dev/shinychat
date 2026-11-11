local_shinychat_tool_display <- function(
  envvar = NULL,
  opt = NULL,
  env = parent.frame()
) {
  withr::local_envvar(SHINYCHAT_TOOL_DISPLAY = envvar, .local_envir = env)
  withr::local_options(shinychat.tool_display = opt, .local_envir = env)
}

with_shinychat_tool_display <- function(
  code,
  envvar = NULL,
  opt = NULL
) {
  local_shinychat_tool_display(envvar, opt)
  force(code)
}

# Helper function to create tool requests
new_tool_request <- function(
  id = "test-id",
  name = "test-tool",
  arguments = list(),
  tool = NULL
) {
  ellmer::ContentToolRequest(
    id = id,
    name = name,
    arguments = arguments,
    tool = tool %||% new_tool()
  )
}

# Helper function to create tool results
new_tool_result <- function(
  value = NULL,
  error = NULL,
  request = new_tool_request(),
  extra = list()
) {
  ellmer::ContentToolResult(
    value = value,
    error = error,
    request = request,
    extra = extra
  )
}

# The wire contract: mcp-console stamps the spec-standard server identity
# (its `Implementation`) on every result's `_meta`; mcptools forwards it
# verbatim into `extra`. Everything else the card needs comes from the
# tool request the client already holds.
console_server_info <- function(
  value = list(name = "mcp-console", version = "0.0.7", title = "MCP Console")
) {
  list("io.modelcontextprotocol/serverInfo" = value)
}

# Helper function to create a basic tool definition
new_tool <- function(name = NULL, description = NULL, annotations = list()) {
  ellmer::tool(
    function() NULL,
    name = name %||% "test_tool",
    description = description %||% "A test tool to test tooling",
    annotations = annotations
  )
}
