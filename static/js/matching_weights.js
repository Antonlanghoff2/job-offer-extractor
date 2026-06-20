// Copyright Anton Langhoff <anton@langhoff.fr>
// SPDX-License-Identifier: MIT

(function () {
  function clamp(value) {
    var parsed = Number(value);
    if (!isFinite(parsed)) {
      return 0;
    }
    if (parsed < 0) {
      return 0;
    }
    if (parsed > 100) {
      return 100;
    }
    return Math.round(parsed);
  }

  function readWeights(form) {
    var weights = {};
    form.querySelectorAll('[data-weight-number]').forEach(function (input) {
      weights[input.getAttribute('data-weight-number')] = clamp(input.value);
    });
    return weights;
  }

  function sumWeights(weights) {
    return Object.keys(weights).reduce(function (acc, key) {
      return acc + clamp(weights[key]);
    }, 0);
  }

  function updateSummary(form) {
    var weights = readWeights(form);
    var total = sumWeights(weights);
    var totalEl = form.querySelector('[data-weights-total]');
    var messageEl = form.querySelector('[data-weights-message]');
    var submitButton = form.querySelector('[data-search-submit]');
    var valid = Math.abs(total - 100) <= 0.01;

    if (totalEl) {
      totalEl.textContent = total.toFixed(0) + ' %';
    }
    if (messageEl) {
      if (valid) {
        messageEl.textContent = '';
        messageEl.classList.remove('alert', 'alert--error');
        messageEl.classList.add('muted');
      } else {
        messageEl.textContent = 'Le total des pondérations doit être égal à 100 %.';
        messageEl.classList.add('alert', 'alert--error');
        messageEl.classList.remove('muted');
      }
    }
    if (submitButton) {
      submitButton.disabled = !valid;
      submitButton.setAttribute('aria-disabled', String(!valid));
    }
  }

  function syncPair(form, key, value, sourceType) {
    var rangeInput = form.querySelector('[data-weight-range="' + key + '"]');
    var numberInput = form.querySelector('[data-weight-number="' + key + '"]');
    var display = form.querySelector('[data-weight-display="' + key + '"]');
    var nextValue = clamp(value);

    if (rangeInput && sourceType !== 'range') {
      rangeInput.value = String(nextValue);
    }
    if (numberInput && sourceType !== 'number') {
      numberInput.value = String(nextValue);
    }
    if (display) {
      display.textContent = String(nextValue);
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var form = document.querySelector('[data-matching-weights-form]');
    if (!form) {
      return;
    }

    var defaultWeights = {};
    try {
      defaultWeights = JSON.parse(form.getAttribute('data-default-weights') || '{}');
    } catch (error) {
      defaultWeights = {};
    }

    form.querySelectorAll('[data-weight-range]').forEach(function (input) {
      input.addEventListener('input', function () {
        syncPair(form, input.getAttribute('data-weight-range'), input.value, 'range');
        updateSummary(form);
      });
    });

    form.querySelectorAll('[data-weight-number]').forEach(function (input) {
      input.addEventListener('input', function () {
        syncPair(form, input.getAttribute('data-weight-number'), input.value, 'number');
        updateSummary(form);
      });
      input.addEventListener('change', function () {
        syncPair(form, input.getAttribute('data-weight-number'), input.value, 'number');
        updateSummary(form);
      });
    });

    var resetButton = form.querySelector('[data-weights-reset]');
    if (resetButton) {
      resetButton.addEventListener('click', function () {
        Object.keys(defaultWeights).forEach(function (key) {
          syncPair(form, key, defaultWeights[key], null);
        });
        updateSummary(form);
      });
    }

    updateSummary(form);
  });
})();
