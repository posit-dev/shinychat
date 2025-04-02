Shiny.addCustomMessageHandler('shinychat-hide-tool-request', function (id) {
    let styleSheet = document.getElementById('shinychat-hidden-tool-requests');

    if (!styleSheet) {
        styleSheet = document.createElement('style');
        styleSheet.id = 'dynamic-styles';
        document.head.appendChild(styleSheet);
    }

    // Add the rule to the stylesheet
    const rule = `[data-tool-call-id=\"${id}\"] { display: none !important; }`;
    styleSheet.sheet.insertRule(rule, styleSheet.sheet.cssRules.length);
})