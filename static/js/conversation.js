document.addEventListener("DOMContentLoaded", function () {

    /* =====================================================
       ELEMENTS
    ===================================================== */

    const page =
        document.querySelector(".conversation-page");

    const messagesBox =
        document.getElementById("chatMessages");

    const typingIndicator =
        document.getElementById("typingIndicator");

    const form =
        document.getElementById("messageForm");

    const textarea =
        document.getElementById("messageInput");

    const sendButton =
        document.getElementById("sendMessageBtn");

    const emojiButton =
        document.getElementById("emojiBtn");

    const emojiPicker =
        document.getElementById("emojiPicker");

    const closeEmojiPicker =
        document.getElementById("closeEmojiPicker");

    const attachButton =
        document.getElementById("attachBtn");

    const fileInput =
        document.getElementById("messageFileInput");

    const sayHelloButton =
        document.getElementById("sayHelloBtn");

    const replyPreview =
        document.getElementById("replyPreview");

    const replyPreviewText =
        document.getElementById("replyPreviewText");

    const cancelReply =
        document.getElementById("cancelReply");


    if (
        !page ||
        !messagesBox ||
        !form ||
        !textarea
    ) {
        return;
    }


    /* =====================================================
       URLS
    ===================================================== */

    const sendUrl =
        form.dataset.sendUrl;

    const statusUrl =
        messagesBox.dataset.statusUrl;


    /* =====================================================
       STATE
    ===================================================== */

    let isSending = false;

    let replyText = "";

    let selectedFiles = [];

    let statusTimer = null;
    let websocket = null;
    let reconnectTimer = null;
    let reconnectDelay = 1000;
    let shouldReconnect = true;
    let isLocallyTyping = false;
    let typingIdleTimer = null;
    let typingHeartbeatTimer = null;
    let remoteTypingTimer = null;


    /* =====================================================
       CSRF
    ===================================================== */

    function getCookie(name) {

        const cookies =
            document.cookie
                ? document.cookie.split(";")
                : [];

        for (let cookie of cookies) {

            cookie = cookie.trim();

            if (
                cookie.startsWith(
                    name + "="
                )
            ) {

                return decodeURIComponent(
                    cookie.substring(
                        name.length + 1
                    )
                );

            }
        }

        return "";
    }


    const csrfToken =
        getCookie("csrftoken");


    function sendTypingStatus(isTyping) {
        if (
            websocket &&
            websocket.readyState === WebSocket.OPEN
        ) {
            websocket.send(JSON.stringify({
                type: "typing",
                is_typing: isTyping
            }));
        }
    }


    function stopLocalTyping() {
        if (typingIdleTimer) {
            clearTimeout(typingIdleTimer);
            typingIdleTimer = null;
        }
        if (typingHeartbeatTimer) {
            clearInterval(typingHeartbeatTimer);
            typingHeartbeatTimer = null;
        }
        if (isLocallyTyping) {
            sendTypingStatus(false);
            isLocallyTyping = false;
        }
    }


    function startLocalTyping() {
        if (!textarea.value.trim()) {
            stopLocalTyping();
            return;
        }
        if (!isLocallyTyping) {
            isLocallyTyping = true;
            sendTypingStatus(true);
            typingHeartbeatTimer = window.setInterval(
                function () {
                    sendTypingStatus(true);
                },
                2000
            );
        }
        if (typingIdleTimer) {
            clearTimeout(typingIdleTimer);
        }
        typingIdleTimer = window.setTimeout(stopLocalTyping, 1600);
    }


    function showRemoteTyping(isTyping) {
        if (!typingIndicator) {
            return;
        }
        typingIndicator.hidden = !isTyping;
        if (remoteTypingTimer) {
            clearTimeout(remoteTypingTimer);
            remoteTypingTimer = null;
        }
        if (isTyping) {
            remoteTypingTimer = window.setTimeout(
                function () {
                    typingIndicator.hidden = true;
                },
                5000
            );
        }
    }


    textarea.addEventListener("input", startLocalTyping);


    /* =====================================================
       HTML ESCAPE
    ===================================================== */

    function escapeHtml(value) {

        const div =
            document.createElement("div");

        div.textContent =
            value || "";

        return div.innerHTML;
    }


    /* =====================================================
       SCROLL
    ===================================================== */

    function scrollToBottom() {

        messagesBox.scrollTop =
            messagesBox.scrollHeight;

    }


    function isNearBottom() {

        return (
            messagesBox.scrollHeight -
            messagesBox.scrollTop -
            messagesBox.clientHeight
        ) < 180;

    }


    /* =====================================================
   INITIAL POSITION
   Always open chat at latest message.
===================================================== */

messagesBox.classList.add("chat-positioning");

function scrollChatToLatest() {

    messagesBox.scrollTop =
        messagesBox.scrollHeight;

}

function showLatestMessageImmediately() {

    // Initial position
    scrollChatToLatest();

    // Wait for layout
    requestAnimationFrame(function () {

        scrollChatToLatest();

        requestAnimationFrame(function () {

            scrollChatToLatest();

            // Wait for images to finish loading
            const images =
                messagesBox.querySelectorAll("img");

            if (images.length === 0) {

                messagesBox.classList.remove(
                    "chat-positioning"
                );

                return;
            }

            let remaining =
                images.length;

            function imageLoaded() {

                remaining--;

                if (remaining <= 0) {

                    scrollChatToLatest();

                    messagesBox.classList.remove(
                        "chat-positioning"
                    );

                }

            }

            images.forEach(function (img) {

                if (img.complete) {

                    imageLoaded();

                } else {

                    img.addEventListener(
                        "load",
                        imageLoaded,
                        { once: true }
                    );

                    img.addEventListener(
                        "error",
                        imageLoaded,
                        { once: true }
                    );

                }

            });

        });

    });

}

showLatestMessageImmediately();



    /* =====================================================
       TEXTAREA RESIZE
    ===================================================== */

    function resizeTextarea() {

        textarea.style.height =
            "auto";

        textarea.style.height =
            Math.min(
                textarea.scrollHeight,
                140
            ) + "px";

    }


    textarea.addEventListener(
        "input",
        resizeTextarea
    );


    resizeTextarea();


    /* =====================================================
       REPLY
    ===================================================== */

    function setReply(text) {

        replyText =
            (text || "").trim();

        if (!replyText) {
            return;
        }


        if (replyPreviewText) {

            replyPreviewText.textContent =
                replyText.length > 140
                    ? replyText.substring(
                        0,
                        140
                    ) + "..."
                    : replyText;

        }


        if (replyPreview) {

            replyPreview.hidden =
                false;

            replyPreview.setAttribute(
                "aria-hidden",
                "false"
            );

        }


        textarea.focus();

    }


    function clearReply() {

        replyText = "";


        if (replyPreview) {

            replyPreview.hidden =
                true;

            replyPreview.setAttribute(
                "aria-hidden",
                "true"
            );

        }


        if (replyPreviewText) {

            replyPreviewText.textContent =
                "";

        }

    }


    /*
       IMPORTANT:
       Chat open chesinappudu Replying to message
       automatic ga kanipinchakudadhu.
    */

    clearReply();


    /* =====================================================
       REPLY BUTTON
    ===================================================== */

    document.addEventListener(
        "click",
        function (event) {

            const button =
                event.target.closest(
                    ".message-reply-btn"
                );

            if (!button) {
                return;
            }


            setReply(
                button.dataset.messageText
            );

        }
    );


    /* =====================================================
       CANCEL REPLY
    ===================================================== */

    if (cancelReply) {

        cancelReply.addEventListener(
            "click",
            function () {

                clearReply();

                textarea.focus();

            }
        );

    }


    /* =====================================================
       EMOJI PICKER
    ===================================================== */

    function closeEmojiPickerNow() {

        if (emojiPicker) {

            emojiPicker.hidden =
                true;

        }

    }


    if (
        emojiButton &&
        emojiPicker
    ) {

        emojiButton.addEventListener(
            "click",
            function (event) {

                event.stopPropagation();

                emojiPicker.hidden =
                    !emojiPicker.hidden;

            }
        );


        emojiPicker.addEventListener(
            "click",
            function (event) {

                const emojiButtonClicked =
                    event.target.closest(
                        "[data-emoji]"
                    );

                if (!emojiButtonClicked) {
                    return;
                }


                const emoji =
                    emojiButtonClicked.dataset.emoji;


                const start =
                    textarea.selectionStart;


                const end =
                    textarea.selectionEnd;


                const currentValue =
                    textarea.value;


                textarea.value =
                    currentValue.substring(
                        0,
                        start
                    ) +
                    emoji +
                    currentValue.substring(
                        end
                    );


                textarea.selectionStart =
                    start + emoji.length;


                textarea.selectionEnd =
                    start + emoji.length;


                resizeTextarea();

                textarea.focus();

                closeEmojiPickerNow();

            }
        );

    }


    if (closeEmojiPicker) {

        closeEmojiPicker.addEventListener(
            "click",
            function () {

                closeEmojiPickerNow();

                textarea.focus();

            }
        );

    }


    document.addEventListener(
        "click",
        function (event) {

            if (
                emojiPicker &&
                !emojiPicker.hidden &&
                !emojiPicker.contains(
                    event.target
                ) &&
                event.target !== emojiButton
            ) {

                closeEmojiPickerNow();

            }

        }
    );


    /* =====================================================
       FILE UPLOAD
    ===================================================== */

    if (
        attachButton &&
        fileInput
    ) {

        attachButton.addEventListener(
            "click",
            function () {

                closeEmojiPickerNow();

                fileInput.click();

            }
        );


        fileInput.addEventListener(
            "change",
            function () {

                const files =
                    Array.from(
                        fileInput.files || []
                    );


                if (!files.length) {
                    return;
                }


                selectedFiles =
                    selectedFiles.concat(
                        files
                    );


                fileInput.value =
                    "";


                renderSelectedFiles();

            }
        );

    }


    /* =====================================================
       SELECTED FILE PREVIEW
    ===================================================== */

    function getFilePreviewContainer() {

        let container =
            document.getElementById(
                "selectedFiles"
            );


        if (!container) {

            container =
                document.createElement(
                    "div"
                );

            container.id =
                "selectedFiles";

            container.className =
                "selected-files";


            form.parentNode.insertBefore(
                container,
                form
            );

        }


        return container;

    }


    function renderSelectedFiles() {

        const container =
            getFilePreviewContainer();


        container.innerHTML =
            "";


        if (!selectedFiles.length) {

            container.remove();

            return;

        }


        selectedFiles.forEach(
            function (file, index) {

                const item =
                    document.createElement(
                        "div"
                    );

                item.className =
                    "selected-file";


                const icon =
                    document.createElement(
                        "i"
                    );


                icon.className =
                    file.type.startsWith(
                        "image/"
                    )
                        ? "bi bi-image"
                        : "bi bi-file-earmark";


                const name =
                    document.createElement(
                        "span"
                    );


                name.textContent =
                    file.name;


                const remove =
                    document.createElement(
                        "button"
                    );


                remove.type =
                    "button";


                remove.className =
                    "selected-file-remove";


                remove.title =
                    "Remove file";


                remove.innerHTML =
                    '<i class="bi bi-x-lg"></i>';


                remove.addEventListener(
                    "click",
                    function () {

                        selectedFiles.splice(
                            index,
                            1
                        );

                        renderSelectedFiles();

                    }
                );


                item.appendChild(icon);

                item.appendChild(name);

                item.appendChild(remove);

                container.appendChild(item);

            }
        );

    }


    /* =====================================================
       MESSAGE ATTACHMENTS HTML
    ===================================================== */

    function addAttachmentsToMessage(
        row,
        attachments
    ) {

        if (
            !attachments ||
            !attachments.length
        ) {
            return;
        }


        const bubble =
            row.querySelector(
                ".message-bubble"
            );


        if (!bubble) {
            return;
        }


        let attachmentContainer =
            bubble.querySelector(
                ".message-attachments"
            );


        if (!attachmentContainer) {

            attachmentContainer =
                document.createElement(
                    "div"
                );

            attachmentContainer.className =
                "message-attachments";


            bubble.appendChild(
                attachmentContainer
            );

        }


        attachments.forEach(
            function (attachment) {

                const name =
                    attachment.name ||
                    "File";


                const url =
                    attachment.url ||
                    "#";


                const isImage =
                    /\.(jpg|jpeg|png|gif|webp|bmp|svg)$/i
                        .test(name);


                if (isImage) {

                    const link =
                        document.createElement(
                            "a"
                        );


                    link.href =
                        url;

                    link.target =
                        "_blank";

                    link.className =
                        "message-image-link";


                    const image =
                        document.createElement(
                            "img"
                        );


                    image.src =
                        url;

                    image.alt =
                        name;

                    image.className =
                        "message-image";


                    link.appendChild(
                        image
                    );


                    attachmentContainer.appendChild(
                        link
                    );


                    return;

                }


                const link =
                    document.createElement(
                        "a"
                    );


                link.href =
                    url;

                link.target =
                    "_blank";

                link.download =
                    name;

                link.className =
                    "message-file";


                link.innerHTML = `
                    <span class="message-file-icon">
                        <i class="bi bi-file-earmark"></i>
                    </span>

                    <span class="message-file-info">
                        <strong>
                            ${escapeHtml(name)}
                        </strong>

                        <small>
                            Open / Download
                        </small>
                    </span>

                    <i class="bi bi-download"></i>
                `;


                attachmentContainer.appendChild(
                    link
                );

            }
        );

    }


    /* =====================================================
       CREATE NEW MESSAGE
       
       IMPORTANT:
       Clone existing outgoing message so new messages
       use exactly the same CSS/layout.
    ===================================================== */

    function createMessageElement(data) {

        const existingMine =
            messagesBox.querySelector(
                ".chat-message-row.message-row-me"
            );


        let row;


        /* =================================================
           CLONE EXISTING OUTGOING MESSAGE
        ================================================= */

        if (existingMine) {

            row =
                existingMine.cloneNode(true);


            row.dataset.messageId =
                data.id;


            /* ---------------------------------------------
               TEXT
            --------------------------------------------- */

            const text =
                row.querySelector(
                    ".message-text"
                );


            if (text) {

                text.innerHTML =
                    escapeHtml(
                        data.content || ""
                    ).replace(
                        /\n/g,
                        "<br>"
                    );

            }


            /* ---------------------------------------------
               TIME
            --------------------------------------------- */

            const time =
                row.querySelector(
                    ".message-time"
                );


            if (time) {

                time.textContent =
                    data.created_at ||
                    "Just now";

            }


            /* ---------------------------------------------
               STATUS
            --------------------------------------------- */

            const status =
                row.querySelector(
                    ".message-status"
                );


            if (status) {

                status.className =
                    "message-status sent";

                status.textContent =
                    "✓";

                status.title =
                    "Sent";

            }


            /* ---------------------------------------------
               COPY
            --------------------------------------------- */

            const copy =
                row.querySelector(
                    ".message-copy-btn"
                );


            if (copy) {

                copy.dataset.copyText =
                    data.content || "";

            }


            /* ---------------------------------------------
               REMOVE REPLY BUTTON
            --------------------------------------------- */

            row.querySelectorAll(
                ".message-reply-btn"
            ).forEach(
                function (button) {

                    button.remove();

                }
            );


            /*
               Remove old attachments from cloned message.
            */

            row.querySelectorAll(
                ".message-attachments"
            ).forEach(
                function (element) {

                    element.remove();

                }
            );


            addAttachmentsToMessage(
                row,
                data.attachments
            );


            return row;

        }


        /* =================================================
           FALLBACK FOR FIRST MESSAGE
        ================================================= */

        row =
            document.createElement(
                "div"
            );


        row.className =
            "chat-message-row message-row-me";


        row.dataset.messageId =
            data.id;


        const content =
            document.createElement(
                "div"
            );


        content.className =
            "message-content message-content-me";


        const bubble =
            document.createElement(
                "div"
            );


        bubble.className =
            "message-bubble";


        const text =
            document.createElement(
                "span"
            );


        text.className =
            "message-text";


        text.innerHTML =
            escapeHtml(
                data.content || ""
            ).replace(
                /\n/g,
                "<br>"
            );


        bubble.appendChild(
            text
        );


        content.appendChild(
            bubble
        );


        const meta =
            document.createElement(
                "div"
            );


        meta.className =
            "message-meta";


        const time =
            document.createElement(
                "span"
            );


        time.className =
            "message-time";


        time.textContent =
            data.created_at ||
            "Just now";


        const status =
            document.createElement(
                "span"
            );


        status.className =
            "message-status sent";


        status.textContent =
            "✓";


        status.title =
            "Sent";


        meta.appendChild(
            time
        );


        meta.appendChild(
            status
        );


        content.appendChild(
            meta
        );


        const actions =
            document.createElement(
                "div"
            );


        actions.className =
            "message-actions";


        const copy =
            document.createElement(
                "button"
            );


        copy.type =
            "button";


        copy.className =
            "message-action-btn message-copy-btn";


        copy.dataset.copyText =
            data.content || "";


        copy.title =
            "Copy";


        copy.innerHTML =
            '<i class="bi bi-copy"></i>';


        actions.appendChild(
            copy
        );

        const deleteButton =
            document.createElement(
                "button"
            );

        deleteButton.type =
            "button";

        deleteButton.className =
            "message-action-btn message-delete-btn";

        deleteButton.dataset.messageId =
            data.id;

        deleteButton.title =
            "Delete";

        deleteButton.setAttribute(
            "aria-label",
            "Delete"
        );

        deleteButton.innerHTML =
            '<i class="bi bi-trash3"></i>';

        actions.appendChild(
            deleteButton
        );


        content.appendChild(
            actions
        );


        row.appendChild(
            content
        );


        addAttachmentsToMessage(
            row,
            data.attachments
        );


        return row;

    }


    function appendIncomingMessage(data) {
        if (messagesBox.querySelector(
            `[data-message-id="${data.id}"]`
        )) {
            return;
        }

        const shouldScroll = isNearBottom();
        const emptyState = document.getElementById("chatEmpty");
        if (emptyState) {
            emptyState.remove();
        }

        const row = document.createElement("div");
        row.className = "chat-message-row message-row-other";
        row.dataset.messageId = data.id;

        const avatar = data.sender_profile_picture
            ? document.createElement("img")
            : document.createElement("div");
        avatar.className = "chat-small-avatar";
        if (data.sender_profile_picture) {
            avatar.src = data.sender_profile_picture;
            avatar.alt = data.sender_display_name || data.sender_username;
            avatar.style.objectFit = "cover";
        } else {
            avatar.textContent = (
                data.sender_display_name ||
                data.sender_username ||
                "?"
            ).charAt(0).toUpperCase();
        }
        row.appendChild(avatar);

        const content = document.createElement("div");
        content.className = "message-content";
        const bubble = document.createElement("div");
        bubble.className = "message-bubble";

        if (data.deleted_for_everyone) {
            const deleted = document.createElement("span");
            deleted.className = "message-deleted";
            deleted.textContent = "This message was deleted";
            bubble.appendChild(deleted);
        } else {
            if (data.content) {
                const text = document.createElement("span");
                text.className = "message-text";
                text.innerHTML = escapeHtml(data.content).replace(/\n/g, "<br>");
                bubble.appendChild(text);
            }
        }

        content.appendChild(bubble);

        const meta = document.createElement("div");
        meta.className = "message-meta";
        const time = document.createElement("span");
        time.className = "message-time";
        time.textContent = data.created_at || "Just now";
        meta.appendChild(time);
        content.appendChild(meta);

        const actions = document.createElement("div");
        actions.className = "message-actions";

        const reply = document.createElement("button");
        reply.type = "button";
        reply.className = "message-action-btn message-reply-btn";
        reply.dataset.messageId = data.id;
        reply.dataset.messageText = data.content || "";
        reply.title = "Reply";
        reply.setAttribute("aria-label", "Reply");
        reply.innerHTML = '<i class="bi bi-reply"></i>';
        actions.appendChild(reply);

        const copy = document.createElement("button");
        copy.type = "button";
        copy.className = "message-action-btn message-copy-btn";
        copy.dataset.copyText = data.content || "";
        copy.title = "Copy";
        copy.setAttribute("aria-label", "Copy");
        copy.innerHTML = '<i class="bi bi-copy"></i>';
        actions.appendChild(copy);

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "message-action-btn message-delete-btn";
        remove.dataset.messageId = data.id;
        remove.dataset.messageSender = data.sender_id;
        remove.title = "Delete";
        remove.setAttribute("aria-label", "Delete");
        remove.innerHTML = '<i class="bi bi-trash3"></i>';
        actions.appendChild(remove);

        content.appendChild(actions);
        row.appendChild(content);
        if (!data.deleted_for_everyone) {
            addAttachmentsToMessage(row, data.attachments);
        }
        messagesBox.appendChild(row);

        if (shouldScroll) {
            scrollToBottom();
        }
    }


    /* =====================================================
       SEND MESSAGE
       
       Supports:
       - Text
       - Emoji
       - Reply
       - Image
       - Video
       - Audio
       - PDF
       - DOC
       - ZIP
       - Multiple files
    ===================================================== */

    async function sendMessage() {

        if (isSending) {
            return;
        }


        const text =
            textarea.value.trim();


        if (
            !text &&
            !selectedFiles.length
        ) {

            textarea.focus();

            return;

        }


        isSending =
            true;


        sendButton.disabled =
            true;


        const formData =
            new FormData();


        formData.append(
            "csrfmiddlewaretoken",
            csrfToken
        );


        /* ---------------------------------------------
           TEXT
        --------------------------------------------- */

        let finalContent =
            text;


        if (replyText && text) {

            finalContent =
                "Replying to: " +
                replyText +
                "\n\n" +
                text;

        }


        formData.append(
            "content",
            finalContent
        );


        /* ---------------------------------------------
           FILES
        --------------------------------------------- */

        selectedFiles.forEach(
            function (file) {

                formData.append(
                    "attachments",
                    file
                );

            }
        );


        try {

            const response =
                await fetch(
                    sendUrl,
                    {
                        method: "POST",

                        headers: {
                            "X-Requested-With":
                                "XMLHttpRequest"
                        },

                        body: formData
                    }
                );


            const data =
                await response.json();


            if (
                !response.ok ||
                !data.success
            ) {

                throw new Error(
                    data.error ||
                    "Unable to send message."
                );

            }


            /* ---------------------------------------------
               REMOVE EMPTY STATE
            --------------------------------------------- */

            const empty =
                document.getElementById(
                    "chatEmpty"
                );


            if (empty) {

                empty.remove();

            }


            /* ---------------------------------------------
               ADD NEW MESSAGE
            --------------------------------------------- */

            const element =
                createMessageElement(
                    data.message
                );


            messagesBox.appendChild(
                element
            );


            /* ---------------------------------------------
               CLEAR INPUT
            --------------------------------------------- */

            textarea.value =
                "";

            stopLocalTyping();

            resizeTextarea();


            selectedFiles =
                [];


            renderSelectedFiles();


            clearReply();


            closeEmojiPickerNow();


            /* ---------------------------------------------
               SCROLL
            --------------------------------------------- */

            scrollToBottom();


            textarea.focus();


        } catch (error) {

            alert(
                error.message ||
                "Unable to send message."
            );

        } finally {

            isSending =
                false;


            sendButton.disabled =
                false;

        }

    }


    /* =====================================================
       FORM SUBMIT
    ===================================================== */

    form.addEventListener(
        "submit",
        function (event) {

            event.preventDefault();

            sendMessage();

        }
    );


   /* =====================================================
   ENTER = SEND
   SHIFT + ENTER = NEW LINE
===================================================== */

textarea.addEventListener(
    "keydown",
    function (event) {

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {

            event.preventDefault();
            event.stopPropagation();

            sendMessage();

            return false;
        }

        // Shift + Enter = new line
    }
);


    /* =====================================================
       SAY HELLO
    ===================================================== */

    if (sayHelloButton) {

        sayHelloButton.addEventListener(
            "click",
            function () {

                if (isSending) {
                    return;
                }


                textarea.value =
                    "Hello 👋";


                resizeTextarea();


                sendMessage();

            }
        );

    }


    /* =====================================================
       COPY MESSAGE
    ===================================================== */

    document.addEventListener(
        "click",
        async function (event) {

            const button =
                event.target.closest(
                    ".message-copy-btn"
                );


            if (!button) {
                return;
            }


            const text =
                button.dataset.copyText ||
                "";


            if (!text) {
                return;
            }


            try {

                await navigator.clipboard.writeText(
                    text
                );


                const oldHtml =
                    button.innerHTML;


                button.innerHTML =
                    '<i class="bi bi-check2"></i>';


                setTimeout(
                    function () {

                        button.innerHTML =
                            oldHtml;

                    },
                    1000
                );


            } catch (error) {

                alert(
                    "Could not copy message."
                );

            }

        }
    );

    /* =====================================================
   DELETE MESSAGE
===================================================== */

let deleteMessageId = null;


/* -----------------------------------------------------
   OPEN DELETE MODAL
----------------------------------------------------- */

document.addEventListener(
    "click",
    function (event) {

        const button =
            event.target.closest(
                ".message-delete-btn"
            );

        if (!button) {
            return;
        }

        deleteMessageId =
            button.dataset.messageId;

        const modal =
            document.getElementById(
                "deleteMessageModal"
            );

        if (!modal) {
            return;
        }

        modal.hidden = false;

        modal.setAttribute(
            "aria-hidden",
            "false"
        );

    }
);


/* -----------------------------------------------------
   CLOSE DELETE MODAL
----------------------------------------------------- */

function closeDeleteModal() {

    const modal =
        document.getElementById(
            "deleteMessageModal"
        );

    if (!modal) {
        return;
    }

    modal.hidden = true;

    modal.setAttribute(
        "aria-hidden",
        "true"
    );

    deleteMessageId = null;
}


/* -----------------------------------------------------
   CANCEL
----------------------------------------------------- */

const cancelDeleteBtn =
    document.getElementById(
        "cancelDeleteBtn"
    );

if (cancelDeleteBtn) {

    cancelDeleteBtn.addEventListener(
        "click",
        function () {

            closeDeleteModal();

        }
    );

}


/* -----------------------------------------------------
   DELETE FOR ME
----------------------------------------------------- */

const deleteForMeBtn =
    document.getElementById(
        "deleteForMeBtn"
    );

if (deleteForMeBtn) {

    deleteForMeBtn.addEventListener(
        "click",
        function () {

            if (!deleteMessageId) {
                return;
            }

            deleteMessage(
                deleteMessageId,
                "me"
            );

        }
    );

}


/* -----------------------------------------------------
   DELETE FOR EVERYONE
----------------------------------------------------- */

const deleteForEveryoneBtn =
    document.getElementById(
        "deleteForEveryoneBtn"
    );

if (deleteForEveryoneBtn) {

    deleteForEveryoneBtn.addEventListener(
        "click",
        function () {

            if (!deleteMessageId) {
                return;
            }

            deleteMessage(
                deleteMessageId,
                "everyone"
            );

        }
    );

}


/* -----------------------------------------------------
   DELETE REQUEST
----------------------------------------------------- */

async function deleteMessage(
    messageId,
    deleteType
) {

    const formData =
        new FormData();

    formData.append(
        "csrfmiddlewaretoken",
        csrfToken
    );

    formData.append(
        "delete_type",
        deleteType
    );


    try {

        const response =
            await fetch(
                `/messages/delete/${messageId}/`,
                {
                    method: "POST",

                    headers: {
                        "X-Requested-With":
                            "XMLHttpRequest"
                    },

                    body: formData
                }
            );


        const data =
            await response.json();


        if (
            !response.ok ||
            !data.success
        ) {

            throw new Error(
                data.error ||
                "Unable to delete message."
            );

        }


        const row =
            messagesBox.querySelector(
                `[data-message-id="${messageId}"]`
            );


        if (row) {

            if (deleteType === "me") {

                row.remove();

            }

            else if (
                deleteType === "everyone"
            ) {

                markMessageAsDeleted(
                    row
                );

            }

        }


        closeDeleteModal();


    } catch (error) {

        alert(
            error.message ||
            "Unable to delete message."
        );

    }

}


/* -----------------------------------------------------
   SHOW "THIS MESSAGE WAS DELETED"
----------------------------------------------------- */

function markMessageAsDeleted(row) {

    const bubble =
        row.querySelector(
            ".message-bubble"
        );

    if (!bubble) {
        return;
    }


    bubble.innerHTML = `
        <span class="message-deleted">
            <i class="bi bi-ban"></i>
            This message was deleted
        </span>
    `;


    row.querySelectorAll(
        ".message-attachments"
    ).forEach(
        function (element) {

            element.remove();

        }
    );


    row.querySelectorAll(
        ".message-actions"
    ).forEach(
        function (element) {

            element.remove();

        }
    );

}

    /* =====================================================
       MESSAGE STATUS
    ===================================================== */

    function updateMessageStatus(
        messageId,
        delivered,
        read
    ) {

        const row =
            messagesBox.querySelector(
                '[data-message-id="' +
                messageId +
                '"]'
            );


        if (!row) {
            return;
        }


        const status =
            row.querySelector(
                ".message-status"
            );


        if (!status) {
            return;
        }


        if (read) {

            status.textContent =
                "✓✓";

            status.className =
                "message-status seen";

            status.title =
                "Seen";

        } else if (delivered) {

            status.textContent =
                "✓✓";

            status.className =
                "message-status delivered";

            status.title =
                "Delivered";

        } else {

            status.textContent =
                "✓";

            status.className =
                "message-status sent";

            status.title =
                "Sent";

        }

    }


    /* =====================================================
       STATUS POLLING
    ===================================================== */

    async function pollStatus() {

        if (!statusUrl) {
            return;
        }


        try {

            const response =
                await fetch(
                    statusUrl,
                    {
                        method: "GET",

                        headers: {
                            "X-Requested-With":
                                "XMLHttpRequest"
                        },

                        cache: "no-store"
                    }
                );


            if (!response.ok) {
                return;
            }


            const data =
                await response.json();


            if (!data.success) {
                return;
            }


            (data.messages || []).forEach(
                function (message) {
                    if (
                        Number(message.sender_id) !==
                            Number(page.dataset.currentUserId) &&
                        !messagesBox.querySelector(
                            `[data-message-id="${message.id}"]`
                        )
                    ) {
                        appendIncomingMessage(message);
                    }

                    updateMessageStatus(
                        message.id,
                        message.is_delivered,
                        message.is_read
                    );

                }
            );


        } catch (error) {

            /*
               Silent.
               Chat should never show an error
               every 2 seconds because polling failed.
            */

        }

    }


    statusTimer =
        window.setInterval(
            pollStatus,
            2000
        );


    pollStatus();


    function connectWebSocket() {
        if (!window.WebSocket || !shouldReconnect) {
            return;
        }

        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const url = `${protocol}//${window.location.host}/ws/messages/${page.dataset.conversationId}/`;
        websocket = new WebSocket(url);

        websocket.addEventListener("open", function () {
            reconnectDelay = 1000;
            if (isLocallyTyping) {
                sendTypingStatus(true);
            }
            if (statusTimer) {
                clearInterval(statusTimer);
                statusTimer = null;
            }
            pollStatus();
        });
        websocket.addEventListener("message", function (event) {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "message_created") {
                    pollStatus();
                } else if (
                    data.type === "typing_status" &&
                    Number(data.user_id) !==
                        Number(page.dataset.currentUserId)
                ) {
                    showRemoteTyping(Boolean(data.is_typing));
                }
            } catch (error) {
                console.error("Invalid chat update received.", error);
            }
        });
        websocket.addEventListener("close", function (event) {
            if (!shouldReconnect || event.code === 4401 || event.code === 4403) {
                return;
            }
            if (!statusTimer) {
                statusTimer = window.setInterval(pollStatus, 2000);
            }
            reconnectTimer = window.setTimeout(function () {
                reconnectDelay = Math.min(reconnectDelay * 2, 30000);
                connectWebSocket();
            }, reconnectDelay);
        });
    }

    connectWebSocket();


    /* =====================================================
       AUTO SCROLL FOR NEW MESSAGES
    ===================================================== */

    const observer =
        new MutationObserver(
            function (mutations) {

                let added =
                    false;


                mutations.forEach(
                    function (mutation) {

                        if (
                            mutation.addedNodes &&
                            mutation.addedNodes.length
                        ) {

                            added =
                                true;

                        }

                    }
                );


                if (
                    added &&
                    isNearBottom()
                ) {

                    scrollToBottom();

                }

            }
        );


    observer.observe(
        messagesBox,
        {
            childList: true
        }
    );


    /* =====================================================
       CLEANUP
    ===================================================== */

    window.addEventListener(
        "beforeunload",
        function () {

            stopLocalTyping();

            if (statusTimer) {

                clearInterval(
                    statusTimer
                );

            }
            shouldReconnect = false;
            if (reconnectTimer) {
                clearTimeout(reconnectTimer);
            }
            if (websocket) {
                websocket.close(1000);
            }
            if (typingIdleTimer) {
                clearTimeout(typingIdleTimer);
            }
            if (typingHeartbeatTimer) {
                clearInterval(typingHeartbeatTimer);
            }
            if (remoteTypingTimer) {
                clearTimeout(remoteTypingTimer);
            }

        }
    );

});