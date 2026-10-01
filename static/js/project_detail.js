document.addEventListener("DOMContentLoaded", function () {

    const csrfToken = document.querySelector(
        "[name=csrfmiddlewaretoken]"
    )?.value;


    /*
    =========================================================
    LIKE / SAVE / FOLLOW
    =========================================================
    */

    const actionForms = document.querySelectorAll(
        ".project-actions form"
    );


    actionForms.forEach(function (form) {

        form.addEventListener("submit", async function (event) {

            event.preventDefault();

            const button = form.querySelector("button");

            if (!button || button.disabled) {
                return;
            }

            button.disabled = true;

            try {

                const response = await fetch(
                    form.action,
                    {
                        method: "POST",
                        headers: {
                            "X-CSRFToken": csrfToken,
                            "X-Requested-With": "XMLHttpRequest"
                        },
                        body: new FormData(form)
                    }
                );


                const data = await response.json();


                if (!data.success) {

                    alert(
                        data.error ||
                        "Something went wrong."
                    );

                    return;
                }


                /*
                =========================
                LIKE
                =========================
                */

                if ("liked" in data) {

                    button.innerHTML = `
                        <i class="bi ${data.liked
                            ? "bi-heart-fill"
                            : "bi-heart"
                        }"></i>
                        ${data.count}
                    `;

                    button.classList.toggle(
                        "active",
                        data.liked
                    );
                }


                /*
                =========================
                SAVE
                =========================
                */

                if ("saved" in data) {

                    button.innerHTML = `
                        <i class="bi ${data.saved
                            ? "bi-bookmark-fill"
                            : "bi-bookmark"
                        }"></i>
                        ${data.count}
                    `;

                    button.classList.toggle(
                        "active",
                        data.saved
                    );
                }


                /*
                =========================
                FOLLOW
                =========================
                */

                if ("following" in data) {

                    button.innerHTML = `
                        <i class="bi ${data.following
                            ? "bi-bell-fill"
                            : "bi-bell"
                        }"></i>
                        ${data.following
                            ? "Following"
                            : "Follow"
                        }
                    `;

                    button.classList.toggle(
                        "active",
                        data.following
                    );
                }


            } catch (error) {

                console.error(
                    "Project action error:",
                    error
                );

                alert(
                    "Unable to complete the action."
                );

            } finally {

                button.disabled = false;

            }

        });

    });


    /*
    =========================================================
    SHARE PROJECT
    =========================================================
    */

    const shareForm = document.querySelector(".project-share-form");

    if (shareForm) {
        shareForm.addEventListener("submit", async function (event) {
            event.preventDefault();

            const button = shareForm.querySelector("button[type='submit']");
            const status = shareForm.querySelector(".share-project-status");
            const shareUrl = shareForm.dataset.shareUrl;
            if (!button || !shareUrl || button.disabled) {
                return;
            }

            button.disabled = true;
            status.textContent = "";

            try {
                let platform = "copy";
                if (navigator.share) {
                    await navigator.share({ title: document.title, url: shareUrl });
                    platform = "native";
                } else if (navigator.clipboard?.writeText) {
                    await navigator.clipboard.writeText(shareUrl);
                } else {
                    window.prompt("Copy this project link", shareUrl);
                }

                const payload = new FormData(shareForm);
                payload.set("platform", platform);
                const response = await fetch(shareForm.action, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    body: payload,
                });
                const data = await response.json();
                if (!response.ok || !data.success) {
                    throw new Error(data.error || "Unable to record the share.");
                }

                status.textContent = platform === "copy" ? "Link copied" : "Shared";
            } catch (error) {
                if (error.name !== "AbortError") {
                    status.textContent = "Sharing failed. Try again.";
                }
            } finally {
                button.disabled = false;
            }
        });
    }


    /*
    =========================================================
    COMMENT
    =========================================================
    */

    const commentForm = document.querySelector(
        ".comment-form"
    );


    if (commentForm) {

        commentForm.addEventListener(
            "submit",
            async function (event) {

                event.preventDefault();


                const textarea =
                    commentForm.querySelector("textarea");

                const button =
                    commentForm.querySelector("button");


                const content =
                    textarea.value.trim();


                if (!content) {
                    return;
                }


                button.disabled = true;


                try {

                    const response = await fetch(
                        commentForm.action,
                        {
                            method: "POST",
                            headers: {
                                "X-CSRFToken": csrfToken,
                                "X-Requested-With": "XMLHttpRequest"
                            },
                            body: new FormData(commentForm)
                        }
                    );


                    const data =
                        await response.json();


                    if (!data.success) {

                        alert(
                            data.error ||
                            "Unable to add comment."
                        );

                        return;
                    }


                    /*
                    Create comment
                    */

                    const commentHTML = `
                        <div class="project-comment">

                            <div class="comment-avatar">
                                ${escapeHTML(
                        data.comment.initial
                    )}
                            </div>

                            <div class="comment-content">

                                <strong>
                                    ${escapeHTML(
                        data.comment.username
                    )}
                                </strong>

                                <span class="comment-date">
                                    ${escapeHTML(
                        data.comment.date
                    )}
                                </span>

                                <p>
                                    ${escapeHTML(
                        data.comment.content
                    )}
                                </p>

                            </div>

                        </div>
                    `;


                    /*
                    Insert comment
                    */

                    commentForm.insertAdjacentHTML(
                        "afterend",
                        commentHTML
                    );


                    /*
                    Clear textarea
                    */

                    textarea.value = "";


                    /*
                    Update comment count
                    */

                    const commentHeading =
                        document.querySelector(
                            ".detail-heading h2"
                        );


                    if (commentHeading) {

                        const countSpan =
                            commentHeading.querySelector(
                                "span"
                            );

                        if (countSpan) {

                            countSpan.textContent =
                                data.count;

                        }

                    }


                    /*
                    Remove "No comments"
                    */

                    const noComments =
                        document.querySelector(
                            ".no-comments"
                        );


                    if (noComments) {
                        noComments.remove();
                    }


                } catch (error) {

                    console.error(
                        "Comment error:",
                        error
                    );

                    alert(
                        "Unable to add comment."
                    );

                } finally {

                    button.disabled = false;

                }

            }
        );

    }


    /*
    =========================================================
    COLLABORATION
    =========================================================
    */

    const collaborateForm =
        document.querySelector(
            ".collaboration-form"
        );

    const collaborateBtn =
        document.getElementById(
            "collaborateBtn"
        );


    const connectModal =
        document.getElementById(
            "connectModal"
        );

    const closeConnectModal =
        document.getElementById(
            "closeConnectModal"
        );

    const connectNotNow =
        document.getElementById(
            "connectNotNow"
        );

    const connectConfirm =
        document.getElementById(
            "connectConfirm"
        );


    /*
    =========================================================
    COLLABORATE → AJAX
    =========================================================
    */

    if (collaborateForm && collaborateBtn) {

        collaborateForm.addEventListener(
            "submit",
            async function (event) {

                event.preventDefault();


                if (collaborateBtn.disabled) {
                    return;
                }


                collaborateBtn.disabled = true;


                try {

                    const response = await fetch(
                        collaborateForm.action,
                        {
                            method: "POST",
                            headers: {
                                "X-CSRFToken": csrfToken,
                                "X-Requested-With": "XMLHttpRequest"
                            },
                            body: new FormData(
                                collaborateForm
                            )
                        }
                    );


                    const data =
                        await response.json();


                    if (!data.success) {

                        alert(
                            data.error ||
                            "Unable to record your interest."
                        );

                        return;
                    }


                    /*
                    =========================
                    CHANGE BUTTON STATE
                    =========================
                    */

                    collaborateBtn.classList.add(
                        "interested"
                    );


                    collaborateBtn.innerHTML = `
                        <i class="bi bi-check2-circle"></i>
                        <span>Interested</span>
                    `;


                    /*
                    =========================
                    OPEN CONNECT MODAL
                    =========================
                    */

                    if (
                        data.show_connect &&
                        connectModal
                    ) {

                        connectModal.classList.add(
                            "show"
                        );

                        connectModal.setAttribute(
                            "aria-hidden",
                            "false"
                        );

                    }


                } catch (error) {

                    console.error(
                        "Collaboration error:",
                        error
                    );

                    alert(
                        "Unable to complete the request."
                    );

                } finally {

                    collaborateBtn.disabled = false;

                }

            }
        );

    }


    /*
    =========================================================
    CLOSE CONNECT MODAL
    =========================================================
    */

    function closeConnectModalFunction() {

        if (!connectModal) {
            return;
        }


        connectModal.classList.remove(
            "show"
        );


        connectModal.setAttribute(
            "aria-hidden",
            "true"
        );

    }


    /*
    Close button
    */

    if (closeConnectModal) {

        closeConnectModal.addEventListener(
            "click",
            closeConnectModalFunction
        );

    }


    /*
    Not Now
    */

    if (connectNotNow) {

        connectNotNow.addEventListener(
            "click",
            closeConnectModalFunction
        );

    }


    /*
    Click outside modal
    */

    if (connectModal) {

        const overlay =
            connectModal.querySelector(
                ".connect-modal-overlay"
            );


        if (overlay) {

            overlay.addEventListener(
                "click",
                closeConnectModalFunction
            );

        }

    }


    /*
    =========================================================
    CONNECT BUTTON
    =========================================================
    */

    if (connectConfirm) {

        connectConfirm.addEventListener(
            "click",
            async function () {

                const connectUrl =
                    connectConfirm.dataset.connectUrl;

                if (!connectUrl) {
                    alert("Connection URL not found.");
                    return;
                }

                connectConfirm.disabled = true;

                connectConfirm.innerHTML = `
                <i class="bi bi-hourglass-split"></i>
                Connecting...
            `;

                try {

                    const response = await fetch(
                        connectUrl,
                        {
                            method: "POST",
                            headers: {
                                "X-CSRFToken": csrfToken,
                                "X-Requested-With": "XMLHttpRequest"
                            }
                        }
                    );

                    const data =
                        await response.json();

                    if (!data.success) {
                        alert(
                            data.error ||
                            "Unable to start conversation."
                        );
                        return;
                    }

                    window.location.href =
                        data.redirect_url;

                } catch (error) {

                    console.error(
                        "Connect error:",
                        error
                    );

                    alert(
                        "Unable to connect right now."
                    );

                } finally {

                    connectConfirm.disabled = false;

                    connectConfirm.innerHTML = `
                    <i class="bi bi-chat-dots"></i>
                    Connect
                `;
                }
            }
        );

    }
    /*
    =========================================================
    ESC KEY → CLOSE MODAL
    =========================================================
    */

    document.addEventListener(
        "keydown",
        function (event) {

            if (
                event.key === "Escape" &&
                connectModal &&
                connectModal.classList.contains("show")
            ) {

                closeConnectModalFunction();

            }

        }
    );


    /*
    =========================================================
    HTML ESCAPE
    =========================================================
    */

    function escapeHTML(value) {

        const div =
            document.createElement("div");

        div.textContent =
            value ?? "";

        return div.innerHTML;

    }

});