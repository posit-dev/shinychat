contents_shinychat <- function(client) {
  # TODO(garrick): placeholder, will be replaces with S7 generic
  check_ellmer_chat(client)

  client_msgs <- map(client$get_turns(), function(turn) {
    content <- ellmer::contents_markdown(turn)
    if (is.null(content) || identical(content, "")) {
      return(NULL)
    }
    list(role = turn@role, content = content)
  })

  compact(client_msgs)
}
