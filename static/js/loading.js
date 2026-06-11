/**
 * Full-page loading overlay for slow form submits and navigation.
 * Skips forms/links with data-no-loading. Links wait briefly before showing.
 */
(function () {
  const overlay = document.getElementById("page-loading");
  if (!overlay) return;

  const LINK_DELAY_MS = 150;
  let showTimer = null;

  function hideLoading() {
    clearTimeout(showTimer);
    showTimer = null;
    overlay.hidden = true;
    document.body.classList.remove("is-loading");
  }

  function revealLoading() {
    overlay.hidden = false;
    document.body.classList.add("is-loading");
  }

  function showLoadingForLink() {
    clearTimeout(showTimer);
    showTimer = window.setTimeout(revealLoading, LINK_DELAY_MS);
  }

  function isSlowNavPath(pathname) {
    const path = (pathname || "").replace(/\/+$/, "") || "/";
    if (path === "/" || path === "/games" || path === "/stats" || path === "/leagues") {
      return true;
    }
    // League detail only (not /leagues/new, /edit, /export, …)
    return /^\/leagues\/[^/]+$/.test(path);
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
    clearTimeout(showTimer);
    revealLoading();
  });

  document.addEventListener("click", function (event) {
    const link = event.target.closest("a[href]");
    if (!link || !shouldArmLink(link)) return;
    showLoadingForLink();
  });

  window.addEventListener("pageshow", hideLoading);
})();
