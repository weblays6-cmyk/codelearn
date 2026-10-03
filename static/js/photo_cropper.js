document.addEventListener("DOMContentLoaded", function () {
    const dialog = document.getElementById("photoCropDialog");
    const canvas = document.getElementById("photoCropCanvas");
    const zoom = document.getElementById("photoCropZoom");
    const cancel = document.getElementById("photoCropCancel");
    const usePhoto = document.getElementById("photoCropUse");
    const fileInput = document.querySelector(".profile-photo-input");

    if (!dialog || !canvas || !zoom || !cancel || !usePhoto || !fileInput) {
        return;
    }

    const context = canvas.getContext("2d");
    const preview = document.querySelector(fileInput.dataset.preview);
    const placeholder = document.querySelector(fileInput.dataset.placeholder);
    const error = document.querySelector(fileInput.dataset.error);
    const allowedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
    const maxSize = 5 * 1024 * 1024;
    const image = new Image();
    let objectUrl = null;
    let scale = 1;
    let offsetX = 0;
    let offsetY = 0;
    let dragging = false;
    let dragX = 0;
    let dragY = 0;
    let imageType = "image/png";

    function clampOffsets() {
        const renderedWidth = image.naturalWidth * scale;
        const renderedHeight = image.naturalHeight * scale;
        offsetX = Math.min(0, Math.max(canvas.width - renderedWidth, offsetX));
        offsetY = Math.min(0, Math.max(canvas.height - renderedHeight, offsetY));
    }

    function drawImage() {
        if (!image.complete || !image.naturalWidth) {
            return;
        }
        clampOffsets();
        context.clearRect(0, 0, canvas.width, canvas.height);
        context.drawImage(
            image,
            offsetX,
            offsetY,
            image.naturalWidth * scale,
            image.naturalHeight * scale
        );
    }

    function closeCropper(clearSelection) {
        dialog.hidden = true;
        dragging = false;
        if (clearSelection) {
            fileInput.value = "";
        }
        if (objectUrl) {
            URL.revokeObjectURL(objectUrl);
            objectUrl = null;
        }
    }

    function showError(message) {
        if (error) {
            error.textContent = message;
        }
    }

    fileInput.addEventListener("change", function () {
        const file = fileInput.files && fileInput.files[0];
        showError("");
        if (!file) {
            return;
        }
        if (!allowedTypes.has(file.type) || file.size > maxSize) {
            fileInput.value = "";
            showError(file.size > maxSize
                ? "Profile photos must be 5 MB or smaller."
                : "Choose a JPG, PNG or WEBP image.");
            return;
        }

        if (objectUrl) {
            URL.revokeObjectURL(objectUrl);
        }
        objectUrl = URL.createObjectURL(file);
        imageType = file.type;
        image.onload = function () {
            const baseScale = Math.max(
                canvas.width / image.naturalWidth,
                canvas.height / image.naturalHeight
            );
            scale = baseScale;
            offsetX = (canvas.width - image.naturalWidth * scale) / 2;
            offsetY = (canvas.height - image.naturalHeight * scale) / 2;
            zoom.value = "1";
            drawImage();
            dialog.hidden = false;
            cancel.focus();
        };
        image.onerror = function () {
            closeCropper(true);
            showError("This image could not be opened. Choose another photo.");
        };
        image.src = objectUrl;
    });

    zoom.addEventListener("input", function () {
        if (!image.naturalWidth) {
            return;
        }
        const nextScale = Math.max(
            canvas.width / image.naturalWidth,
            canvas.height / image.naturalHeight
        ) * Number(zoom.value);
        const centerX = canvas.width / 2;
        const centerY = canvas.height / 2;
        const sourceX = (centerX - offsetX) / scale;
        const sourceY = (centerY - offsetY) / scale;
        scale = nextScale;
        offsetX = centerX - sourceX * scale;
        offsetY = centerY - sourceY * scale;
        drawImage();
    });

    canvas.addEventListener("pointerdown", function (event) {
        dragging = true;
        dragX = event.clientX;
        dragY = event.clientY;
        canvas.setPointerCapture(event.pointerId);
    });

    canvas.addEventListener("pointermove", function (event) {
        if (!dragging) {
            return;
        }
        const bounds = canvas.getBoundingClientRect();
        offsetX += (event.clientX - dragX) * (canvas.width / bounds.width);
        offsetY += (event.clientY - dragY) * (canvas.height / bounds.height);
        dragX = event.clientX;
        dragY = event.clientY;
        drawImage();
    });

    canvas.addEventListener("pointerup", function () {
        dragging = false;
    });
    canvas.addEventListener("pointercancel", function () {
        dragging = false;
    });

    cancel.addEventListener("click", function () {
        closeCropper(true);
    });

    dialog.addEventListener("click", function (event) {
        if (event.target === dialog) {
            closeCropper(true);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && !dialog.hidden) {
            closeCropper(true);
        }
    });

    usePhoto.addEventListener("click", function () {
        if (!image.naturalWidth) {
            return;
        }
        const sourceX = Math.max(0, -offsetX / scale);
        const sourceY = Math.max(0, -offsetY / scale);
        const sourceSize = canvas.width / scale;
        const output = document.createElement("canvas");
        const outputSize = Math.min(2048, Math.max(640, Math.round(sourceSize)));
        output.width = outputSize;
        output.height = outputSize;
        output.getContext("2d").drawImage(
            image,
            sourceX,
            sourceY,
            sourceSize,
            sourceSize,
            0,
            0,
            outputSize,
            outputSize
        );
        output.toBlob(function (blob) {
            if (!blob) {
                fileInput.value = "";
                showError("The photo could not be cropped. Please try again.");
                return;
            }
            if (blob.size > maxSize) {
                fileInput.value = "";
                showError("The cropped photo is larger than 5 MB. Zoom out or choose another image.");
                return;
            }
            const outputType = allowedTypes.has(blob.type) ? blob.type : "image/png";
            const extension = outputType === "image/jpeg"
                ? "jpg"
                : outputType === "image/webp" ? "webp" : "png";
            const file = new File(
                [blob],
                `profile-photo.${extension}`,
                { type: outputType, lastModified: Date.now() }
            );
            const transfer = new DataTransfer();
            transfer.items.add(file);
            fileInput.files = transfer.files;
            if (preview) {
                if (preview.dataset.objectUrl) {
                    URL.revokeObjectURL(preview.dataset.objectUrl);
                }
                const previewUrl = URL.createObjectURL(file);
                preview.dataset.objectUrl = previewUrl;
                preview.src = previewUrl;
                preview.hidden = false;
            }
            if (placeholder) {
                placeholder.hidden = true;
            }
            closeCropper(false);
        }, imageType, imageType === "image/jpeg" ? 0.94 : undefined);
    });
});
