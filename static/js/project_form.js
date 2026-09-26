document.addEventListener("DOMContentLoaded", function () {

    const imageInput = document.getElementById("project-images");
    const previewContainer = document.getElementById("project-image-preview");

    if (!imageInput || !previewContainer) {
        return;
    }

    imageInput.addEventListener("change", function () {

        previewContainer.innerHTML = "";

        const files = Array.from(this.files);

        files.forEach(function (file) {

            if (!file.type.startsWith("image/")) {
                return;
            }

            const reader = new FileReader();

            reader.onload = function (event) {

                const previewItem = document.createElement("div");
                previewItem.className = "project-preview-item";

                const image = document.createElement("img");
                image.src = event.target.result;
                image.alt = file.name;

                previewItem.appendChild(image);
                previewContainer.appendChild(previewItem);
            };

            reader.readAsDataURL(file);
        });

    });

});