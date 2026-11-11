    // Header shadow on scroll
    const header = document.querySelector("header");
    window.addEventListener("scroll", () => {
        header.classList.toggle("scrolled", window.scrollY > 20);
    });

    // Smooth scroll CTA
    document.getElementById("exploreBtn").addEventListener("click", () => {
        document.getElementById("products").scrollIntoView({ behavior: "smooth" });
    });

    // Category interaction
    const categories = document.querySelectorAll(".category-card");
    categories.forEach(card => {
        card.addEventListener("click", () => {
            categories.forEach(c => c.classList.remove("active"));
            card.classList.add("active");
        });
    });

    const hamburger = document.getElementById("hamburger");
    const navMenu = document.getElementById("navMenu");

    hamburger.addEventListener("click", () => {
        navMenu.classList.toggle("active");
    });
