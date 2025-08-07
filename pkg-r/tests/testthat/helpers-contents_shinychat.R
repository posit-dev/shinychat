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

# Helper function to create a basic tool definition
new_tool <- function(name = NULL, description = NULL, annotations = list()) {
  ellmer::tool(
    function() NULL,
    name = name %||% "test_tool",
    description = description %||% "A test tool to test tooling",
    annotations = annotations
  )
}
