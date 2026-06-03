/**
 * Single searchable dropdown (Select2) for game form selects.
 */
(function () {
  function initSelect2() {
    if (!window.jQuery || !jQuery.fn.select2) return;

    jQuery(".enhanced-select").each(function () {
      const $el = jQuery(this);
      if ($el.data("select2")) return;

      const placeholder =
        $el.data("placeholder") ||
        $el.find('option[value=""]').first().text() ||
        "";

      $el.select2({
        width: "100%",
        language: "es",
        placeholder: placeholder,
        allowClear: !$el.prop("required"),
        dropdownParent: jQuery("#game-form"),
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSelect2);
  } else {
    initSelect2();
  }
})();
