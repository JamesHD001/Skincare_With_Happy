// Header shadow on scroll
const header = document.querySelector("header");

if (header) {
    const updateHeaderShadow = () => {
        header.classList.toggle("scrolled", window.scrollY > 20);
    };

    updateHeaderShadow();
    window.addEventListener("scroll", updateHeaderShadow, { passive: true });
}

// Smooth scrolling for optional in-page explore controls
const exploreButton = document.getElementById("exploreBtn");
const productsSection = document.getElementById("products");

if (exploreButton && productsSection) {
    exploreButton.addEventListener("click", () => {
        productsSection.scrollIntoView({ behavior: "smooth" });
    });
}

// Legacy category cards, when present on older templates
const categories = document.querySelectorAll(".category-card");

categories.forEach((card) => {
    card.addEventListener("click", () => {
        categories.forEach((item) => item.classList.remove("active"));
        card.classList.add("active");
    });
});

// Accessible mobile navigation
const hamburger = document.getElementById("hamburger");
const navMenu = document.getElementById("navMenu");

if (hamburger && navMenu) {
    hamburger.addEventListener("click", () => {
        const isOpen = navMenu.classList.toggle("active");
        hamburger.setAttribute("aria-expanded", String(isOpen));
        hamburger.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
    });

    navMenu.addEventListener("click", (event) => {
        if (event.target.closest("a")) {
            navMenu.classList.remove("active");
            hamburger.setAttribute("aria-expanded", "false");
            hamburger.setAttribute("aria-label", "Open navigation");
        }
    });
}

// Five-slide skincare editorial carousel
const heroCarousel = document.querySelector("[data-hero-carousel]");
if (heroCarousel) {
    const slides = Array.from(heroCarousel.querySelectorAll(".home-hero__slide"));
    const status = document.querySelector("[data-hero-status]");
    const previous = document.querySelector("[data-hero-prev]");
    const next = document.querySelector("[data-hero-next]");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let activeIndex = 0;
    let rotation;

    const showSlide = (index) => {
        activeIndex = (index + slides.length) % slides.length;
        slides.forEach((slide, slideIndex) => {
            const active = slideIndex === activeIndex;
            slide.classList.toggle("is-active", active);
            slide.setAttribute("aria-hidden", String(!active));
        });
        if (status) status.textContent = String(activeIndex + 1).padStart(2, "0") + " / " + String(slides.length).padStart(2, "0");
    };
    const stopRotation = () => window.clearInterval(rotation);
    const startRotation = () => {
        if (!reducedMotion) {
            stopRotation();
            rotation = window.setInterval(() => showSlide(activeIndex + 1), 5500);
        }
    };
    previous?.addEventListener("click", () => { showSlide(activeIndex - 1); startRotation(); });
    next?.addEventListener("click", () => { showSlide(activeIndex + 1); startRotation(); });
    heroCarousel.addEventListener("mouseenter", stopRotation);
    heroCarousel.addEventListener("mouseleave", startRotation);
    heroCarousel.addEventListener("focusin", stopRotation);
    heroCarousel.addEventListener("focusout", startRotation);
    showSlide(0);
    startRotation();
}

// Add products in the background and update the shared cart indicator
document.querySelectorAll(".js-add-to-cart").forEach((form) => {
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector('button[type="submit"]');
        const message = form.querySelector(".catalog-card__cart-message");
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = "Adding...";
        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: { "X-Requested-With": "XMLHttpRequest" }
            });
            const result = await response.json();
            if (!response.ok || result.status !== "success") throw new Error(result.message || "The product could not be added.");
            document.querySelectorAll("[data-cart-count]").forEach((count) => { count.textContent = result.cart_count; });
            document.querySelectorAll(".cart-nav").forEach((link) => link.setAttribute("aria-label", "Open cart, " + result.cart_count + " items"));
            if (message) message.textContent = "Added to cart ✓";
            button.textContent = "Added ✓";
        } catch (error) {
            if (message) message.textContent = error.message;
            button.textContent = originalText;
        } finally {
            window.setTimeout(() => { button.textContent = originalText; button.disabled = false; }, 1400);
        }
    });
});
