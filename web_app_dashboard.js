
    const summary = document.getElementById('summary');
    const trendCompetences = document.getElementById('trend-competences');
    const trendContrats = document.getElementById('trend-contrats');
    const trendNiveaux = document.getElementById('trend-niveaux');
    const detailCompetences = document.getElementById('detail-competences');
    const detailMetiers = document.getElementById('detail-metiers');
    const detailContrats = document.getElementById('detail-contrats');
    const detailNiveaux = document.getElementById('detail-niveaux');
    const marketContext = document.getElementById('market-context');
    const offersBody = document.getElementById('offers-body');
    const topMetiers = document.getElementById('top-metiers');
    const topCompetences = document.getElementById('top-competences');
    const metiersCaption = document.getElementById('metiers-caption');
    const competencesCaption = document.getElementById('competences-caption');
    const trendCompetencesCaption = document.getElementById('trend-competences-caption');
    const trendContratsCaption = document.getElementById('trend-contrats-caption');
    const trendNiveauxCaption = document.getElementById('trend-niveaux-caption');
    const territoryInput = document.getElementById('territoire');
    const periodInput = document.getElementById('periode');
    const topNInput = document.getElementById('top-n');
    const territoryList = document.getElementById('territoire-list');
    const trendsCaption = document.getElementById('trends-caption');
    const offersCaption = document.getElementById('offers-caption');
    const form = document.getElementById('filters');
    const resetButton = document.getElementById('reset');

    function escapeHtml(text) {
      return String(text ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function renderSummary(state) {
      const t = state.trends;
      summary.innerHTML = [
        ['Offres brutes', state.nombre_offres_brutes, `${state.nombre_offres_filtrees} retenues`],
        ['Offres filtrées', state.nombre_offres_filtrees, `${t.periode_jours} jours`],
        ['Compétences', Object.keys(t.competences || {}).length, 'fréquences comptées'],
        ['Métiers', Object.keys(t.metiers || {}).length, 'fréquences comptées'],
      ].map(([label, value, caption]) => `
        <div class="metric">
          <div class="label">${label}</div>
          <div class="value">${value}</div>
          <div class="caption">${caption}</div>
        </div>
      `).join('');
      trendsCaption.textContent = state.territoire ? `Territoire ${state.territoire}` : 'Tous territoires';
      trendCompetencesCaption.textContent = `Top ${state.top_n}`;
      trendContratsCaption.textContent = `Top ${state.top_n}`;
      trendNiveauxCaption.textContent = `Top ${state.top_n}`;
      metiersCaption.textContent = `Top ${state.top_n}`;
      competencesCaption.textContent = `Top ${state.top_n}`;
      offersCaption.textContent = `${state.offers.length} offres affichées`;
    }

    function sortEntriesByCount(data) {
      return Object.entries(data || {})
        .map(([label, count]) => [String(label), Number(count)])
        .filter(([label, count]) => label.trim() && Number.isFinite(count) && count > 0)
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'fr', { sensitivity: 'base' }));
    }

    function isLikelyCompetenceNoise(label) {
      const text = String(label ?? '').trim();
      if (!text || text.length > 80) return true;
      if (text.indexOf(String.fromCharCode(10)) >= 0 || text.includes('.') || text.includes('!') || text.includes('?') || text.includes(';') || text.includes(':')) return true;
      if (text.split(' ').filter(Boolean).length > 12) return true;
      const lowered = text.toLowerCase();
      return [
        'vous apprendrez',
        'vous serez',
        'formation',
        'mission',
        'objectif',
        'capacité à',
        'capacite a',
        'maîtriser',
        'maitriser',
        'savoir faire',
      ].some(fragment => lowered.includes(fragment));
    }

    function formatPercentage(count, totalOffers) {
      return totalOffers > 0 ? ((count / totalOffers) * 100).toFixed(1).replace('.', ',') : '0,0';
    }

    function renderTrendBlock(title, data, totalOffers, limit) {
      const isCompetenceBlock = title.toLowerCase().includes('compétences');
      const entries = sortEntriesByCount(data).filter(([label]) => !isCompetenceBlock || !isLikelyCompetenceNoise(label)).slice(0, Math.max(limit, 1));
      if (!entries.length) {
        return '<div class="trend-empty">Aucune donnée disponible pour cette catégorie.</div>';
      }
      const max = Math.max(...entries.map(([, count]) => count));
      const rows = entries.map(([label, count]) => {
        const width = max ? Math.max(8, (count / max) * 100) : 0;
        const percentage = formatPercentage(count, totalOffers);
        return `
          <div class="trend-row">
            <div class="trend-head">
              <div class="trend-label" title="${escapeHtml(label)}">${escapeHtml(label)}</div>
              <div class="trend-stats">${count} offres · ${percentage} %</div>
            </div>
            <div class="trend-track"><div class="trend-fill" style="width:${width}%"></div></div>
          </div>
        `;
      }).join('');
      return `<div class="trend-list">${rows}</div>`;
    }

    function renderRankingTable(container, data, totalOffers, emptyLabel, limit) {
      const entries = Object.entries(data || {})
        .map(([label, count]) => [label, Number(count)])
        .filter(([, count]) => Number.isFinite(count) && count > 0)
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'fr', { sensitivity: 'base' }))
        .slice(0, Math.max(limit, 1));

      if (!entries.length) {
        container.innerHTML = `<tbody><tr><td colspan="3" class="ranking-empty">${emptyLabel}</td></tr></tbody>`;
        return;
      }

      const rows = entries.map(([label, count]) => {
        const percentage = totalOffers > 0 ? ((count / totalOffers) * 100).toFixed(1).replace('.', ',') : '0,0';
        return `<tr>
          <td>${escapeHtml(label)}</td>
          <td class="ranking-value">${count}</td>
          <td class="ranking-value">${percentage} %</td>
        </tr>`;
      }).join('');

      container.innerHTML = `
        <thead>
          <tr>
            <th>Nom</th>
            <th class="ranking-value">Offres</th>
            <th class="ranking-value">Part</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      `;
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

    function renderOffers(offers) {
      if (!offers.length) {
        offersBody.innerHTML = '<tr><td colspan="6" class="empty">Aucune offre ne correspond aux filtres.</td></tr>';
        return;
      }
      offersBody.innerHTML = offers.map(offer => {
        const competences = (offer.competences || []).map(c => `<span class="chip">${escapeHtml(c)}</span>`).join(' ');
        const description = offer.description ? escapeHtml(offer.description) : '<span class="empty">Aucune description</span>';
        return `
          <tr>
            <td>${escapeHtml(offer.date || '')}</td>
            <td>
              <div class="offer-title">${escapeHtml(offer.intitule || offer.metier || '')}</div>
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

    async function loadState() {
      const params = new URLSearchParams();
      if (territoryInput.value.trim()) params.set('territoire', territoryInput.value.trim());
      params.set('periode', periodInput.value || '30');
      params.set('top_n', topNInput.value || '10');
      const response = await fetch(`/api/state?${params.toString()}`);
      if (!response.ok) throw new Error('Erreur lors du chargement des données');
      const state = await response.json();
      renderSummary(state);
      trendCompetences.innerHTML = renderTrendBlock('Compétences', state.trends.competences || {}, state.trends.nombre_offres || 0, state.top_n || 10);
      trendContrats.innerHTML = renderTrendBlock('Nature des contrats', state.trends.contrats || {}, state.trends.nombre_offres || 0, state.top_n || 10);
      trendNiveaux.innerHTML = renderTrendBlock('Ancienneté demandée', state.trends.niveau || {}, state.trends.nombre_offres || 0, state.top_n || 10);
      detailCompetences.innerHTML = renderTrendBlock('Compétences', state.trends.competences || {}, state.trends.nombre_offres || 0, Math.max(state.top_n || 10, 20));
      detailMetiers.innerHTML = renderTrendBlock('Métiers', state.trends.metiers || {}, state.trends.nombre_offres || 0, Math.max(state.top_n || 10, 20));
      detailContrats.innerHTML = renderTrendBlock('Nature des contrats', state.trends.contrats || {}, state.trends.nombre_offres || 0, Math.max(state.top_n || 10, 20));
      detailNiveaux.innerHTML = renderTrendBlock('Ancienneté demandée', state.trends.niveau || {}, state.trends.nombre_offres || 0, Math.max(state.top_n || 10, 20));
      renderRankingTable(topMetiers, state.top_metiers || {}, state.trends.nombre_offres || 0, 'Aucun intitulé de poste disponible', state.top_n || 10);
      renderRankingTable(topCompetences, state.top_competences || {}, state.trends.nombre_offres || 0, 'Aucune compétence disponible', state.top_n || 10);
      renderMarketContext(state.market_context || []);
      renderOffers(state.offers || []);
      populateTerritories(state.territoire_options || []);
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      await loadState();
    });

    resetButton.addEventListener('click', async () => {
      territoryInput.value = '';
      periodInput.value = 30;
      topNInput.value = 10;
      await loadState();
    });

    loadState().catch(err => {
      summary.innerHTML = `<div class="metric" style="grid-column:1/-1;border-color:var(--danger);color:var(--danger);">${escapeHtml(err.message)}</div>`;
    });
  