
    const summary = document.getElementById('summary');
    const territoryInput = document.getElementById('territoire');
    const indeedInput = document.getElementById('indeed');
    const periodInput = document.getElementById('periode');
    const territoryList = document.getElementById('territoire-list');
    const form = document.getElementById('filters');
    const offersCaption = document.getElementById('offers-caption');
    const importJsonButton = document.getElementById('import-json-btn');
    const importJsonInput = document.getElementById('import-json-file');

    const ftCaption = document.getElementById('ft-caption');
    const indeedCaption = document.getElementById('indeed-caption');
    const comparisonCaption = document.getElementById('comparison-caption');
    const deltaOffers = document.getElementById('delta-offers');
    const commonSkillsCount = document.getElementById('common-skills-count');
    const ftExclusiveCount = document.getElementById('ft-exclusive-count');
    const indeedExclusiveCount = document.getElementById('indeed-exclusive-count');
    const commonSkills = document.getElementById('common-skills');
    const ftExclusive = document.getElementById('ft-exclusive');
    const indeedExclusive = document.getElementById('indeed-exclusive');

    const ftCompetences = document.getElementById('ft-competences');
    const ftMetiers = document.getElementById('ft-metiers');
    const ftNiveaux = document.getElementById('ft-niveaux');
    const ftContrats = document.getElementById('ft-contrats');
    const indeedCompetences = document.getElementById('indeed-competences');
    const indeedMetiers = document.getElementById('indeed-metiers');
    const indeedNiveaux = document.getElementById('indeed-niveaux');
    const indeedContrats = document.getElementById('indeed-contrats');
    const offersFt = document.getElementById('offers-ft');
    const offersIndeed = document.getElementById('offers-indeed');
    const marketContext = document.getElementById('market-context');

    function escapeHtml(text) {
      return String(text ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function renderMetricRow(container, label, value, caption) {
      container.innerHTML += `
        <div class="metric">
          <div class="label">${label}</div>
          <div class="value">${value}</div>
          <div class="caption">${caption}</div>
        </div>
      `;
    }

    function renderSummary(state) {
      summary.innerHTML = '';
      renderMetricRow(summary, 'Offres FT', state.nombre_offres_ft, `${state.periode_jours} jours`);
      renderMetricRow(summary, 'Offres Indeed', state.nombre_offres_indeed, `${state.indeed_count} chargées`);
      renderMetricRow(summary, 'Écart', state.comparison ? state.comparison.comparaison.ecart_nombre_offres : 0, 'France Travail - Indeed');
      renderMetricRow(summary, 'Contexte', state.market_context.length, 'lignes T3 2025');
      ftCaption.textContent = state.territoire ? `Territoire ${state.territoire}` : 'Tous territoires';
      indeedCaption.textContent = state.source_mode === 'local_json' ? `Import local: ${state.source_label}` : state.indeed_path;
      comparisonCaption.textContent = state.source_mode === 'local_json' ? `Comparaison sur JSON local` : (state.territoire ? `Comparaison sur ${state.territoire}` : 'Comparaison globale');
      offersCaption.textContent = `${state.offers_ft.length} FT / ${state.offers_indeed.length} ${state.source_mode === 'local_json' ? 'local' : 'Indeed'} affichées`;
    }

    function renderBars(container, data, emptyLabel) {
      const entries = Object.entries(data || {});
      if (!entries.length) {
        container.innerHTML = `<div class="empty">${emptyLabel}</div>`;
        return;
      }
      const max = Math.max(...entries.map(([, count]) => count));
      container.innerHTML = entries.slice(0, 12).map(([label, count]) => {
        const width = max ? Math.max(8, (count / max) * 100) : 0;
        return `
          <div>
            <div class="bar-row">
              <div class="bar-label" title="${escapeHtml(label)}">${escapeHtml(label)}</div>
              <div class="bar-value">${count}</div>
            </div>
            <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
          </div>
        `;
      }).join('');
    }

    function renderComparison(state) {
      const comparison = state.comparison;
      if (!comparison) {
        deltaOffers.textContent = '0';
        commonSkillsCount.textContent = '0';
        ftExclusiveCount.textContent = '0';
        indeedExclusiveCount.textContent = '0';
        commonSkills.innerHTML = '<div class="empty">Aucune comparaison disponible.</div>';
        ftExclusive.innerHTML = '<div class="empty">Aucune comparaison disponible.</div>';
        indeedExclusive.innerHTML = '<div class="empty">Aucune comparaison disponible.</div>';
        return;
      }
      deltaOffers.textContent = comparison.comparaison.ecart_nombre_offres;
      commonSkillsCount.textContent = Object.keys(comparison.comparaison.competences_communes || {}).length;
      ftExclusiveCount.textContent = Object.keys(comparison.comparaison.competences_fr_exclusives || {}).length;
      indeedExclusiveCount.textContent = Object.keys(comparison.comparaison.competences_indeed_exclusives || {}).length;
      renderBars(commonSkills, comparison.comparaison.competences_communes || {}, 'Aucune compétence commune');
      renderBars(ftExclusive, comparison.comparaison.competences_fr_exclusives || {}, 'Aucune compétence FT exclusive');
      renderBars(indeedExclusive, comparison.comparaison.competences_indeed_exclusives || {}, 'Aucune compétence Indeed exclusive');
    }

    function renderMarketContext(rows) {
      if (!rows.length) {
        marketContext.innerHTML = '<tr><td class="empty">Aucun contexte marché disponible.</td></tr>';
        return;
      }
      const headers = Object.keys(rows[0]).slice(0, 4);
      marketContext.innerHTML = `
        <thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>
        <tbody>
          ${rows.map(row => `
            <tr>${headers.map(header => `<td>${escapeHtml(row[header] ?? '')}</td>`).join('')}</tr>
          `).join('')}
        </tbody>
      `;
    }

    function renderOffers(container, offers) {
      if (!offers.length) {
        container.innerHTML = '<tr><td colspan="6" class="empty">Aucune offre ne correspond aux filtres.</td></tr>';
        return;
      }
      container.innerHTML = offers.map(offer => {
        const competences = (offer.competences || []).map(c => `<span class="chip">${escapeHtml(c)}</span>`).join(' ');
        const description = offer.description ? escapeHtml(offer.description) : '<span class="empty">Aucune description</span>';
        return `
          <tr>
            <td>${escapeHtml(offer.date || '')}</td>
            <td>
              <div class="offer-title">${escapeHtml(offer.intitule || offer.titre || offer.metier || '')}</div>
              <div class="offer-company">${escapeHtml(offer.entreprise || '')}</div>
              <div class="offer-desc">${description}</div>
            </td>
            <td>${escapeHtml(offer.territoire || '')}</td>
            <td>${escapeHtml(offer.niveau || '')}</td>
            <td>${escapeHtml(offer.contrat || '')}</td>
            <td><div class="chips">${competences || '<span class="empty">Aucune compétence</span>'}</div></td>
          </tr>
        `;
      }).join('');
    }

    function populateTerritories(options) {
      territoryList.innerHTML = options.map(value => `<option value="${escapeHtml(value)}"></option>`).join('');
    }

    async function loadStateFromIndeed() {
      const params = new URLSearchParams();
      if (territoryInput.value.trim()) params.set('territoire', territoryInput.value.trim());
      if (indeedInput.value.trim()) params.set('indeed', indeedInput.value.trim());
      params.set('periode', periodInput.value || '30');
      const response = await fetch(`/api/state?${params.toString()}`);
      if (!response.ok) throw new Error('Erreur lors du chargement des données');
      return response.json();
    }

    async function loadStateFromUploadedFile(file) {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('periode', periodInput.value || '30');
      if (territoryInput.value.trim()) formData.append('territoire', territoryInput.value.trim());
      const response = await fetch('/api/import-json', {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Erreur lors de l'import JSON");
      }
      return response.json();
    }

    function applyState(state) {
      renderSummary(state);
      renderBars(ftCompetences, state.france_travail.competences || {}, 'Aucune compétence FT');
      renderBars(ftMetiers, state.france_travail.metiers || {}, 'Aucun métier FT');
      renderBars(ftNiveaux, state.france_travail.niveau || {}, 'Aucun niveau FT');
      renderBars(ftContrats, state.france_travail.contrats || {}, 'Aucun contrat FT');
      renderBars(indeedCompetences, state.indeed.competences || {}, 'Aucune compétence source');
      renderBars(indeedMetiers, state.indeed.metiers || {}, 'Aucun métier source');
      renderBars(indeedNiveaux, state.indeed.niveau || {}, 'Aucun niveau source');
      renderBars(indeedContrats, state.indeed.contrats || {}, 'Aucun contrat source');
      renderComparison(state);
      renderOffers(offersFt, state.offers_ft || []);
      renderOffers(offersIndeed, state.offers_indeed || []);
      renderMarketContext(state.market_context || []);
      populateTerritories(state.territoire_options || []);
    }

    async function loadState() {
      applyState(await loadStateFromIndeed());
    }

    async function importLocalJson(file) {
      applyState(await loadStateFromUploadedFile(file));
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      await loadState();
    });

    importJsonButton.addEventListener('click', () => {
      importJsonInput.click();
    });

    importJsonInput.addEventListener('change', async () => {
      const file = importJsonInput.files && importJsonInput.files[0];
      if (!file) return;
      try {
        await importLocalJson(file);
      } finally {
        importJsonInput.value = '';
      }
    });

    loadState().catch(err => {
      summary.innerHTML = `<div class="metric" style="grid-column:1/-1;border-color:var(--danger);color:var(--danger);"><div class="label">Erreur</div><div class="value">X</div><div class="caption">${escapeHtml(err.message)}</div></div>`;
    });
  