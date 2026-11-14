(function () {
    "use strict";

    const MAX_IMAGE_SIZE = 4 * 1024 * 1024;
    const ALLOWED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

    function setStatus(element, message, isError) {
        if (!element) {
            return;
        }

        element.textContent = message;
        element.classList.toggle("is-error", Boolean(isError));
    }

    function initializeImageInput(input) {
        const previewContainer = input.closest("label")
            ? input.closest("label").parentElement.querySelector("[data-image-preview]")
            : input.closest(".product-image-cell");
        const previewImage = previewContainer
            ? previewContainer.querySelector(".image-preview-large, .product-image-preview")
            : null;
        const placeholder = previewContainer
            ? previewContainer.querySelector(".image-preview-placeholder, .product-image-empty")
            : null;
        const status = input.getAttribute("aria-describedby")
            ? document.getElementById(input.getAttribute("aria-describedby").split(/\\s+/).pop())
            : previewContainer
                ? previewContainer.querySelector(".image-preview-status")
                : null;

        if (!previewImage || !status) {
            return;
        }

        let currentObjectUrl = null;

        input.addEventListener("change", function () {
            const file = input.files && input.files[0];

            if (!file) {
                setStatus(status, "No new image selected. The current image will be kept.", false);
                return;
            }

            if (!ALLOWED_TYPES.has(file.type)) {
                input.value = "";
                setStatus(status, "Choose a JPEG, PNG, or WebP image.", true);
                return;
            }

            if (file.size > MAX_IMAGE_SIZE) {
                input.value = "";
                setStatus(status, "The image must be 4 MB or smaller.", true);
                return;
            }

            if (currentObjectUrl) {
                URL.revokeObjectURL(currentObjectUrl);
            }

            currentObjectUrl = URL.createObjectURL(file);
            previewImage.onload = function () {
                previewImage.hidden = false;
                if (placeholder) {
                    placeholder.hidden = true;
                }
                setStatus(status, "Preview ready: " + file.name, false);
            };
            previewImage.onerror = function () {
                previewImage.hidden = true;
                if (placeholder) {
                    placeholder.hidden = false;
                }
                input.value = "";
                setStatus(status, "This image could not be previewed. Choose another file.", true);
                URL.revokeObjectURL(currentObjectUrl);
                currentObjectUrl = null;
            };
            previewImage.src = currentObjectUrl;
        });

        window.addEventListener("beforeunload", function () {
            if (currentObjectUrl) {
                URL.revokeObjectURL(currentObjectUrl);
            }
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll(".product-image-upload").forEach(initializeImageInput);
    });
})();
