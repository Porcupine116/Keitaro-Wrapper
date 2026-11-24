const $ = (selector) => document.querySelector(selector);
const state = {
  refs: {domains: [], groups: [], traffic_sources: [], offers: [], campaigns: []},
  streams: [],
  campaignId: null,
  trackerUrl: null,
};

function showToast(message, isError = false) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.toggle('error-toast', isError);
  toast.classList.remove('hidden');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add('hidden'), 4200);
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}

function entityName(item, fallback = 'Без названия') {
  return item?.name || item?.title || item?.alias || fallback;
}

function entityLabel(item, fallback) {
  return `${entityName(item, fallback)} · ID ${item.id}`;
}

function fillSelect(select, items, placeholder) {
  select.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>`;
  (items || []).filter(item => !['deleted', 'archived'].includes(String(item.state || '').toLowerCase())).forEach(item => {
    const option = document.createElement('option');
    option.value = item.id;
    option.textContent = entityLabel(item, 'Без названия');
    select.append(option);
  });
}

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {'Content-Type': 'application/json', ...(options.headers || {})},
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    let message = typeof detail === 'string' ? detail : detail?.message || JSON.stringify(detail || data);
    if (response.status === 502 && detail?.keitaro) message += `\nДетали Keitaro: ${JSON.stringify(detail.keitaro)}`;
    throw new Error(message || `HTTP ${response.status}`);
  }
  return data;
}

async function init() {
  try {
    await api('/health');
    const info = await api('/keitaro/info');
    state.trackerUrl = info.tracker_url;
    const refs = await api('/references');
    state.refs = refs;
    setConnection(true, 'Keitaro подключен');
    fillSelect($('#offer-select'), refs.offers, 'Выбери оффер…');
    fillSelect($('#domain-select'), refs.domains, 'Выбери домен…');
    fillSelect($('#group-select'), refs.groups, 'Выбери группу…');
    fillSelect($('#source-select'), refs.traffic_sources, 'Выбери источник…');
    fillSelect($('#campaign-select'), refs.campaigns, 'Выбери кампанию…');
  } catch (error) {
    setConnection(false, 'Нет подключения к Keitaro');
    ['offer-select','domain-select','group-select','source-select','campaign-select'].forEach(id => {
      const select = document.getElementById(id);
      if (select) select.innerHTML = '<option value="">Не удалось загрузить</option>';
    });
    showToast(`Не удалось загрузить справочники: ${error.message}`, true);
  }
}

function setConnection(ok, label) {
  $('#connection-text').textContent = label;
  $('#sidebar-status').textContent = ok ? 'Подключено' : 'Нет соединения';
  $('#connection-dot').classList.toggle('connected', ok);
  document.querySelector('.note-dot').classList.toggle('connected', ok);
}

function setView(view) {
  const creator = view === 'creator';
  $('#creator-view').classList.toggle('hidden', !creator);
  $('#editor-view').classList.toggle('hidden', creator);
  $('#page-title').textContent = creator ? 'Создание кампании' : 'Редактор потоков';
  document.querySelectorAll('.nav-item').forEach(button => button.classList.toggle('active', button.dataset.view === view));
}

document.querySelectorAll('.nav-item').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));

$('#creator-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $('#create-button');
  const payload = Object.fromEntries(new FormData(form).entries());
  ['offer_id','domain_id','group_id','traffic_source_id'].forEach(key => payload[key] = Number(payload[key]));
  payload.country_code = payload.country_code.trim().toUpperCase();
  button.disabled = true;
  button.innerHTML = '<span class="button-spinner"></span> Создаём…';
  $('#creator-result').classList.add('hidden');
  try {
    const result = await api('/campaigns', {method:'POST', body:JSON.stringify(payload)});
    const domain = state.refs.domains.find(item => Number(item.id) === Number(payload.domain_id));
    const trackingUrl = domain?.name ? `https://${domain.name}/${result.alias}` : null;
    const box = $('#creator-result');
    box.className = 'result-panel success-result';
    box.innerHTML = `
      <div class="result-icon">✓</div>
      <div class="result-body">
        <b>Кампания создана</b>
        <p>${escapeHtml(result.name)} · ID ${result.campaign_id}</p>
        <div class="result-meta"><span>Alias: <code>${escapeHtml(result.alias || '')}</code></span><span>Поток Google: #${result.google_flow_id}</span><span>Поток оффера: #${result.offer_flow_id}</span></div>
        ${trackingUrl ? `<a href="${escapeHtml(trackingUrl)}" target="_blank" rel="noopener">Открыть ссылку кампании ↗</a>` : ''}
        <button type="button" class="text-action" id="show-created-campaign">Перейти к редактору кампании →</button>
      </div>`;
    box.classList.remove('hidden');
    $('#show-created-campaign').addEventListener('click', async () => {
      await reloadCampaigns(result.campaign_id);
      setView('editor');
      await loadCampaign(result.campaign_id);
    });
    showToast('Кампания успешно создана в Keitaro');
    await reloadCampaigns();
  } catch (error) {
    const box = $('#creator-result');
    box.className = 'result-panel error-result';
    box.innerHTML = `<div class="result-icon">!</div><div class="result-body"><b>Не удалось завершить создание</b><p>${escapeHtml(error.message)}</p><small>Проверь детали ошибки. Если кампания успела создаться до сбоя, её ID будет указан в ответе API.</small></div>`;
    box.classList.remove('hidden');
  } finally {
    button.disabled = false;
    button.innerHTML = 'Создать кампанию <span>→</span>';
  }
});

