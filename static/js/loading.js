/**
 * Full-page loading overlay for slow form submits and marked navigation links.
 * Skips forms/links with data-no-loading. Waits briefly before showing to avoid flashes.
 */
(function () {
  const overlay = document.getElementById("page-loading");
  if (!overlay) return;

  const SHOW_DELAY_MS = 200;
  let showTimer = null;

  function hideLoading() {
    clearTimeout(showTimer);
    showTimer = null;
    overlay.hidden = true;
    document.body.classList.remove("is-loading");
  }

  function showLoading() {
    clearTimeout(showTimer);
    showTimer = window.setTimeout(function () {
      overlay.hidden = false;
      document.body.classList.add("is-loading");
    }, SHOW_DELAY_MS);
  }

  function isSlowNavPath(pathname) {
    const path = (pathname || "").replace(/\/+$/, "") || "/";
    return path.endsWith("/stats");
  }

  function shouldArmLink(link) {
    if (!(link instanceof HTMLAnchorElement)) return false;
    if (link.dataset.noLoading !== undefined) return false;
    if (link.target && link.target !== "_self") return false;
    if (link.hasAttribute("download")) return false;
    const href = link.getAttribute("href") || "";
    if (href === "#" || href === "") return false;
    if (link.origin !== window.location.origin) return false;
    return (
      isSlowNavPath(link.pathname) ||
      link.dataset.loading !== undefined ||
      link.classList.contains("js-show-loading")
    );
  }

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.dataset.noLoading !== undefined) return;
    if (form.target && form.target !== "_self") return;
    showLoading();
  });

  document.addEventListener("click", function (event) {
    const link = event.target.closest("a[data-loading], a.js-show-loading");
    if (!link || !shouldArmLink(link)) return;
    showLoading();
  });

  window.addEventListener("pageshow", hideLoading);
})();
