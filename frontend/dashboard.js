"use strict";
const $ = id => document.getElementById(id);
let snapshot = null, selectedId = null, loading = false, failed = false;
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time = value => new Date(value).getTime() === 0 ? 'never (no readings yet)' : new Date(value).toLocaleString();
const statusLabel = status => ({normal:'Healthy',alert:'Needs attention',unknown:'Unknown'}[status] || 'Unknown');
function metrics(member) {
  return member.metrics.map(m => `<div class="metric"><span>${escapeHTML(m.label)}</span><strong>${escapeHTML(m.value ?? '—')} <small>${escapeHTML(m.unit)}</small></strong></div>`).join('');
}
function render() {
  const {crew, alerts} = snapshot;
  $('summary').innerHTML = [['Crew members',crew.length],['Healthy',crew.filter(m => m.status === 'normal').length],['Needs attention',crew.filter(m => m.status === 'alert').length],['Unknown / stale',crew.filter(m => m.status === 'unknown' || m.stale).length]].map(([label,count]) => `<div class="stat"><span>${label}</span><strong>${count}</strong></div>`).join('');
  const filtered = crew.filter(m => $('filter').value === 'all' || m.status === $('filter').value);
  $('crew').innerHTML = filtered.map(m => `<article class="card ${escapeHTML(m.status)}"><div class="card-top"><span class="avatar">${escapeHTML(m.name.split(' ').map(n => n[0]).join(''))}</span><span class="badge">${statusLabel(m.status)}</span></div><div><h3>${escapeHTML(m.name)}</h3><p class="role">${escapeHTML(m.role)} · ${escapeHTML(m.id)}</p></div>${metrics(m)}<p class="timestamp">${m.stale ? 'STALE · ' : ''}Observed ${escapeHTML(time(m.observed_at))}</p><button data-member="${escapeHTML(m.id)}">View health details ↗</button></article>`).join('') || '<p class="empty">No crew members in this view.</p>';
  $('alert-count').textContent = `${alerts.length} exceptions`;
  $('alerts').innerHTML = alerts.map(a => `<div class="alert-row"><div><strong>${escapeHTML(a.crew_name)}</strong><p>${escapeHTML(a.message)}</p><span class="timestamp">Observed ${escapeHTML(time(a.observed_at))}</span></div><button data-member="${escapeHTML(a.crew_id)}">Review member ↗</button></div>`).join('') || '<p class="empty">No out-of-range readings in this snapshot.</p>';
  if (selectedId) renderDetail();
}
function renderDetail() {
  const member = snapshot.crew.find(m => m.id === selectedId);
  if (!member) { $('detail-content').innerHTML = '<p>Crew member is no longer available.</p>'; return; }
  $('detail-content').innerHTML = `<h1 id="detail-title">${escapeHTML(member.name)}</h1><p class="muted">${escapeHTML(member.role)} · ${escapeHTML(member.id)} · ${statusLabel(member.status)}</p><p class="timestamp">Observed ${escapeHTML(time(member.observed_at))}${member.stale ? ' · STALE DATA' : ''}${failed ? ' · Refresh failed; showing last snapshot' : ''}</p>${metrics(member)}${member.metrics.map(m => {
    const values = m.history;
    const low = Math.min(...values), high = Math.max(...values);
    const points = values.map((v,i) => `${10+i*480/Math.max(values.length-1,1)},${55-(v-low)*40/Math.max(high-low,1)}`).join(' ');
    return `<div class="history"><p>${escapeHTML(m.label)} · Recent stored readings (oldest → newest)</p>${values.length ? `<svg viewBox="0 0 500 70" role="img" aria-label="${escapeHTML(m.label)} readings: ${escapeHTML(values.join(', '))}"><polyline points="${points}" fill="none" stroke="#73c8e2" stroke-width="2"/></svg>` : '<p>No history available.</p>'}<p>Configured demo range: ${escapeHTML(m.lower)}–${escapeHTML(m.upper)} ${escapeHTML(m.unit)}</p></div>`;
  }).join('')}<h2>Manual measurements</h2><p class="muted">Latest recorded values; no manual alert rules are configured.</p>${(member.manual_measurements || []).map(m => `<div class="history"><p>${escapeHTML(m.label)}</p><strong>${escapeHTML(m.value)} ${escapeHTML(m.unit || '')}</strong><p>Measured ${escapeHTML(time(m.measured_at))}</p></div>`).join('') || '<p class="muted">No manual measurements recorded.</p>'}<h2>Model predictions</h2>${(member.predictions || []).map(p => `<div class="history"><p>${escapeHTML(p.label)} · ${escapeHTML(p.model_version)}</p><p>Score: ${escapeHTML(Math.round(p.score * 100))}% · Alert threshold: ${escapeHTML(Math.round(p.threshold * 100))}%</p><p>Observed ${escapeHTML(time(p.observed_at))}</p></div>`).join('') || '<p class="muted">No predictions available.</p>'}<h2>Member alerts</h2>${snapshot.alerts.filter(a => a.crew_id === member.id).map(a => `<p class="warning">${escapeHTML(a.message)}</p>`).join('') || '<p class="muted">No out-of-range readings.</p>'}`;
}
async function refresh() {
  if (loading) return;
  loading = true; $('refresh').disabled = true; $('data-source').disabled = true;
  try {
    const endpoint = $('data-source').value === 'demo' ? '/api/dashboard?demo=true' : '/api/dashboard';
    const response = await fetch(endpoint, {cache:'no-store', signal:AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    snapshot = await response.json(); failed = false;
    render();
    document.querySelector('.demo').textContent = snapshot.mode === 'demo'
      ? 'SAMPLE PREVIEW · Synthetic crew readings and model scores. Your saved database is unchanged.'
      : 'SAVED READINGS · Database values. Manual entries appear in member details; missing model readings remain unknown.';
    $('connection').textContent = snapshot.mode === 'live'
      ? `Live data from the database · Updated ${time(snapshot.generated_at)}`
      : `Demo replay as of ${time(snapshot.demo_as_of)} · Loaded from demo files · No live sensor connection`;
  } catch (error) {
    failed = true;
    $('connection').textContent = `Unable to refresh data. ${snapshot ? 'Showing last retrieved snapshot; readings may be outdated.' : 'No crew data available.'} Use Refresh data to retry.`;
    if (selectedId && snapshot) renderDetail();
  } finally { loading = false; $('refresh').disabled = false; $('data-source').disabled = false; }
}
$('data-source').value = new URLSearchParams(location.search).get('source') === 'demo' ? 'demo' : 'live';
$('data-source').addEventListener('change', () => { if (!loading) refresh(); });
$('refresh').addEventListener('click', refresh);
$('filter').addEventListener('change', () => snapshot && render());
document.addEventListener('click', event => {
  const button = event.target.closest('[data-member]');
  if (button) { selectedId = button.dataset.member; renderDetail(); if (!$('detail').open) $('detail').showModal(); }
});
$('close').addEventListener('click', () => $('detail').close());
$('detail').addEventListener('close', () => { selectedId = null; });
refresh();
setInterval(refresh, 15000);
