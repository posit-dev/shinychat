# Get the current greeting content

Get the current greeting content

## Usage

``` r
chat_get_greeting(id, session = getDefaultReactiveDomain())
```

## Arguments

- id:

  The ID of the chat element

- session:

  The Shiny session object

## Value

A character string with the current greeting content, or `NULL` if no
greeting is set or has been cleared.
