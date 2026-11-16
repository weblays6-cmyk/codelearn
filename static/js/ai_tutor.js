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
    const chatSearch = document.getElementById("aiChatSearch");
    const characterCount = document.getElementById("aiCharCount");
    const slashMenu = document.getElementById("slashCommandMenu");
    const sidebar = document.getElementById("aiSidebar");
    const workspace = page.querySelector(".ai-workspace");
    const sidebarToggle = document.getElementById("sidebarToggle");
    const sidebarClose = document.getElementById("aiSidebarClose");
    const sidebarBackdrop = document.getElementById("aiSidebarBackdrop");

    let conversationId = messages.dataset.chatId || "";
    let historyPage = 1;
    let historyPageCount = 1;
    let historySearchTimer;
    let pendingConfirmation;
    let historyPreviewObserver;
    let activeStream;
    let lastSentQuestion = "";
    let slashItems = [];
    let activeDraftKey = "";

    function draftKey() {
        return `ai-tutor-draft:${page.dataset.userId}:${conversationId || "new"}`;
    }

    function saveDraft() {
        try {
            window.localStorage.setItem(draftKey(), input.value);
        } catch {
            // Draft saving is best-effort when browser storage is unavailable.
        }
    }

    function restoreDraft(preserveCurrent = false) {
        try {
            const savedDraft = window.localStorage.getItem(draftKey());
            input.value = savedDraft !== null ? savedDraft : (preserveCurrent ? input.value : "");
        } catch {
            if (!preserveCurrent) input.value = "";
        }
        input.dispatchEvent(new Event("input"));
    }

    function conversationUrl(id) {
        return page.dataset.conversationUrl.replace(/0\/$/, `${id}/`);
    }

    function setSidebarOpen(open) {
        sidebar.classList.toggle("is-open", open);
        workspace.classList.toggle("sidebar-open", open);
        sidebarToggle.setAttribute("aria-expanded", String(open));
        sidebarToggle.setAttribute("aria-label", open ? "Close conversation sidebar" : "Open conversation sidebar");
        sidebarBackdrop.hidden = !open || window.innerWidth > 900;
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
        const normalizedLanguage = (language || "").toLowerCase();
        if (["python", "py", "javascript", "js", "sql"].includes(normalizedLanguage)) {
            const openButton = document.createElement("button");
            openButton.type = "button";
            openButton.className = "ai-code-copy";
            openButton.textContent = "Open in Playground";
            openButton.addEventListener("click", () => {
                const target = new URL(page.dataset.playgroundUrl, window.location.origin);
                target.searchParams.set("language", normalizedLanguage === "py" ? "python" : normalizedLanguage === "js" ? "javascript" : normalizedLanguage);
                target.searchParams.set("code", source);
                window.open(target.toString(), "_blank", "noopener");
            });
            header.append(languageLabel, copyButton, openButton);
        } else {
            header.append(languageLabel, copyButton);
        }
        const pre = document.createElement("pre");
        const code = document.createElement("code");
        code.textContent = source;
        pre.appendChild(code);
        block.append(header, pre);
        return block;
    }

    function renderMessageContent(container, content, supportsCode) {
        if (!supportsCode) {
            container.textContent = content;
            return;
        }
        if (window.marked && window.DOMPurify) {
            try {
                const safeHtml = window.DOMPurify.sanitize(window.marked.parse(content, { breaks: true }));
                const fragment = document.createElement("template");
                fragment.innerHTML = safeHtml;
                fragment.content.querySelectorAll("pre > code").forEach((code) => {
                    const languageClass = [...code.classList].find((name) => name.startsWith("language-")) || "";
                    const language = languageClass.slice("language-".length);
                    const source = code.textContent;
                    const block = createCodeBlock(language, source);
                    code.closest("pre").replaceWith(block);
                });
                container.replaceChildren(fragment.content.cloneNode(true));
                return;
            } catch (error) {
                console.error("AI Tutor Markdown rendering failed.", error);
                container.replaceChildren();
            }
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
        if (options.messageId) element.dataset.messageId = options.messageId;
        const label = document.createElement("span");
        label.className = "message-label";
        label.textContent = options.error ? "⚠ AI Tutor" : (role === "user" ? "👤 You" : "✦ AI Tutor");
        const body = document.createElement("span");
        body.className = "message-content";
        renderMessageContent(body, content, role === "assistant" && !options.error);
        element.append(label, body);
        messages.insertBefore(element, thinking);
        if (options.messageId) appendAssistantActions(element, options.messageId);
        if (role === "user") {
            messages.querySelectorAll(".user-message .message-edit").forEach((button) => button.remove());
            appendUserEditButton(element, content);
        }
        return element;
    }

    function appendUserEditButton(element, content) {
        if (!element.dataset.messageId) return;
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "message-edit";
        edit.textContent = "Edit and resend";
        edit.addEventListener("click", () => {
            input.value = content;
            document.getElementById("editMessageId").value = element.dataset.messageId;
            input.focus();
            input.dispatchEvent(new Event("input"));
        });
        element.appendChild(edit);
    }

    function enableLatestUserEdit() {
        const lastUser = [...messages.querySelectorAll(".user-message")].pop();
        if (lastUser) appendUserEditButton(lastUser, lastUser.querySelector(".message-content").textContent);
    }

    function appendAssistantActions(element, messageId) {
        const actions = document.createElement("div");
        actions.className = "message-actions";
        const copy = document.createElement("button");
        copy.type = "button";
        copy.textContent = "Copy";
        copy.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(element.querySelector(".message-content").textContent);
                copy.textContent = "Copied";
                window.setTimeout(() => { copy.textContent = "Copy"; }, 1200);
            } catch {
                copy.textContent = "Copy unavailable";
            }
        });
        actions.appendChild(copy);
        const readAloud = document.createElement("button");
        readAloud.type = "button";
        readAloud.textContent = "Read aloud";
        readAloud.addEventListener("click", () => {
            if (!("speechSynthesis" in window)) {
                readAloud.textContent = "Not supported";
                return;
            }
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(
                element.querySelector(".message-content").textContent
            );
            utterance.onend = () => { readAloud.textContent = "Read aloud"; };
            utterance.onerror = () => { readAloud.textContent = "Read aloud"; };
            window.speechSynthesis.speak(utterance);
            readAloud.textContent = "Speaking…";
        });
        actions.appendChild(readAloud);
        for (const [rating, label] of [[1, "Helpful"], [-1, "Not helpful"]]) {
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = label;
            button.addEventListener("click", async () => {
                const reason = rating < 0 ? window.prompt("What could be improved?") || "" : "";
                const data = new FormData();
                data.set("rating", String(rating));
                data.set("reason", reason);
                try {
                    await requestJson(page.dataset.feedbackUrl.replace(/0\/$/, `${messageId}/`), {
                        method: "POST",
                        body: data,
                        headers: { "X-CSRFToken": csrfToken },
                    });
                    button.textContent = "Thanks";
                    button.disabled = true;
                } catch (error) {
                    button.textContent = error.message;
                }
            });
            actions.appendChild(button);
        }
        element.appendChild(actions);
    }

    function appendContinueButton(element) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "message-edit";
        button.textContent = "Continue generating";
        button.addEventListener("click", () => {
            input.value = "Continue your previous response from where it stopped.";
            input.focus();
        });
        element.appendChild(button);
    }

    function appendFollowUps(element) {
        const group = document.createElement("div");
        group.className = "ai-follow-ups";
        ["Show me an example", "Give me a practice question", "Explain that more simply"].forEach((suggestion) => {
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = suggestion;
            button.addEventListener("click", () => {
                input.value = suggestion;
                form.requestSubmit();
            });
            group.appendChild(button);
        });
        element.appendChild(group);
    }

    function setWelcomeMessage() {
        messages.replaceChildren();
        const welcome = document.createElement("section");
        welcome.className = "ai-empty-state";
        welcome.id = "aiWelcome";
        const mark = document.createElement("div");
        mark.className = "ai-welcome-mark";
        mark.innerHTML = '<i class="bi bi-stars" aria-hidden="true"></i>';
        const eyebrow = document.createElement("p");
        eyebrow.className = "ai-welcome-eyebrow";
        eyebrow.textContent = "YOUR LEARNING COMPANION";
        const title = document.createElement("h1");
        title.textContent = `Hi ${page.dataset.firstName || "there"}, what shall we learn today?`;
        const description = document.createElement("p");
        description.textContent = "Ask a question, bring a tricky bug, or choose a starting point.";
        const suggestions = document.createElement("div");
        suggestions.className = "ai-suggestion-grid";
        const prompts = [
            ["Explain a concept", "Make a tricky topic clear", "Explain a programming concept to me with a simple example.", "bi-lightbulb"],
            ["Debug my code", "Find the cause, then fix it", "Help me debug my code. I will share the code and error.", "bi-bug"],
            ["Review my code", "Get thoughtful feedback", "Review my code for correctness, clarity, and maintainability.", "bi-code-square"],
            ["Quiz me", "Practice as you learn", "Quiz me on a programming topic, one question at a time.", "bi-patch-question"],
            ["Mock interview", "Build confidence answering", "Run a supportive mock technical interview with me.", "bi-person-video3"],
            ["Build a roadmap", "Choose your next steps", "Build a practical learning roadmap based on my goal.", "bi-signpost-split"],
        ];
        prompts.forEach(([name, detail, prompt, icon]) => {
            const button = document.createElement("button");
            button.type = "button";
            button.dataset.prompt = prompt;
            const symbol = document.createElement("i");
            symbol.className = `bi ${icon}`;
            const text = document.createElement("span");
            const heading = document.createElement("strong");
            heading.textContent = name;
            const caption = document.createElement("small");
            caption.textContent = detail;
            text.append(heading, caption);
            button.append(symbol, text);
            suggestions.append(button);
        });
        welcome.append(mark, eyebrow, title, description, suggestions);
        messages.append(welcome, thinking);
    }

    function scrollToLatest() {
        messages.scrollTop = messages.scrollHeight;
    }

    async function sendQuestion(question) {
        if (page.dataset.aiReady !== "true") return;
        lastSentQuestion = question;
        activeDraftKey = draftKey();
        const data = new FormData(form);
        data.set("question", question);
        data.set("stream", "1");
        if (conversationId) data.set("conversation_id", conversationId);
        else data.delete("conversation_id");

        thinking.classList.add("active");
        sendButton.disabled = true;
        document.getElementById("stopButton").hidden = false;
        activeStream = new AbortController();
        const assistantElement = appendMessage("assistant", "");
        const assistantBody = assistantElement.querySelector(".message-content");
        try {
            const response = await fetch(page.dataset.sendUrl, {
                method: "POST",
                body: data,
                credentials: "same-origin",
                signal: activeStream.signal,
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (!response.ok) {
                let failure = {};
                try { failure = await response.json(); } catch { /* handled with a friendly fallback */ }
                throw new Error(failure.error || "The request could not be completed.");
            }
            let buffer = "";
            let streamed = "";
            let completed = false;
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            const handleEvent = (rawEvent) => {
                const lines = rawEvent.split(/\r?\n/);
                const eventName = (lines.find((line) => line.startsWith("event:")) || "").slice(6).trim();
                const dataLine = lines.find((line) => line.startsWith("data:"));
                if (!dataLine) return;
                const payload = JSON.parse(dataLine.slice(5).trim());
                if (eventName === "token") {
                    streamed += payload.text || "";
                    assistantBody.textContent = streamed;
                    scrollToLatest();
                } else if (eventName === "done") {
                    completed = true;
                    conversationId = String(payload.conversation_id);
                    messages.dataset.chatId = conversationId;
                    const latestUserMessage = [...messages.querySelectorAll(".user-message")].pop();
                    if (latestUserMessage && payload.user_message_id) latestUserMessage.dataset.messageId = payload.user_message_id;
                    enableLatestUserEdit();
                    assistantBody.replaceChildren();
                    renderMessageContent(assistantBody, streamed, true);
                    if (payload.message_id) appendAssistantActions(assistantElement, payload.message_id);
                    appendFollowUps(assistantElement);
                    const usage = document.getElementById("aiUsageCount");
                    const current = Number(usage.textContent.split("/")[0].trim()) || 0;
                    usage.textContent = `${current + 1} / ${usage.textContent.split("/")[1].trim()}`;
                    const progress = document.querySelector(".ai-usage progress");
                    if (progress) progress.value = current + 1;
                    try { window.localStorage.removeItem(activeDraftKey); } catch { /* Best effort. */ }
                } else if (eventName === "error") {
                    if (payload.conversation_id) {
                        conversationId = String(payload.conversation_id);
                        messages.dataset.chatId = conversationId;
                    }
                    const latestUserMessage = [...messages.querySelectorAll(".user-message")].pop();
                    if (latestUserMessage && payload.user_message_id) {
                        latestUserMessage.dataset.messageId = payload.user_message_id;
                        enableLatestUserEdit();
                    }
                    assistantBody.textContent = streamed || payload.error;
                    throw new Error(payload.error || "The AI response was interrupted.");
                }
            };
            while (true) {
                const chunk = await reader.read();
                buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done });
                const events = buffer.split(/\r?\n\r?\n/);
                buffer = events.pop() || "";
                events.forEach(handleEvent);
                if (chunk.done) break;
            }
            if (buffer.trim()) handleEvent(buffer);
            if (!completed && streamed) {
                assistantBody.replaceChildren();
                renderMessageContent(assistantBody, streamed, true);
                appendContinueButton(assistantElement);
            } else if (!streamed && !completed) {
                assistantElement.remove();
            }
            scrollToLatest();
        } catch (error) {
            if (error.name === "AbortError") {
                assistantBody.textContent = assistantBody.textContent || "Generation stopped.";
                appendContinueButton(assistantElement);
            } else if (!assistantBody.textContent) {
                assistantBody.textContent = error.message;
                assistantElement.classList.add("error-message");
            }
            if (error.name !== "AbortError") {
                const retryButton = document.createElement("button");
                retryButton.type = "button";
                retryButton.className = "message-edit";
                retryButton.textContent = "Retry";
                retryButton.addEventListener("click", () => sendQuestion(lastSentQuestion));
                assistantElement.appendChild(retryButton);
            }
            scrollToLatest();
        } finally {
            activeStream = null;
            thinking.classList.remove("active");
            sendButton.disabled = false;
            document.getElementById("stopButton").hidden = true;
            input.focus();
        }
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        let question = input.value.trim();
        if (!question || sendButton.disabled) return;
        const slashModes = { explain: "explain", debug: "debug", review: "review", quiz: "quiz", interview: "interview", roadmap: "roadmap", eli5: "eli5", summarize: "summarize", test: "quiz" };
        const slash = question.match(/^\/([a-z]+)\s*/i);
        if (slash && slashModes[slash[1].toLowerCase()]) {
            document.getElementById("aiMode").value = slashModes[slash[1].toLowerCase()];
            question = question.slice(slash[0].length).trim();
            if (!question) return;
        }
        const editId = document.getElementById("editMessageId").value;
        if (editId) {
            const editTarget = [...messages.querySelectorAll(".user-message")].find((message) => message.dataset.messageId === editId);
            if (editTarget) {
                editTarget.querySelector(".message-content").textContent = question;
                editTarget.querySelector(".message-edit")?.remove();
                while (editTarget.nextElementSibling && editTarget.nextElementSibling !== thinking) {
                    editTarget.nextElementSibling.remove();
                }
            } else {
                appendMessage("user", question);
            }
        } else {
            appendMessage("user", question);
        }
        input.value = "";
        document.getElementById("editMessageId").value = "";
        input.style.height = "auto";
        scrollToLatest();
        sendQuestion(question);
    });
    document.getElementById("stopButton").addEventListener("click", () => activeStream?.abort());
    document.getElementById("sidebarNewChatButton").addEventListener("click", newChat);
    sidebarToggle.addEventListener("click", () => {
        setSidebarOpen(!sidebar.classList.contains("is-open"));
    });
    sidebarClose.addEventListener("click", () => setSidebarOpen(false));
    sidebarBackdrop.addEventListener("click", () => setSidebarOpen(false));
    sidebar.addEventListener("click", async (event) => {
        const open = event.target.closest("[data-open-conversation]");
        if (open) {
            try {
                await requestJson(conversationUrl(open.dataset.openConversation), {
                    method: "POST",
                    headers: { "X-CSRFToken": csrfToken },
                });
                window.location.reload();
            } catch (error) {
                appendMessage("assistant", error.message, { error: true });
            }
            return;
        }
        const remove = event.target.closest("[data-delete-conversation]");
        if (remove) {
            confirmAction("delete", remove.dataset.deleteConversation, remove.dataset.title);
            return;
        }
        const actionButton = event.target.closest("[data-conversation-action]");
        if (!actionButton) return;
        const action = actionButton.dataset.conversationAction;
        const endpoint = page.dataset.actionUrl.replace(/0\/$/, `${actionButton.dataset.id}/`);
        const body = new FormData();
        body.set("action", action);
        if (action === "rename") {
            const title = window.prompt("Conversation title", actionButton.closest(".ai-history-entry").querySelector(".ai-history-open").textContent.trim());
            if (!title) return;
            body.set("title", title);
        }
        try {
            const result = await requestJson(endpoint, { method: "POST", body, headers: { "X-CSRFToken": csrfToken } });
            if (action === "share" && result.url) {
                await navigator.clipboard.writeText(result.url);
                window.alert("Read-only share link copied.");
            }
            window.location.reload();
        } catch (error) {
            window.alert(error.message);
        }
    });
    document.getElementById("voiceButton").addEventListener("click", () => {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            appendMessage("assistant", "Voice input is not available in this browser.", { error: true });
            return;
        }
        const recognition = new SpeechRecognition();
        recognition.lang = document.documentElement.lang || "en-US";
        recognition.onresult = (event) => {
            input.value = `${input.value} ${event.results[0][0].transcript}`.trim();
            input.dispatchEvent(new Event("input"));
        };
        recognition.onerror = () => appendMessage("assistant", "Voice input could not be started. Please type your message.", { error: true });
        recognition.start();
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
        input.style.height = `${Math.min(input.scrollHeight, 200)}px`;
        if (characterCount) characterCount.textContent = `${input.value.length.toLocaleString()} / 20,000`;
        saveDraft();
        if (slashMenu) {
            const slash = input.value.match(/^\/([a-z]*)$/i);
            slashMenu.hidden = !slash;
            slashItems.forEach((button) => {
                button.hidden = Boolean(slash && !button.dataset.command.slice(1).startsWith(slash[1].toLowerCase()));
            });

            document.getElementById("aiAttachment")?.addEventListener("change", (event) => {
                const label = event.currentTarget.closest(".ai-attachment").querySelector("span");
                const file = event.currentTarget.files[0];
                label.textContent = file ? file.name : "Attach file";
                label.title = file ? file.name : "";
            });
        }
    });

    function setPrompt(prompt) {
        input.value = prompt;
        input.focus();
        input.dispatchEvent(new Event("input"));
    }

    window.setPrompt = setPrompt;

    messages.addEventListener("click", (event) => {
        const prompt = event.target.closest("[data-prompt]");
        if (prompt) setPrompt(prompt.dataset.prompt);
    });

    chatSearch?.addEventListener("input", () => {
        const query = chatSearch.value.trim().toLocaleLowerCase();
        document.querySelectorAll(".ai-history-entry").forEach((entry) => {
            entry.hidden = query && !entry.textContent.toLocaleLowerCase().includes(query);
        });
        document.querySelectorAll(".ai-history-groups section").forEach((group) => {
            group.hidden = ![...group.querySelectorAll(".ai-history-entry")].some((entry) => !entry.hidden);
        });
    });

    if (slashMenu) {
        slashItems = [...slashMenu.querySelectorAll("[data-command]")];
        slashMenu.addEventListener("click", (event) => {
            const command = event.target.closest("[data-command]");
            if (!command) return;
            input.value = `${command.dataset.command} `;
            input.focus();
            input.dispatchEvent(new Event("input"));
        });
    }

    document.getElementById("removeContextButton")?.addEventListener("click", async () => {
        try {
            await requestJson(page.dataset.clearContextUrl, {
                method: "POST",
                headers: { "X-CSRFToken": csrfToken },
            });
        } catch {
            appendMessage("assistant", "We could not clear the saved context. Please refresh and try again.", { error: true });
            return;
        }
        document.querySelector(".ai-context-chip")?.remove();
    });

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
            input.dispatchEvent(new Event("input"));
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
            restoreDraft();
            enableLatestUserEdit();
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
        element.dataset.messageId = message.id;
        const label = document.createElement("span");
        label.className = "message-label";
        label.textContent = message.role === "user" ? "👤 You" : "✦ AI Tutor";
        const body = document.createElement("span");
        body.className = "message-content";
        renderMessageContent(body, message.content, message.role === "assistant");
        element.append(label, body);
        if (message.role === "assistant" && message.id) {
            appendAssistantActions(element, message.id);
        }
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
        const lastUserMessage = [...messages.querySelectorAll(".user-message")].pop();
        if (lastUserMessage) {
            input.value = lastUserMessage.querySelector(".message-content").textContent;
            document.getElementById("editMessageId").value = lastUserMessage.dataset.messageId || "";
            form.requestSubmit();
        }
    });
    document.addEventListener("keydown", (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
            event.preventDefault();
            newChat();
        }
        if (event.key === "Escape") {
            confirmModal.hidden = true;
            closeHistory();
            setSidebarOpen(false);
        }
    });

    let touchStart = null;
    document.addEventListener("touchstart", (event) => {
        const target = event.target;
        if (target.closest("input, textarea, select, [contenteditable=true]")) {
            touchStart = null;
            return;
        }
        touchStart = { x: event.changedTouches[0].clientX, y: event.changedTouches[0].clientY };
    }, { passive: true });
    document.addEventListener("touchend", (event) => {
        if (!touchStart) return;
        const deltaX = event.changedTouches[0].clientX - touchStart.x;
        const deltaY = event.changedTouches[0].clientY - touchStart.y;
        if (touchStart.x < 32 && deltaX > 80 && Math.abs(deltaY) < 60 && window.innerWidth <= 850) {
            setSidebarOpen(true);
        }
        touchStart = null;
    }, { passive: true });
    window.addEventListener("resize", () => {
        if (sidebar.classList.contains("is-open")) {
            setSidebarOpen(true);
        }
    });

    restoreDraft(!conversationId);

    messages.querySelectorAll(".message-content").forEach((content) => {
        const message = content.closest(".message");
        const role = message.dataset.role;
        const value = content.textContent;
        content.replaceChildren();
        renderMessageContent(content, value, role === "assistant");
        if (role === "assistant" && message.dataset.messageId) {
            appendAssistantActions(message, message.dataset.messageId);
        }
    });
    enableLatestUserEdit();
})();
