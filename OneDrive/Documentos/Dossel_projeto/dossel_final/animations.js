(function () {
  const SELECTORS = [
    ".section-head",
    ".bioma",
    ".stat-box",
    ".step-box",
    ".caminho",
    ".dado-box",
    ".mec-item",
    ".ods-card",
    ".setor-card",
    ".vantagem",
    ".valor",
    ".araripe-box",
    ".fundador",
    ".post-card",
    ".calc",
    ".contact-form",
    ".newsletter-box",
    ".stats-band",
  ];

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12 }
  );

  const joined = SELECTORS.join(",");

  document.querySelectorAll(joined).forEach((el) => {
    el.classList.add("reveal");

    // stagger para irmãos no mesmo container (cards em grid)
    const siblings = Array.from(el.parentElement.children).filter((c) =>
      c.matches(joined)
    );
    if (siblings.length > 1) {
      const idx = siblings.indexOf(el);
      el.style.transitionDelay = idx * 0.1 + "s";
    }

    observer.observe(el);
  });
})();
