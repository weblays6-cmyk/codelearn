document.addEventListener("DOMContentLoaded", function () {
    const links = document.querySelectorAll("[data-message-unread-link]");
    const socketPath = document.body.dataset.messageNotificationsPath;
    const toastContainer = document.getElementById("messageToastContainer");

    if (!links.length || !socketPath || !toastContainer || !window.WebSocket) {
        return;
    }

    let websocket = null;
    let reconnectTimer = null;
    let reconnectDelay = 1000;
    let shouldReconnect = true;

    function showChatMessagePopup(data) {
        const currentConversation = document.querySelector(".conversation-page");
        if (
            currentConversation &&
            Number(currentConversation.dataset.conversationId) ===
                Number(data.conversation_id)
        ) {
            return;
        }
        if (
            typeof data.sender_name !== "string" ||
            typeof data.preview !== "string" ||
            typeof data.url !== "string" ||
            !data.url.startsWith("/") ||
            data.url.startsWith("//")
        ) {
            console.error("Invalid chat message notification received.");
            return;
        }

        const toast = document.createElement("a");
        toast.className = "message-toast";
        toast.href = data.url;
        toast.setAttribute("role", "status");

        const icon = document.createElement("span");
        icon.className = "message-toast-icon";
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = "✉";

        const content = document.createElement("span");
        content.className = "message-toast-content";

        const title = document.createElement("strong");
        title.textContent = "New message from " + data.sender_name;

        const preview = document.createElement("span");
        preview.className = "message-toast-preview";
        preview.textContent = data.preview;

        const close = document.createElement("span");
        close.className = "message-toast-close";
        close.setAttribute("aria-hidden", "true");
        close.textContent = "×";

        content.append(title, preview);
        toast.append(icon, content, close);
        toastContainer.append(toast);

        window.setTimeout(function () {
            toast.classList.add("message-toast-leaving");
            toast.addEventListener("transitionend", function () {
                toast.remove();
            }, { once: true });
            window.setTimeout(function () {
                toast.remove();
            }, 350);
        }, 6000);
    }

    function updateUnreadCount(count) {
        if (!Number.isInteger(count) || count < 0) {
            console.error("Invalid unread message count received.");
            return;
        }

        links.forEach(function (link) {
            const mobile = link.classList.contains("mobile-messages-link");
            const badgeClass = mobile
                ? "mobile-message-unread-count"
                : "navbar-action-badge";
            let badge = link.querySelector("." + badgeClass);

            if (count === 0) {
                if (badge) {
                    badge.remove();
                }
            } else {
                if (!badge) {
                    badge = document.createElement("span");
                    badge.className = badgeClass;
                    if (mobile) {
                        link.querySelector(".mobile-nav-icon-wrap").append(badge);
                    } else {
                        link.append(badge);
                    }
                }
                badge.textContent = count > 99 ? "99+" : String(count);
                badge.setAttribute("aria-label", count + " unread messages");
            }

            link.setAttribute(
                "aria-label",
                count > 0 ? "Messages, " + count + " unread messages" : "Messages"
            );
        });
    }

    function connect() {
        if (!shouldReconnect) {
            return;
        }

        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        websocket = new WebSocket(
            protocol + "//" + window.location.host + socketPath
        );

        websocket.addEventListener("open", function () {
            reconnectDelay = 1000;
        });

        websocket.addEventListener("message", function (event) {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "unread_count_updated") {
                    updateUnreadCount(data.count);
                } else if (data.type === "chat_message_popup") {
                    showChatMessagePopup(data);
                }
            } catch (error) {
                console.error("Invalid message notification received.", error);
            }
        });

        websocket.addEventListener("close", function (event) {
            if (!shouldReconnect || event.code === 4401) {
                return;
            }
            reconnectTimer = window.setTimeout(function () {
                reconnectDelay = Math.min(reconnectDelay * 2, 30000);
                connect();
            }, reconnectDelay);
        });
    }

    window.addEventListener("beforeunload", function () {
        shouldReconnect = false;
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
        }
        if (websocket) {
            websocket.close();
        }
    });

    connect();
});
