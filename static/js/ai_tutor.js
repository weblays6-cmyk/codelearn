(() => {
    const page = document.querySelector(".ai-tutor-page[data-send-url]");
    if (!page) return;

    const form = document.getElementById("aiForm");
    const input = document.getElementById("questionInput");
    const sendButton = document.getElementById("askButton");
    const messages = document.getElementById("messages");
    const thinking = document.getElementById("thinking");
    const historyModal = document.getElementById("historyModal");
    const historyList = document.getElementById("historyList");
    const historyFeedback = document.getElementById("historyFeedback");
    const historySearch = document.getElementById("historySearch");
    const confirmModal = document.getElementById("historyConfirmModal");
    const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;

    let conversationId = messages.dataset.chatId || "";
    let historyPage = 1;
    let historyPageCount = 1;
    let historySearchTimer;
    let pendingConfirmation;
    let historyPreviewObserver;

    function conversationUrl(id) {
        return page.dataset.conversationUrl.replace(/0\/$/, `${id}/`);
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                ...(options.headers || {}),
            },
        });
        let data;
        try {
            data = await response.json();
        } catch {
            throw new Error("The server returned an invalid response. Please try again.");
        }
        if (!response.ok) {
            throw new Error(data.error || "The request could not be completed.");
        }
        return data;
    }

    function createCodeBlock(language, source) {
        const block = document.createElement("div");
        block.className = "ai-code-block";
        const header = document.createElement("div");
        header.className = "ai-code-header";
        const languageLabel = document.createElement("span");
        languageLabel.textContent = language || "code";
        const copyButton = document.createElement("button");
        copyButton.type = "button";
        copyButton.className = "ai-code-copy";
        copyButton.textContent = "Copy";
        copyButton.setAttribute("aria-label", "Copy code block");
        copyButton.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(source);
                copyButton.textContent = "Copied";
                window.setTimeout(() => { copyButton.textContent = "Copy"; }, 1400);
            } catch {
                copyButton.textContent = "Copy unavailable";
            }
        });
        const pre = document.createElement("pre");
        const code = document.createElement("code");
        code.textContent = source;
        pre.appendChild(code);
        header.append(languageLabel, copyButton);
        block.append(header, pre);
        return block;
    }

    function renderMessageContent(container, content, supportsCode) {
        if (!supportsCode) {
            container.textContent = content;
            return;
        }
        const pattern = /```([a-zA-Z0-9_+#.-]*)[ \t]*\n([\s\S]*?)```/g;
        let lastIndex = 0;
        let match;
        while ((match = pattern.exec(content)) !== null) {
            const text = content.slice(lastIndex, match.index).trim();
            if (text) {
                const paragraph = document.createElement("p");
                paragraph.className = "ai-answer-text";
                paragraph.textContent = text;
                container.appendChild(paragraph);
            }
            container.appendChild(createCodeBlock(match[1], match[2]));
            lastIndex = pattern.lastIndex;
        }
        const remainder = content.slice(lastIndex).trim();
        if (remainder) {
            const paragraph = document.createElement("p");
            paragraph.className = "ai-answer-text";
            paragraph.textContent = remainder;
            container.appendChild(paragraph);
        }
        if (!container.childNodes.length) container.textContent = content;
    }

    function appendMessage(role, content, options = {}) {
        const element = document.createElement("div");
        element.className = `message ${role === "user" ? "user-message" : "ai-message"}`;
        if (options.error) element.classList.add("error-message");
        element.dataset.role = role;
        const label = document.createElement("span");
        label.className = "message-label";
        label.textContent = options.error ? "⚠ AI Tutor" : (role === "user" ? "👤 You" : "✦ AI Tutor");
        const body = document.createElement("span");
        body.className = "message-content";
        renderMessageContent(body, content, role === "assistant" && !options.error);
        element.append(label, body);
        messages.insertBefore(element, thinking);
        return element;
    }

    function setWelcomeMessage() {
        messages.replaceChildren();
        const welcome = document.createElement("div");
        welcome.className = "message ai-message";
        welcome.id = "defaultMessage";
        const label = document.createElement("span");
        label.className = "message-label";
        label.textContent = "✦ AI Tutor";
        const text = document.createElement("span");
        text.className = "message-content";
        text.textContent = `👋 Hey! I'm your ${page.dataset.siteName} AI Tutor.\n\nAsk me anything about programming. I can explain concepts, debug your code, give examples and help you practice.`;
        welcome.append(label, text);
        messages.append(welcome, thinking);
    }

    function scrollToLatest() {
        messages.scrollTop = messages.scrollHeight;
    }

    async function sendQuestion(question) {
        const data = new FormData(form);
        data.set("question", question);
        if (conversationId) data.set("conversation_id", conversationId);
        else data.delete("conversation_id");

        thinking.classList.add("active");
        sendButton.disabled = true;
        try {
            const result = await requestJson(page.dataset.sendUrl, {
                method: "POST",
                body: data,
            });
            if (conversationId && String(result.conversation_id) !== conversationId) {
                setWelcomeMessage();
                appendMessage("user", question);
            }
            conversationId = String(result.conversation_id);
            messages.dataset.chatId = conversationId;
            appendMessage("assistant", result.answer);
            scrollToLatest();
        } catch (error) {
            appendMessage("assistant", error.message, { error: true });
            scrollToLatest();
        } finally {
            thinking.classList.remove("active");
            sendButton.disabled = false;
            input.focus();
        }
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const question = input.value.trim();
        if (!question || sendButton.disabled) return;
        appendMessage("user", question);
        input.value = "";
        input.style.height = "auto";
        scrollToLatest();
        sendQuestion(question);
    });

    input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();

        if (input.value.trim() && !sendButton.disabled) {
            form.requestSubmit();
        }
    }
});

    input.addEventListener("input", () => {
        input.style.height = "auto";
        input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
    });

    window.setPrompt = (prompt) => {
        input.value = prompt;
        input.focus();
        input.dispatchEvent(new Event("input"));
    };

    async function newChat() {
        try {
            await requestJson(page.dataset.newChatUrl, {
                method: "POST",
                headers: { "X-CSRFToken": csrfToken },
            });
            conversationId = "";
            messages.dataset.chatId = "";
            messages.dataset.hasOlder = "false";
            messages.dataset.beforeId = "";
            setWelcomeMessage();
            input.value = "";
            closeHistory();
            input.focus();
        } catch (error) {
            appendMessage("assistant", error.message, { error: true });
        }
    }

    function conversationRow(item) {
        const row = document.createElement("div");
        row.className = "history-row";
        const open = document.createElement("button");
        open.type = "button";
        open.className = "history-item";
        open.setAttribute("aria-label", `Open conversation: ${item.title}`);
        const copy = document.createElement("span");
        copy.className = "history-item-copy";
        const title = document.createElement("span");
        title.className = "history-title";
        title.textContent = item.title;
        const preview = document.createElement("span");
        preview.className = "history-preview";
        preview.textContent = "Loading preview…";
        const metadata = document.createElement("span");
        metadata.className = "history-meta";
        const date = document.createElement("span");
        date.className = "history-date";
        date.textContent = new Date(item.updated_at).toLocaleString(undefined, {
            dateStyle: "medium",
            timeStyle: "short",
        });
        const count = document.createElement("span");
        count.className = "history-count";
        count.textContent = `${item.message_count} ${item.message_count === 1 ? "message" : "messages"}`;
        metadata.append(date, count);
        copy.append(title, preview, metadata);
        const openLabel = document.createElement("span");
        openLabel.className = "history-open-label";
        openLabel.innerHTML = 'Open <i class="bi bi-arrow-right" aria-hidden="true"></i>';
        open.append(copy, openLabel);
        open.addEventListener("click", () => loadConversation(item.id));
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "history-delete";
        remove.innerHTML = '<i class="bi bi-trash3" aria-hidden="true"></i><span class="visually-hidden">Delete</span>';
        remove.setAttribute("aria-label", `Delete ${item.title}`);
        remove.addEventListener("click", () => confirmAction("delete", item.id, item.title));
        row.append(open, remove);

        if (historyPreviewObserver) {
            preview.dataset.conversationId = item.id;
            historyPreviewObserver.observe(preview);
        } else {
            loadConversationPreview(item.id, preview);
        }
        return row;
    }

    async function loadConversationPreview(id, preview) {
        if (!preview.isConnected || preview.dataset.loading === "true") return;
        preview.dataset.loading = "true";
        try {
            const data = await requestJson(conversationUrl(id));
            const latestUserMessage = [...data.messages].reverse().find((message) => message.role === "user");
            preview.textContent = latestUserMessage
                ? latestUserMessage.content.replace(/\s+/g, " ").trim()
                : "No messages in this conversation yet.";
        } catch {
            preview.textContent = "Preview unavailable";
        }
    }

    async function loadHistory(pageNumber = 1) {
        historyPage = pageNumber;
        historyFeedback.textContent = "Loading conversations…";
        historyList.replaceChildren();
        const url = new URL(page.dataset.historyUrl, window.location.origin);
        url.searchParams.set("page", String(historyPage));
        if (historySearch.value.trim()) url.searchParams.set("search", historySearch.value.trim());
        try {
            const data = await requestJson(url);
            if (historyPreviewObserver) historyPreviewObserver.disconnect();
            historyPreviewObserver = "IntersectionObserver" in window
                ? new IntersectionObserver((entries, observer) => {
                    entries.forEach((entry) => {
                        if (entry.isIntersecting) {
                            observer.unobserve(entry.target);
                            loadConversationPreview(entry.target.dataset.conversationId, entry.target);
                        }
                    });
                }, { root: historyList, rootMargin: "80px" })
                : null;
            historyList.replaceChildren();
            data.items.forEach((item) => historyList.appendChild(conversationRow(item)));
            if (!data.items.length) {
                const empty = document.createElement("div");
                empty.className = "empty-history";
                const icon = document.createElement("span");
                icon.className = "empty-history-icon";
                icon.innerHTML = '<i class="bi bi-chat-square-text" aria-hidden="true"></i>';
                const heading = document.createElement("h4");
                heading.textContent = historySearch.value.trim()
                    ? "No matching conversations"
                    : "No saved conversations yet";
                const description = document.createElement("p");
                description.textContent = historySearch.value.trim()
                    ? "Try another title or search phrase."
                    : "Your AI Tutor conversations will appear here.";
                empty.append(icon, heading, description);
                if (!historySearch.value.trim()) {
                    const startChat = document.createElement("button");
                    startChat.type = "button";
                    startChat.className = "history-start-chat";
                    startChat.textContent = "Start a new chat";
                    startChat.addEventListener("click", newChat);
                    empty.appendChild(startChat);
                }
                historyList.appendChild(empty);
            }
            historyPage = data.page;
            historyPageCount = data.num_pages;
            document.getElementById("historyPageLabel").textContent = `${historyPage} / ${historyPageCount}`;
            document.getElementById("historyPrevious").disabled = historyPage <= 1;
            document.getElementById("historyNext").disabled = historyPage >= historyPageCount;
            historyFeedback.textContent = "";
        } catch (error) {
            historyFeedback.textContent = error.message;
        }
    }

    async function showHistory() {
        historyModal.hidden = false;
        historyModal.classList.add("active");
        document.body.classList.add("history-modal-open");
        await loadHistory(1);
        document.getElementById("historyCloseButton").focus();
    }

    function closeHistory() {
        historyModal.classList.remove("active");
        historyModal.hidden = true;
        document.body.classList.remove("history-modal-open");
        document.getElementById("historyButton").focus();
    }

    async function loadConversation(id) {
        historyFeedback.textContent = "Loading conversation…";
        try {
            const data = await requestJson(conversationUrl(id), {
                method: "POST",
                headers: { "X-CSRFToken": csrfToken },
            });
            conversationId = String(data.conversation_id);
            messages.dataset.chatId = conversationId;
            messages.replaceChildren();
            if (data.has_older_messages) {
                const earlier = document.createElement("button");
                earlier.type = "button";
                earlier.className = "load-earlier-btn";
                earlier.id = "loadEarlierButton";
                earlier.textContent = "Load earlier messages";
                messages.appendChild(earlier);
            }
            messages.appendChild(thinking);
            data.messages.forEach((message) => appendLoadedMessage(message));
            messages.dataset.hasOlder = String(data.has_older_messages);
            messages.dataset.beforeId = data.before_id || "";
            closeHistory();
            scrollToLatest();
        } catch (error) {
            historyFeedback.textContent = error.message;
        }
    }

    function appendLoadedMessage(message, beforeNode = thinking) {
        const element = document.createElement("div");
        element.className = `message ${message.role === "user" ? "user-message" : "ai-message"}`;
        element.dataset.role = message.role;
        const label = document.createElement("span");
        label.className = "message-label";
        label.textContent = message.role === "user" ? "👤 You" : "✦ AI Tutor";
        const body = document.createElement("span");
        body.className = "message-content";
        renderMessageContent(body, message.content, message.role === "assistant");
        element.append(label, body);
        messages.insertBefore(element, beforeNode);
    }

    async function loadEarlierMessages() {
        const before = messages.dataset.beforeId;
        if (!conversationId || !before) return;
        const url = new URL(conversationUrl(conversationId), window.location.origin);
        url.searchParams.set("before", before);
        try {
            const data = await requestJson(url);
            const button = document.getElementById("loadEarlierButton");
            const anchor = button ? button.nextSibling : messages.firstElementChild;
            data.messages.forEach((message) => appendLoadedMessage(message, anchor));
            messages.dataset.beforeId = data.before_id || "";
            if (!data.has_older_messages && button) button.remove();
        } catch (error) {
            appendMessage("assistant", error.message, { error: true });
        }
    }

    function confirmAction(action, id = "", title = "") {
        pendingConfirmation = { action, id };
        document.getElementById("historyConfirmTitle").textContent =
            action === "clear" ? "Clear all AI Tutor history?" : "Delete this conversation?";
        document.getElementById("historyConfirmText").textContent =
            action === "clear"
                ? "All of your saved AI Tutor conversations will be permanently deleted."
                : `“${title}” and all of its messages will be permanently deleted.`;
        document.getElementById("historyConfirmAccept").textContent =
            action === "clear" ? "Clear history" : "Delete";
        confirmModal.hidden = false;
    }

    async function acceptConfirmation() {
        if (!pendingConfirmation) return;
        const pending = pendingConfirmation;
        const url = pending.action === "clear"
            ? page.dataset.clearHistoryUrl
            : conversationUrl(pending.id);
        try {
            await requestJson(url, {
                method: "DELETE",
                headers: { "X-CSRFToken": csrfToken },
            });
            confirmModal.hidden = true;
            pendingConfirmation = null;
            if (pending.action === "clear" || String(pending.id) === conversationId) {
                conversationId = "";
                messages.dataset.chatId = "";
                messages.dataset.hasOlder = "false";
                messages.dataset.beforeId = "";
                setWelcomeMessage();
            }
            await loadHistory(historyPage);
        } catch (error) {
            document.getElementById("historyConfirmText").textContent = error.message;
        }
    }

    document.getElementById("newChatButton").addEventListener("click", newChat);
    document.getElementById("historyButton").addEventListener("click", showHistory);
    document.getElementById("clearHistoryButton").addEventListener("click", () => confirmAction("clear"));
    document.getElementById("historyCloseButton").addEventListener("click", closeHistory);
    document.getElementById("historyConfirmCancel").addEventListener("click", () => {
        confirmModal.hidden = true;
        pendingConfirmation = null;
    });
    document.getElementById("historyConfirmAccept").addEventListener("click", acceptConfirmation);
    document.getElementById("historyPrevious").addEventListener("click", () => loadHistory(historyPage - 1));
    document.getElementById("historyNext").addEventListener("click", () => loadHistory(historyPage + 1));
    document.getElementById("historyList").addEventListener("click", (event) => {
        if (event.target.closest("#loadEarlierButton")) loadEarlierMessages();
    });
    historySearch.addEventListener("input", () => {
        window.clearTimeout(historySearchTimer);
        historySearchTimer = window.setTimeout(() => loadHistory(1), 250);
    });
    historyModal.addEventListener("click", (event) => {
        if (event.target === historyModal) closeHistory();
    });
    messages.addEventListener("click", (event) => {
        if (event.target.closest("#loadEarlierButton")) loadEarlierMessages();
    });
    document.getElementById("regenerateButton")?.addEventListener("click", () => {
        const lastQuestion = messages.querySelector(".user-message .message-content");
        if (lastQuestion) {
            input.value = lastQuestion.textContent;
            form.requestSubmit();
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            confirmModal.hidden = true;
            closeHistory();
        }
    });

    messages.querySelectorAll(".message-content").forEach((content) => {
        const message = content.closest(".message");
        const role = message.dataset.role;
        const value = content.textContent;
        content.replaceChildren();
        renderMessageContent(content, value, role === "assistant");
    });
})();
