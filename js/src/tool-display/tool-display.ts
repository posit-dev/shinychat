window.Shiny.addCustomMessageHandler(
  "shinychat-hide-tool-request",
  function (id: string) {
    let styleSheet = document.getElementById("shinychat-hidden-tool-requests")

    if (!styleSheet) {
      styleSheet = document.createElement("style")
      styleSheet.id = "shinychat-hidden-tool-requests"
      document.head.appendChild(styleSheet)
    }

    // Add the rule to the stylesheet
    const rule = `[data-tool-call-id="${id}"] { display: none !important; }`
    const sheet = (styleSheet as HTMLStyleElement).sheet
    if (sheet) {
      sheet.insertRule(rule, sheet.cssRules.length)
    }
  },
)
