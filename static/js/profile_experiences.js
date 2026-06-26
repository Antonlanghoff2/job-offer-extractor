// Copyright Anton Langhoff
// SPDX-License-Identifier: MIT

window.addEventListener('DOMContentLoaded', () => {
  const panel = document.getElementById('experience-skill-panel-content');
  const extractButtons = document.querySelectorAll('.js-extract-experience');
  const csrfInput = document.querySelector('input[name="csrf_token"]');
  const csrfToken = csrfInput ? csrfInput.value : '';

  if (!panel || extractButtons.length === 0 || !csrfToken) {
    return;
  }

  const state = {
    experienceId: null,
    confirmUrl: null,
    skills: [],
  };

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderEmpty(message) {
    panel.innerHTML = `<div class="muted">${escapeHtml(message)}</div>`;
  }

  function renderLoading(message) {
    panel.innerHTML = `<div class="muted">${escapeHtml(message)}</div>`;
  }

  function renderSkills(skills) {
    if (!skills.length) {
      renderEmpty('Aucune compétence détectée pour cette expérience.');
      return;
    }

    const items = skills
      .map((skill, index) => {
        const confidence = typeof skill.confidence === 'number' ? Math.round(skill.confidence * 100) : '';
        return `
          <label class="card experience-skill-panel__item">
            <div class="actions" style="justify-content: space-between; align-items: flex-start;">
              <div>
                <strong>${escapeHtml(skill.name || '')}</strong>
                <div class="muted small">${escapeHtml(skill.reason || skill.source || 'professional_experience')}</div>
              </div>
              <input type="checkbox" data-skill-index="${index}" checked>
            </div>
            <div class="meta">
              <span>Confiance: ${confidence}%</span>
              ${skill.raw_text ? `<span>Source: ${escapeHtml(skill.raw_text)}</span>` : ''}
            </div>
          </label>
        `;
      })
      .join('');

    panel.innerHTML = `
      <div class="cards">
        ${items}
      </div>
      <div class="actions" style="margin-top: 14px;">
        <button type="button" class="btn" id="experience-skill-confirm">Confirmer la sélection</button>
        <button type="button" class="btn secondary" id="experience-skill-reset">Réinitialiser</button>
      </div>
      <div class="muted small" id="experience-skill-feedback" style="margin-top: 10px;"></div>
    `;

    const confirmButton = document.getElementById('experience-skill-confirm');
    const resetButton = document.getElementById('experience-skill-reset');
    const feedback = document.getElementById('experience-skill-feedback');

    if (resetButton) {
      resetButton.addEventListener('click', () => {
        panel.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
          checkbox.checked = true;
        });
        if (feedback) {
          feedback.textContent = 'Sélection réinitialisée.';
        }
      });
    }

    if (confirmButton) {
      confirmButton.addEventListener('click', async () => {
        const selected = Array.from(panel.querySelectorAll('input[type="checkbox"]'))
          .map((checkbox) => (checkbox.checked ? skills[Number(checkbox.dataset.skillIndex)] : null))
          .filter(Boolean)
          .map((skill) => ({ name: skill.name }));

        feedback.textContent = 'Enregistrement des compétences validées...';
        confirmButton.disabled = true;

        try {
          const response = await fetch(state.confirmUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRF-Token': csrfToken,
            },
            body: JSON.stringify({
              experience_id: state.experienceId,
              skills: selected,
            }),
          });
          const data = await response.json();
          if (!response.ok || data.status === 'error') {
            throw new Error(data.error || 'Impossible de confirmer les compétences.');
          }

          const row = document.querySelector(`tr[data-item-id="${state.experienceId}"]`);
          if (row) {
            const cell = row.querySelector('[data-field="skills_text"]');
            if (cell) {
              cell.textContent = selected.map((skill) => skill.name).join(', ') || '—';
            }
          }
          feedback.textContent = 'Compétences confirmées.';
          renderSkills((data.confirmed_skills || []).map((name) => ({ name, confidence: 1, reason: 'Compétence confirmée' })));
        } catch (error) {
          feedback.textContent = error.message || 'Erreur lors de la confirmation.';
          confirmButton.disabled = false;
        }
      });
    }
  }

  async function extractSkills(button) {
    state.experienceId = button.dataset.experienceId;
    state.confirmUrl = button.dataset.confirmUrl;
    renderLoading('Extraction en cours...');
    try {
      const response = await fetch(button.dataset.extractUrl, {
        method: 'POST',
        headers: {
          'X-CSRF-Token': csrfToken,
        },
      });
      const data = await response.json();
      if (!response.ok || data.status === 'error') {
        throw new Error(data.error || 'Extraction impossible.');
      }
      state.skills = data.suggested_skills || [];
      renderSkills(state.skills);
    } catch (error) {
      renderEmpty(error.message || 'Extraction impossible.');
    }
  }

  extractButtons.forEach((button) => {
    button.addEventListener('click', () => {
      extractSkills(button);
    });
  });
});
