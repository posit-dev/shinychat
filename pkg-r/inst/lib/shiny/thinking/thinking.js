(function() {
  const thinkingBlocks = new Map();

  function findStreamingMessage() {
    const messages = document.querySelector('shiny-chat-messages');
    if (!messages) return null;
    return messages.querySelector('shiny-chat-message[streaming]');
  }

  function createThinkingContainer(id) {
    const wrapper = document.createElement('div');
    wrapper.className = 'shinychat-thinking';
    wrapper.dataset.id = id;
    wrapper.dataset.open = 'false';

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'shinychat-thinking-toggle';
    button.setAttribute('aria-expanded', 'false');

    const preview = document.createElement('span');
    preview.className = 'shinychat-thinking-preview';
    preview.textContent = '…';

    button.appendChild(preview);

    const content = document.createElement('div');
    content.className = 'shinychat-thinking-content';

    wrapper.appendChild(button);
    wrapper.appendChild(content);

    return { wrapper, preview, content, fullText: '' };
  }

  function handleThinkingMessage(payload) {
    const { id, type, content: text } = payload;

    if (type === 'start') {
      const message = findStreamingMessage();
      if (!message) {
        setTimeout(() => handleThinkingMessage(payload), 50);
        return;
      }

      const parts = createThinkingContainer(id);
      thinkingBlocks.set(id, parts);

      const target = message.querySelector('shiny-markdown-stream') || message;
      target.insertAdjacentElement('afterbegin', parts.wrapper);
    }

    if (type === 'update' || type === 'start') {
      const parts = thinkingBlocks.get(id);
      if (!parts) return;

      if (text) {
        parts.fullText += text;
        parts.content.textContent = parts.fullText;

        const previewText = parts.fullText.trim().split('\n')[0];
        parts.preview.textContent = previewText.length > 60
          ? previewText.slice(0, 60) + '…'
          : previewText || '…';
      }
    }

    if (type === 'done') {
      const parts = thinkingBlocks.get(id);
      if (!parts) return;

      if (!parts.fullText.trim()) {
        parts.wrapper.remove();
        thinkingBlocks.delete(id);
      }
    }
  }

  function handleThinkingClick(event) {
    const wrapper = event.target.closest('.shinychat-thinking');
    if (!wrapper) return;

    const button = wrapper.querySelector('button');
    const isOpen = wrapper.dataset.open === 'true';
    wrapper.dataset.open = (!isOpen).toString();
    if (button) {
      button.setAttribute('aria-expanded', (!isOpen).toString());
    }
  }

  function register() {
    if (!window.Shiny) return;
    Shiny.addCustomMessageHandler('shinychat-thinking', handleThinkingMessage);
  }

  document.addEventListener('click', handleThinkingClick);

  if (window.Shiny) {
    register();
  } else {
    document.addEventListener('shiny:connected', register);
  }
})();
