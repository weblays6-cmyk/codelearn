document.addEventListener("DOMContentLoaded", function () {

    /* =====================================================
       ELEMENTS
    ===================================================== */

    const newMessageBtn =
        document.getElementById("newMessageBtn");

    const messageModal =
        document.getElementById("messageModal");

    const closeMessageModal =
        document.getElementById("closeMessageModal");

    const userSearch =
        document.getElementById("userSearch");

    const userSearchItems =
        document.querySelectorAll(
            ".user-search-item"
        );

    const userSearchNoResults =
        document.getElementById(
            "userSearchNoResults"
        );

    const conversationSearch =
        document.getElementById(
            "conversationSearch"
        );

    const conversationItems =
        document.querySelectorAll(
            ".conversation-item"
        );

    const messagesNoResults =
        document.getElementById(
            "messagesNoResults"
        );


    /* =====================================================
       CSRF
    ===================================================== */

    function getCookie(name) {

        const cookies = document.cookie
            ? document.cookie.split(";")
            : [];

        for (let cookie of cookies) {

            cookie = cookie.trim();

            if (cookie.startsWith(name + "=")) {

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


    /* =====================================================
       OPEN MODAL
    ===================================================== */

    function openMessageModal() {

        if (!messageModal) {
            return;
        }

        messageModal.classList.add(
            "active"
        );

        messageModal.setAttribute(
            "aria-hidden",
            "false"
        );

        if (userSearch) {

            userSearch.value = "";

            filterUsers();

            window.setTimeout(
                function () {
                    userSearch.focus();
                },
                100
            );
        }
    }


    /* =====================================================
       CLOSE MODAL
    ===================================================== */

    function closeModal() {

        if (!messageModal) {
            return;
        }

        messageModal.classList.remove(
            "active"
        );

        messageModal.setAttribute(
            "aria-hidden",
            "true"
        );
    }


    if (newMessageBtn) {

        newMessageBtn.addEventListener(
            "click",
            openMessageModal
        );
    }


    if (closeMessageModal) {

        closeMessageModal.addEventListener(
            "click",
            closeModal
        );
    }


    if (messageModal) {

        messageModal.addEventListener(
            "click",
            function (event) {

                if (
                    event.target ===
                    messageModal
                ) {

                    closeModal();
                }
            }
        );
    }


    document.addEventListener(
        "keydown",
        function (event) {

            if (event.key === "Escape") {
                closeModal();
            }
        }
    );


    /* =====================================================
       USER SEARCH
    ===================================================== */

    function filterUsers() {

        if (!userSearch) {
            return;
        }

        const search =
            userSearch.value
                .trim()
                .toLowerCase();

        let visibleCount = 0;

        userSearchItems.forEach(
            function (item) {

                const username =
                    (
                        item.dataset.username ||
                        item.innerText ||
                        ""
                    ).toLowerCase();

                const match =
                    search === "" ||
                    username.includes(search);

                item.style.display =
                    match ? "flex" : "none";

                if (match) {
                    visibleCount++;
                }
            }
        );

        if (userSearchNoResults) {

            userSearchNoResults.style.display =
                (
                    userSearchItems.length > 0 &&
                    visibleCount === 0
                )
                    ? "flex"
                    : "none";
        }
    }


    if (userSearch) {

        userSearch.addEventListener(
            "input",
            filterUsers
        );
    }


    /* =====================================================
       START PERSONAL CHAT
    ===================================================== */

    userSearchItems.forEach(
        function (item) {

            item.addEventListener(
                "click",
                async function () {

                    const connectUrl =
                        item.dataset.connectUrl;

                    if (!connectUrl) {
                        return;
                    }

                    item.disabled = true;

                    try {

                        const response =
                            await fetch(
                                connectUrl,
                                {
                                    method: "POST",
                                    headers: {
                                        "X-CSRFToken":
                                            csrfToken,
                                        "X-Requested-With":
                                            "XMLHttpRequest"
                                    }
                                }
                            );

                        const data =
                            await response.json();

                        if (!response.ok ||
                            !data.success) {

                            throw new Error(
                                data.error ||
                                "Unable to start conversation."
                            );
                        }

                        if (data.redirect_url) {

                            window.location.href =
                                data.redirect_url;

                        }

                    } catch (error) {

                        alert(
                            error.message ||
                            "Unable to start conversation."
                        );

                        item.disabled = false;
                    }
                }
            );
        }
    );


    /* =====================================================
       CONVERSATION SEARCH
    ===================================================== */

    function filterConversations() {

        if (!conversationSearch) {
            return;
        }

        const searchText =
            conversationSearch.value
                .trim()
                .toLowerCase();

        let visibleCount = 0;

        conversationItems.forEach(
            function (item) {

                const searchableText =
                    (
                        item.dataset.conversationSearch ||
                        item.innerText ||
                        ""
                    ).toLowerCase();

                const match =
                    searchText === "" ||
                    searchableText.includes(
                        searchText
                    );

                item.style.display =
                    match ? "flex" : "none";

                if (match) {
                    visibleCount++;
                }
            }
        );

        if (messagesNoResults) {

            messagesNoResults.style.display =
                (
                    conversationItems.length > 0 &&
                    visibleCount === 0
                )
                    ? "flex"
                    : "none";
        }
    }


    if (conversationSearch) {

        conversationSearch.addEventListener(
            "input",
            filterConversations
        );
    }


    filterConversations();

});