$('#campaign-select').addEventListener('change', async (event) => {
  const campaignId = Number(event.target.value) || null;
  if (!campaignId) {
    state.campaignId = null;
    state.streams = [];
    $('#campaign-summary').classList.add('hidden');
    setKeitaroLink(null);
    $('#editor-content').innerHTML = emptyState();
    return;
  }
  await loadCampaign(campaignId);
});

$('#refresh-campaigns').addEventListener('click', async () => {
  const selected = state.campaignId;
  await reloadCampaigns(selected);
  showToast('Список кампаний обновлён');
  if (selected) await loadCampaign(selected);
});

async function reloadCampaigns(selectId = null) {
  const campaigns = await api('/campaigns');
  state.refs.campaigns = campaigns;
  fillSelect($('#campaign-select'), campaigns, 'Выбери кампанию…');
  if (selectId) $('#campaign-select').value = String(selectId);
}

async function loadCampaign(campaignId) {
  state.campaignId = campaignId;
  $('#editor-content').innerHTML = '<div class="surface loading-state"><span class="button-spinner"></span> Загружаем потоки кампании…</div>';
  try {
    state.streams = await api(`/campaigns/${campaignId}/streams`);
    const campaign = state.refs.campaigns.find(item => Number(item.id) === campaignId);
    renderCampaignSummary(campaign, state.streams);
    setKeitaroLink(campaignId);
    renderAllStreams();
  } catch (error) {
    $('#editor-content').innerHTML = `<div class="surface empty-state error-state"><b>Не удалось загрузить потоки</b><span>${escapeHtml(error.message)}</span></div>`;
    showToast(`Ошибка загрузки кампании: ${error.message}`, true);
  }
}

function renderCampaignSummary(campaign, streams) {
  const summary = $('#campaign-summary');
  const name = entityName(campaign, `Кампания ${state.campaignId}`);
  summary.innerHTML = `<div><small>ВЫБРАННАЯ КАМПАНИЯ</small><b>${escapeHtml(name)}</b><span>ID ${state.campaignId}${campaign?.alias ? ` · ${escapeHtml(campaign.alias)}` : ''}</span></div><div class="summary-stat"><b>${streams.length}</b><span>потоков</span></div>`;
  summary.classList.remove('hidden');
}

