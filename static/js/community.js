document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".community-share-button").forEach((button) => {
        button.addEventListener("click", async () => {
            const card = button.closest(".community-post");
            const status = card?.querySelector(".community-share-status");
            const shareUrl = button.dataset.shareUrl;

            if (!status || !shareUrl || button.disabled) {
                return;
            }

            button.disabled = true;
            status.textContent = "";
            try {
                if (navigator.share) {
                    await navigator.share({
                        title: button.dataset.shareTitle || document.title,
                        url: shareUrl,
                    });
                    status.textContent = "Shared";
                } else if (navigator.clipboard?.writeText) {
                    await navigator.clipboard.writeText(shareUrl);
                    status.textContent = "Link copied";
                } else {
                    window.prompt("Copy this community post link", shareUrl);
                }
            } catch (error) {
                if (error.name !== "AbortError") {
                    console.error("Community post share failed:", error);
                    status.textContent = "Unable to share this post.";
                }
            } finally {
                button.disabled = false;
            }
        });
    });
});
