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
  $('summary').innerHTML = [['Within range', 'normal'], ['Needs attention', 'alert'], ['Unknown', 'unknown']].map(([label,status]) => `<div class="stat ${status}"><img src="/ui-assets/status-placeholder.svg" alt=""><span>${label}</span><strong>${crew.filter(m => m.status === status).length}</strong></div>`).join('');
  const filtered = crew.filter(m => $('filter').value === 'all' || m.status === $('filter').value);
  $('crew').innerHTML = filtered.map(m => {
    const heart = m.metrics.find(metric => metric.key === 'heart_rate');
    const respiration = m.metrics.find(metric => metric.key === 'respiratory_rate');
    return `<article class="card ${escapeHTML(m.status)}"><img class="crew-portrait" src="/ui-assets/portrait-placeholder.svg" alt="Portrait placeholder for ${escapeHTML(m.name)}"><span class="portrait-initials" aria-hidden="true">${escapeHTML(m.name.split(' ').map(n => n[0]).join(''))}</span><div class="card-content"><h3>${escapeHTML(m.name)}</h3><p class="role">${escapeHTML(m.role)} · ${escapeHTML(m.id)}</p><span class="badge">${statusLabel(m.status)}</span><div class="metric"><span>Heart Rate</span><strong>${escapeHTML(heart?.value ?? '—')} <small>BPM</small></strong></div><div class="metric"><span>Respiratory Rate</span><strong>${escapeHTML(respiration?.value ?? '—')} <small>br/min</small></strong></div><p class="timestamp">Observed ${escapeHTML(time(m.observed_at))}</p><button data-member="${escapeHTML(m.id)}">Check status ↗</button></div></article>`;
  }).join('') || '<p class="empty">No crew members in this view.</p>';
  $('alert-count').textContent = `${alerts.length} exceptions`;
  $('alerts').innerHTML = alerts.map(a => `<div class="alert-row"><div><strong>${escapeHTML(a.crew_name)}</strong><p>${escapeHTML(a.message)}</p><span class="timestamp">Observed ${escapeHTML(time(a.observed_at))}</span></div><button data-member="${escapeHTML(a.crew_id)}">Review member ↗</button></div>`).join('') || '<p class="empty">No out-of-range readings in this snapshot.</p>';
  if (selectedId) renderDetail();
}
function trendChart(metric) {
  const values = metric.history.filter(Number.isFinite);
  if (!values.length) return '<p class="muted">No stored readings available.</p>';
  const span = Math.max(metric.upper - metric.lower, 1);
  const low = Math.min(metric.lower - span * .15, ...values);
  const high = Math.max(metric.upper + span * .15, ...values);
  const y = value => 130 - (value - low) * 110 / (high - low);
  const x = index => 45 + index * 430 / Math.max(values.length - 1, 1);
  const points = values.map((v,i) => `${x(i)},${y(v)}`).join(' ');
  return `<svg class="vital-chart" viewBox="0 0 500 165" role="img" aria-label="${escapeHTML(metric.label)}: ${escapeHTML(values.join(', '))} ${escapeHTML(metric.unit)}. Configured range ${metric.lower} to ${metric.upper}."><rect x="45" y="20" width="430" height="110" fill="#fcdada"/><rect x="45" y="${y(metric.upper)}" width="430" height="${y(metric.lower)-y(metric.upper)}" fill="#c9ffdc"/><path d="M45 ${y(metric.upper)}H475 M45 ${y(metric.lower)}H475" stroke="#8ba5c8" stroke-dasharray="5 4"/><path d="M45 20V130H475" fill="none" stroke="#66758b"/><text x="4" y="${y(metric.upper)+4}">${escapeHTML(metric.upper)}</text><text x="4" y="${y(metric.lower)+4}">${escapeHTML(metric.lower)}</text><polyline points="${points}" fill="none" stroke="#0472d3" stroke-width="3"/>${values.map((v,i) => `<circle cx="${x(i)}" cy="${y(v)}" r="3" fill="#0472d3"/>`).join('')}<text x="45" y="153">Oldest</text><text x="425" y="153">Latest</text></svg>`;
}
function renderDetail() {
  const member = snapshot.crew.find(m => m.id === selectedId);
  if (!member) { $('detail-content').innerHTML = '<p>Crew member is no longer available.</p>'; return; }
  const alerts = snapshot.alerts.filter(a => a.crew_id === member.id);
  const vitals = [
    member.metrics.find(m => m.key === 'heart_rate') || {label:'Heart Rate', value:null, unit:'bpm', history:[]},
    member.metrics.find(m => m.key === 'respiratory_rate') || {label:'Respiratory Rate', value:null, unit:'br/min', history:[]}
  ];
  const readings = member.manual_measurements || [];
  $('detail-content').innerHTML = `<header class="profile-header"><strong>Bionotate</strong><h1 id="detail-title">Crew Profile</h1><span class="timestamp">Updated ${escapeHTML(time(snapshot.generated_at))}</span></header>
  ${failed ? '<p role="status">Refresh failed; showing last retrieved snapshot.</p>' : ''}
  <div class="profile-grid">
    <section class="body-panel" aria-label="Crew illustration and latest vitals"><span class="body-caption">${escapeHTML(member.name)}</span><img class="body-placeholder" src="/ui-assets/portrait-placeholder.svg" alt="Body illustration placeholder"><div class="body-vitals">${vitals.map(m => `<div class="vital-callout"><span>${escapeHTML(m.label)}</span><strong>${escapeHTML(m.value ?? '—')} <small>${escapeHTML(m.unit)}</small></strong></div>`).join('')}</div></section>
    <div class="profile-side"><section class="profile-panel identity-panel ${escapeHTML(member.status)}"><div class="section-heading"><h2>${escapeHTML(member.name)}</h2><span class="badge">${statusLabel(member.status)}</span></div><p>${escapeHTML(member.role)} · ${escapeHTML(member.id)}</p><dl class="profile-facts">${['Age','Blood type','Height','Weight'].map(label => `<div><dt>${label}</dt><dd>—</dd></div>`).join('')}</dl><p class="timestamp">Observed ${escapeHTML(time(member.observed_at))}</p></section>
    <section class="profile-panel status-summary"><h2><img src="/ui-assets/status-placeholder.svg" alt=""> Status Summary</h2><ul>${alerts.map(a => `<li class="summary-alert">${escapeHTML(a.message)}</li>`).join('') || `<li>${member.status === 'unknown' ? 'Insufficient readings to determine status.' : 'No readings outside configured ranges.'}</li>`}</ul></section></div>
    <section class="profile-panel trends-panel"><div class="section-heading"><h2>Key Vitals (Trend)</h2><div class="report-actions"><button type="button" data-profile-refresh>↻ Refresh data</button><a class="video-action" href="/upload">Video analysis ↗</a></div></div>
    <div class="profile-data-grid"><div>${vitals.map(m => `<div class="vital-trend"><div><h3>${escapeHTML(m.label)}</h3><strong>${escapeHTML(m.value ?? '—')} <small>${escapeHTML(m.unit)}</small></strong></div><div>${trendChart(m)}</div></div>`).join('')}<p class="muted">Shaded green: configured range. Readings shown oldest to newest.</p></div>
    <section class="profile-actions"><h2>Recommended Actions</h2><p class="muted">Recommendations are not configured yet.</p><a class="profile-action-link" href="/measurements">Add manual measurement ↗</a><details><summary>Expand saved measurements</summary>${readings.map(m => `<div class="saved-reading"><strong>${escapeHTML(m.label)}</strong><span>${escapeHTML(m.value)} ${escapeHTML(m.unit || '')}</span><small>Measured ${escapeHTML(time(m.measured_at))}</small></div>`).join('') || '<p>No manual measurements recorded.</p>'}<p class="muted">Manual readings do not affect health status yet.</p></details></section></div></section></div>`;
}
async function refresh() {
  if (loading) return;
  loading = true; $('refresh').disabled = true;
  try {
    const response = await fetch('/api/dashboard', {cache:'no-store', signal:AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    snapshot = await response.json(); failed = false;
    render();
    $('connection').textContent = snapshot.mode === 'live'
      ? `Database · Updated ${time(snapshot.generated_at)}`
      : `Demo replay as of ${time(snapshot.demo_as_of)} · Loaded from demo files · No live sensor connection`;
  } catch (error) {
    failed = true;
    $('connection').textContent = `Unable to refresh data. ${snapshot ? 'Showing last retrieved snapshot; readings may be outdated.' : 'No crew data available.'} Use Refresh data to retry.`;
    if (selectedId && snapshot) renderDetail();
  } finally { loading = false; $('refresh').disabled = false; }
}
$('refresh').addEventListener('click', refresh);
$('filter').addEventListener('change', () => snapshot && render());
document.addEventListener('click', event => {
  if (event.target.closest('[data-profile-refresh]')) { refresh(); return; }
  const button = event.target.closest('[data-member]');
  if (button) { selectedId = button.dataset.member; renderDetail(); if (!$('detail').open) $('detail').showModal(); }
});
$('close').addEventListener('click', () => $('detail').close());
$('detail').addEventListener('close', () => { selectedId = null; });
refresh();
setInterval(refresh, 15000);