function setKeitaroLink(campaignId) {
  const link = $('#open-in-keitaro');
  if (!campaignId || !state.trackerUrl) {
    link.href = '#';
    link.classList.add('disabled-link');
    return;
  }
  link.href = `${state.trackerUrl.replace(/\/$/, '')}/admin/#!/campaign.editor/${campaignId}`;
  link.classList.remove('disabled-link');
}

function renderAllStreams() {
  const content = $('#editor-content');
  if (!state.streams.length) {
    content.innerHTML = '<div class="surface empty-state"><b>В кампании пока нет потоков</b><span>Добавь потоки в Keitaro или выбери другую кампанию.</span></div>';
    return;
  }
  content.innerHTML = state.streams.map(stream => renderStreamCard(stream)).join('');
  content.querySelectorAll('[data-add-offer]').forEach(button => button.addEventListener('click', async () => {
    const streamId = Number(button.dataset.addOffer);
    const card = button.closest('.stream-card');
    const select = card.querySelector(`[data-offer-select="${streamId}"]`);
    const offerId = Number(select.value);
    if (!offerId) return showToast('Сначала выбери оффер');
    button.disabled = true;
    try {
      const updated = await api(`/campaigns/${state.campaignId}/streams/${streamId}/offers`, {method:'POST', body:JSON.stringify({offer_id:offerId})});
      replaceStream(updated);
      renderAllStreams();
      showToast('Оффер добавлен, доли пересчитаны');
    } catch (error) {
      showToast(`Не удалось добавить оффер: ${error.message}`, true);
      button.disabled = false;
    }
  }));
  content.querySelectorAll('[data-remove-offer]').forEach(button => button.addEventListener('click', async () => {
    const streamId = Number(button.dataset.streamId);
    const offerId = Number(button.dataset.removeOffer);
    const offer = findOffer(offerId);
    if (!confirm(`Удалить «${entityName(offer, `оффер ${offerId}`)}» из этого потока? Сам оффер в Keitaro останется.`)) return;
    button.disabled = true;
    try {
      const updated = await api(`/campaigns/${state.campaignId}/streams/${streamId}/offers/${offerId}`, {method:'DELETE'});
      replaceStream(updated);
      renderAllStreams();
      showToast('Оффер удалён, доли пересчитаны');
    } catch (error) {
      showToast(`Не удалось удалить оффер: ${error.message}`, true);
      button.disabled = false;
    }
  }));
}

