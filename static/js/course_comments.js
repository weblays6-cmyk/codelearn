document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("courseCommentForm");
    const list = document.getElementById("courseCommentList");
    const count = document.getElementById("courseCommentCount");
    const status = document.getElementById("courseCommentStatus");

    if (!form || !list || !count || !status) {
        return;
    }

    const button = form.querySelector('button[type="submit"]');
    const textarea = form.querySelector('textarea[name="content"]');
    const initialButtonMarkup = button ? button.innerHTML : "Add Comment";
    let submitting = false;

    function addAction(container, label, href, className) {
        const link = document.createElement("a");
        link.textContent = label;
        link.href = href;
        link.className = className;
        container.appendChild(link);
    }

    function renderComment(comment) {
        const card = document.createElement("div");
        card.className = "comment-card";
        card.dataset.commentId = String(comment.id);

        const header = document.createElement("div");
        header.className = "comment-header";
        const author = document.createElement("div");
        author.className = "comment-author";

        if (comment.avatar_url) {
            const avatar = document.createElement("img");
            avatar.className = "comment-avatar";
            avatar.src = comment.avatar_url;
            avatar.alt = `@${comment.username} profile photo`;
            author.appendChild(avatar);
        } else {
            const avatar = document.createElement("div");
            avatar.className = "comment-avatar";
            avatar.textContent = comment.initial;
            author.appendChild(avatar);
        }

        const name = document.createElement("strong");
        const profileLink = document.createElement("a");
        profileLink.href = comment.profile_url;
        profileLink.textContent = `@${comment.username.toLowerCase()}`;
        name.appendChild(profileLink);
        author.appendChild(name);

        const time = document.createElement("time");
        time.className = "comment-date";
        time.textContent = comment.created_at;
        header.append(author, time);
        card.appendChild(header);

        const content = document.createElement("div");
        content.className = "comment-text";
        content.textContent = comment.content;
        card.appendChild(content);

        const actions = document.createElement("div");
        actions.className = "comment-actions";
        addAction(actions, "Edit", comment.edit_url, "edit-btn");
        addAction(actions, "Delete", comment.delete_url, "delete-btn");
        card.appendChild(actions);
        return card;
    }

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        if (submitting || !textarea || !textarea.value.trim()) {
            if (textarea && !textarea.value.trim()) {
                status.textContent = "Write a comment before submitting.";
                textarea.focus();
            }
            return;
        }

        submitting = true;
        if (button) {
            button.disabled = true;
            button.textContent = "Adding...";
        }
        status.textContent = "";

        try {
            const response = await fetch(window.location.href, {
                method: "POST",
                body: new FormData(form),
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                },
                credentials: "same-origin",
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || "Your comment could not be added.");
            }

            const emptyState = document.getElementById("courseCommentEmpty");
            if (emptyState) {
                emptyState.remove();
            }
            list.prepend(renderComment(result.comment));
            textarea.value = "";
            count.textContent = `${result.count} ${result.count === 1 ? "comment" : "comments"}`;
            status.textContent = "Comment added.";
        } catch (error) {
            status.textContent = error.message || "Your comment could not be added.";
        } finally {
            submitting = false;
            if (button) {
                button.disabled = false;
                button.innerHTML = initialButtonMarkup;
            }
        }
    });
});
