/**
 * Live validation for league VP threshold input (mirrors games/scoring.parse_vp_thresholds_input).
 */
(function () {
  function parseVpThresholdsInput(raw) {
    const text = (raw || "").trim();
    if (!text) {
      return { ok: true, thresholds: [] };
    }
    const parts = text.split(/[,;\s]+/).filter((part) => part.length > 0);
    const values = [];
    for (const part of parts) {
      if (!/^\d+$/.test(part)) {
        return {
          ok: false,
          message: `«${part}» no es un número válido.`,
        };
      }
      const value = Number.parseInt(part, 10);
      if (value < 1) {
        return {
          ok: false,
          message: "Cada umbral debe ser mayor a 1.",
        };
      }
      values.push(value);
    }
    const unique = [...new Set(values)].sort((a, b) => a - b);
    return { ok: true, thresholds: unique };
  }

  function formatThresholdsLabel(thresholds) {
    if (!thresholds.length) {
      return "Sin bonos por PV.";
    }
    const list = thresholds.map((t) => `${t} PV`).join(", ");
    return `Umbrales: ${list} (+1 por cada umbral alcanzado).`;
  }

  function initVpThresholdsField(root) {
    const input = root.querySelector(".vp-thresholds-input");
    const feedback = root.querySelector(".vp-thresholds-feedback");
    const form = root.closest("form.game-form");
    const submitBtn = form
      ? form.querySelector('button[type="submit"].btn-primary')
      : null;

    if (!input || !feedback) {
      return;
    }

    let lastOk = true;

    function setState(result) {
      lastOk = result.ok;
      input.classList.toggle("vp-thresholds-input--error", !result.ok);
      input.classList.toggle("vp-thresholds-input--ok", result.ok);
      feedback.classList.remove(
        "vp-thresholds-feedback--ok",
        "vp-thresholds-feedback--error"
      );

      if (result.ok) {
        feedback.textContent = formatThresholdsLabel(result.thresholds);
        feedback.classList.add("vp-thresholds-feedback--ok");
        if (submitBtn) {
          submitBtn.disabled = false;
        }
        return;
      }

      feedback.textContent = `ERROR — ${result.message}`;
      feedback.classList.add("vp-thresholds-feedback--error");
      if (submitBtn) {
        submitBtn.disabled = true;
      }
    }

    function validate() {
      setState(parseVpThresholdsInput(input.value));
    }

    input.addEventListener("input", validate);
    input.addEventListener("blur", validate);

    if (form) {
      form.addEventListener("submit", (event) => {
        const result = parseVpThresholdsInput(input.value);
        setState(result);
        if (!result.ok) {
          event.preventDefault();
          input.focus();
        }
      });
    }

    validate();
  }

  document.addEventListener("DOMContentLoaded", () => {
    document
      .querySelectorAll("[data-vp-thresholds-field]")
      .forEach(initVpThresholdsField);
  });
})();
