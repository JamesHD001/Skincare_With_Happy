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