/**
 * Filterable <select> — type in the paired input to narrow options.
 */
(function () {
  function initWrap(wrap) {
    const select = wrap.querySelector("select.search-select");
    const input = wrap.querySelector(".search-select-filter");
    if (!select || !input) return;

    const syncInputFromSelect = () => {
      const opt = select.options[select.selectedIndex];
      if (opt && opt.value) {
        input.value = opt.text;
      }
    };

    const filterOptions = () => {
      const q = input.value.trim().toLowerCase();
      let visible = 0;
      Array.from(select.options).forEach((opt) => {
        if (!opt.value) {
          opt.hidden = false;
          return;
        }
        const match = !q || opt.text.toLowerCase().includes(q);
        opt.hidden = !match;
        if (match) visible += 1;
      });
      wrap.classList.toggle("search-select--empty", q.length > 0 && visible === 0);
    };

    input.addEventListener("input", filterOptions);
    input.addEventListener("focus", () => {
      wrap.classList.add("search-select--open");
      filterOptions();
    });
    input.addEventListener("blur", () => {
      window.setTimeout(() => wrap.classList.remove("search-select--open"), 150);
    });
    select.addEventListener("change", () => {
      syncInputFromSelect();
      filterOptions();
    });
    select.addEventListener("focus", () => wrap.classList.add("search-select--open"));
    select.addEventListener("blur", () => {
      window.setTimeout(() => wrap.classList.remove("search-select--open"), 150);
    });

    syncInputFromSelect();
    filterOptions();
  }

  document.querySelectorAll(".search-select").forEach(initWrap);
})();