function renderStreamCard(stream) {
  const offers = Array.isArray(stream.offers) ? stream.offers : [];
  const isOfferStream = stream.schema === 'landings' || offers.length > 0 || stream.type === 'default';
  const typeLabel = stream.type === 'default' ? 'DEFAULT' : stream.type === 'forced' ? 'FORCED' : 'REGULAR';
  const statusLabel = stream.state || 'active';
  const total = offers.reduce((sum, item) => sum + Number(item.share || 0), 0);
  const offerRows = offers.map((item, index) => {
    const offer = findOffer(item.offer_id);
    return `<tr>
      <td><div class="offer-name-cell"><span class="offer-order">${index + 1}</span><div><b>${escapeHtml(entityName(offer, `Оффер ${item.offer_id}`))}</b><small>ID ${item.offer_id}</small></div></div></td>
      <td class="share-value">${Number(item.share || 0)}%</td>
      <td class="action-cell"><button type="button" class="remove-button" data-stream-id="${stream.id}" data-remove-offer="${item.offer_id}" aria-label="Удалить оффер ${item.offer_id}">✕ <span>REMOVE</span></button></td>
    </tr>`;
  }).join('');
  const available = state.refs.offers.filter(offer => !['deleted','archived'].includes(String(offer.state || '').toLowerCase()) && !offers.some(existing => Number(existing.offer_id) === Number(offer.id)));
  const routeInfo = isOfferStream ? renderOfferRoute(offers, total) : renderRedirectRoute(stream);
  const offerEditor = isOfferStream ? `
    <div class="stream-table-wrap">
      ${offers.length ? `<table class="offer-table"><thead><tr><th>ОФФЕР</th><th>ДОЛЯ</th><th class="align-right">ДЕЙСТВИЯ</th></tr></thead><tbody>${offerRows}</tbody></table>
      <div class="share-footer"><span>Суммарная доля</span><b class="${total === 100 ? 'total-valid' : 'total-invalid'}">${total}%</b><small>${total === 100 ? 'Баланс корректен' : 'Проверь распределение долей'}</small></div>`
      : '<div class="no-offers">В потоке пока нет офферов. Добавь первый оффер ниже.</div>'}
      <div class="add-offer-row"><label class="field"><span>Добавить оффер в поток</span><select data-offer-select="${stream.id}"><option value="">Выбери оффер…</option>${available.map(offer => `<option value="${offer.id}">${escapeHtml(entityName(offer))} · ID ${offer.id}</option>`).join('')}</select></label><button type="button" class="add-button" data-add-offer="${stream.id}" ${available.length ? '' : 'disabled'}>＋ Добавить</button></div>
    </div>` : '';
  return `<article class="surface stream-card" data-stream-card="${stream.id}">
    <div class="stream-card-header">
      <div class="stream-heading"><span class="stream-grip">⠿</span><span class="active-indicator ${statusLabel === 'active' ? '' : 'inactive'}"></span><div><div class="stream-title-line"><h3>${escapeHtml(stream.name || `Flow ${stream.position || ''}`)}</h3><span class="stream-id">#${stream.id}</span></div><div class="stream-subtitle">${typeLabel} · ${escapeHtml(stream.schema || 'Схема не указана')} · ${offers.length} оффер${pluralRu(offers.length)}</div></div></div>
      <span class="stream-status ${statusLabel === 'active' ? 'active-status' : 'inactive-status'}">${escapeHtml(statusLabel)}</span>
    </div>
    <div class="stream-route">${routeInfo}</div>
    ${offerEditor}
  </article>`;
}

function renderRedirectRoute(stream) {
  const filters = Array.isArray(stream.filters) ? stream.filters : [];
  const route = typeof stream.action_payload === 'string' ? stream.action_payload : JSON.stringify(stream.action_payload || '');
  const filterText = filters.length ? filters.map(filter => {
    const value = Array.isArray(filter.payload) ? filter.payload.join(', ') : filter.payload;
    const country = filter.name === 'country' ? countryName(value) : value;
    return `${filter.mode === 'accept' ? 'принимать' : 'исключать'} «${country}»`;
  }).join('; ') : 'Фильтры не настроены';
  return `<div class="route-detail"><span class="route-tag">REDIRECT</span><b>${escapeHtml(route || 'URL перехода не указан')}</b><span class="filter-detail"><strong>Фильтры:</strong> ${escapeHtml(filterText)}</span></div>`;
}

function renderOfferRoute(offers, total) {
  return `<div class="route-detail"><span class="route-tag offer-route-tag">OFFERS</span><b>${offers.length} оффер${pluralRu(offers.length)} · ${total}% распределено</b><span class="filter-detail">Распределение трафика между офферами этого потока</span></div>`;
}

function countryName(value) {
  const code = String(value || '').trim().toUpperCase();
  if (!code || code.length !== 2) return code || '—';
  try { return new Intl.DisplayNames(['ru'], {type:'region'}).of(code) || code; }
  catch { return code; }
}

function pluralRu(number) {
  const mod10 = number % 10;
  const mod100 = number % 100;
  if (mod10 === 1 && mod100 !== 11) return '';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'а';
  return 'ов';
}

function findOffer(offerId) {
  return state.refs.offers.find(item => Number(item.id) === Number(offerId));
}

function replaceStream(updated) {
  const index = state.streams.findIndex(item => Number(item.id) === Number(updated.id));
  if (index >= 0) state.streams[index] = updated;
}

function emptyState() {
  return '<div class="surface empty-state"><div class="empty-symbol">⇄</div><b>Кампания не выбрана</b><span>Выбери кампанию выше, чтобы загрузить её потоки.</span></div>';
}

init();
