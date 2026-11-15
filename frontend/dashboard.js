"use strict";
const $ = id => document.getElementById(id);
let snapshot = null, selectedId = null, loading = false, failed = false;
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const never = value => new Date(value).getTime() === 0;
const time = value => {
  if (!value || !Number.isFinite(new Date(value).getTime())) return '—';
  if (never(value)) return 'never (no readings yet)';
  return new Date(value).toISOString().slice(0,19).replace(/-/g, '').replace('T', ' ');
};
const day = value => time(value).split(' ')[0];
const clock = value => time(value).split(' ')[1] || '';
const observed = value => time(value);
const statusLabel = status => ({normal:'Within range', alert:'Needs attention', warning:'Check required', unknown:'Check required'}[status] || 'Check required');

// A vital sign (heart or respiratory rate) outside its configured range is a warning (yellow).
// Other alerts, such as a model score that keeps rising, are red.
function alertSeverity(alert, member) {
  if (alert.severity === 'warning' || alert.severity === 'alert') return alert.severity;
  const m = member?.metrics.find(x => x.key === alert.metric);
  return m && m.lower != null && m.upper != null ? 'warning' : 'alert';
}
function classify(data) {
  for (const a of data.alerts) a.severity = alertSeverity(a, data.crew.find(m => m.id === a.crew_id));
  for (const m of data.crew) {
    const own = data.alerts.filter(a => a.crew_id === m.id);
    m.display = m.status !== 'alert' ? m.status : own.length && own.every(a => a.severity === 'warning') ? 'warning' : 'alert';
  }
}

// Line icons drawn to match the Figma design (24px grid, inherit text colour).
const ICON_PATHS = {
  heart: '<path d="M12 20.5s-7.6-4.6-9.3-9.4C1.5 7.6 3.7 4.5 7 4.5c2 0 3.6 1.1 5 3 1.4-1.9 3-3 5-3 3.3 0 5.5 3.1 4.3 6.6-1.7 4.8-9.3 9.4-9.3 9.4Z"/>',
  lungs: '<path d="M12 3v8.5m0 0c-.8 1-2 1.6-3 1.8m3-1.8c.8 1 2 1.6 3 1.8"/><path d="M8.3 6.5C5.4 6.5 3 11.6 3 16.3 3 18.9 4.4 20 6 20c1.7 0 3-1.2 3-3.2V8.2c0-1-.3-1.7-.7-1.7ZM15.7 6.5c2.9 0 5.3 5.1 5.3 9.8 0 2.6-1.4 3.7-3 3.7-1.7 0-3-1.2-3-3.2V8.2c0-1 .3-1.7.7-1.7Z"/>',
  observed: '<path d="M9 3.5h6v3H9z"/><path d="M15 5h2.5A1.5 1.5 0 0 1 19 6.5V11M9 5H6.5A1.5 1.5 0 0 0 5 6.5v12A1.5 1.5 0 0 0 6.5 20H11M8.5 10.5h6M8.5 14h3"/><circle cx="17" cy="17" r="4"/><path d="M17 15.3V17l1.2 1"/>',
  wave: '<path d="M3 12h3l2-5 3.5 10L14 9l1.5 3H21"/>',
  warning: '<path d="M12 3.5 2.5 20.5h19L12 3.5Z"/><path d="M12 10v5m0 2.8h.01"/>',
  refresh: '<path d="M19.5 10A7.8 7.8 0 0 0 5.6 7.2M4.5 4v4h4M4.5 14a7.8 7.8 0 0 0 13.9 2.8m1.1 3.2v-4h-4"/>',
  play: '<path d="M7 4.5 19.5 12 7 19.5Z"/>',
  external: '<path d="M7 17 17 7M8.5 7H17v8.5"/>',
  up: '<path d="M12 18.5v-13M6.5 11 12 5.5l5.5 5.5"/>',
  down: '<path d="M12 5.5v13M6.5 13l5.5 5.5 5.5-5.5"/>',
  check: '<path d="m5.5 12.5 4 4 9-9"/>',
  calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4m8-4v4M8 14h1m3 0h1m3 0h1M8 17h1m3 0h1"/>',
  drop: '<path d="M12 3.5S6 10.2 6 14.3a6 6 0 0 0 12 0c0-4.1-6-10.8-6-10.8Z"/>',
  ruler: '<path d="M3.5 16.5 16.5 3.5l4 4-13 13Z"/><path d="m7.5 12.5 1.8 1.8m1.2-4.8 1.8 1.8m1.2-4.8 1.8 1.8"/>',
  weight: '<path d="M6.5 9h11l2.5 11H4L6.5 9Z"/><path d="M9.5 9a2.5 2.5 0 1 1 5 0"/>',
  clipboard: '<path d="M9 3.5h6v3H9z"/><path d="M15 5h2.5A1.5 1.5 0 0 1 19 6.5v12a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 18.5v-12A1.5 1.5 0 0 1 6.5 5H9M9 11h6m-6 4h6"/>',
  trend: '<rect x="3" y="3.5" width="18" height="17" rx="2"/><path d="m6.5 15 3.5-4 3 2.5 4.5-5.5"/>',
  medkit: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V4.5h6V7m-3 4v5.5M9.2 13.7h5.6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
};
const icon = (name, cls = '') => `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name]}</svg>`;
const metricIcon = key => key === 'heart_rate' ? 'heart' : key === 'respiratory_rate' ? 'lungs' : 'wave';

// Crew photos (public-domain NASA images, see data/ui/crew/CREDITS.md):
// data/ui/crew/<crew id>.jpg is the headshot, <crew id>-body.jpg the full-body photo.
const PLACEHOLDER = '/ui-assets/portrait-placeholder.svg';
const portrait = id => `/ui-assets/crew/${encodeURIComponent(id)}.jpg`;
const photoFallback = `onerror="this.onerror=null;this.src='${PLACEHOLDER}';this.parentElement.classList.add('no-photo')"`;
const BODY_IMAGES = Object.fromEntries(['A-01', 'A-02', 'A-03', 'A-04'].map(id => [id, `/ui-assets/crew/${id}-body.jpg`]));

const vital = (member, key, label, unit) => member.metrics.find(m => m.key === key) || {key, label, value:null, unit, history:[]};
const outOfRange = m => m.value != null && m.lower != null && m.upper != null && (m.value > m.upper || m.value < m.lower);

function render() {
  const {crew, alerts} = snapshot;
  $('summary').innerHTML = [['normal', 'green'], ['unknown', 'yellow'], ['alert', 'red']].map(([status, face]) =>
    `<div class="stat ${status}"><img src="/ui-assets/status-${face}.png" alt=""><span>${statusLabel(status)}:</span><strong>${crew.filter(m => status === 'unknown' ? ['unknown','warning'].includes(m.display) : m.display === status).length}</strong></div>`).join('');
  const filtered = crew.filter(m => $('filter').value === 'all' || ($('filter').value === 'unknown' ? ['unknown','warning'].includes(m.display) : m.display === $('filter').value));
  $('crew').innerHTML = filtered.map(m => {
    const rows = [vital(m, 'heart_rate', 'Heart Rate', 'bpm'), vital(m, 'respiratory_rate', 'Respiratory Rate', 'br/min')];
    const initials = m.name.split(' ').map(n => n[0]).join('');
    return `<article class="card ${escapeHTML(m.display)}">
      <img class="crew-portrait" src="${portrait(m.id)}" alt="Photo of ${escapeHTML(m.name)}" ${photoFallback}>
      <span class="portrait-initials" aria-hidden="true">${escapeHTML(initials)}</span>
      <header class="card-title"><h3>${escapeHTML(m.name)}</h3><p class="role">${escapeHTML(m.role)}<span>${escapeHTML(m.id)}</span></p></header>
      <div class="card-content">
        <span class="badge">${statusLabel(m.display)}</span>
        ${rows.map(r => `<div class="metric">${icon(metricIcon(r.key))}<span>${r.key === 'heart_rate' ? 'Heart Rate' : 'Respiratory Rate'}</span><strong>${escapeHTML(r.value ?? '—')} <small>${r.key === 'heart_rate' ? 'BPM' : 'br/min'}</small></strong></div>`).join('')}
        <div class="metric observed">${icon('observed')}<span>observed ${escapeHTML(observed(m.observed_at))}</span></div>
        <button data-member="${escapeHTML(m.id)}">Check Status</button>
      </div></article>`;
  }).join('') || '<p class="empty">No crew members in this view.</p>';
  $('alert-count').textContent = alerts.length ? `${alerts.length} issues` : '';
  $('alerts').innerHTML = alerts.map(a => `<button class="alert-row ${escapeHTML(a.severity)}" data-member="${escapeHTML(a.crew_id)}" aria-label="Open profile of ${escapeHTML(a.crew_name)}: ${escapeHTML(a.message)}">
      <strong>${escapeHTML(a.crew_name)}</strong>${icon(metricIcon(a.metric))}<span class="alert-message">${escapeHTML(a.message)}</span>
      <span class="alert-when"><span>Observed ${escapeHTML(day(a.observed_at))}</span><span>${escapeHTML(clock(a.observed_at))}</span></span></button>`).join('')
    || '<p class="empty">No out-of-range readings in this snapshot.</p>';
  if (selectedId) renderDetail();
}

function trendArrow(m) {
  if (m.value == null || m.lower == null) return '';
  if (m.value > m.upper) return `<span class="trend-flag high" title="Above configured range">${icon('up')}</span>`;
  if (m.value < m.lower) return `<span class="trend-flag low" title="Below configured range">${icon('down')}</span>`;
  return `<span class="trend-flag ok" title="Within configured range">${icon('check')}</span>`;
}

const storedTrendCache = new Map();
const storedTrendPending = new Set();
async function loadStoredTrends(id) {
  if (storedTrendPending.has(id) || Date.now() - (storedTrendCache.get(id)?.at || 0) < 15000) return;
  storedTrendPending.add(id);
  try {
    const response = await fetch(`/api/measurements/trends?astronaut_id=${encodeURIComponent(id)}`, {signal:AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error('Unable to load measurements');
    storedTrendCache.set(id, {at:Date.now(), data:await response.json()});
  } catch (_) { storedTrendCache.set(id, {at:Date.now(), error:true}); }
  finally { storedTrendPending.delete(id); if (selectedId === id) renderDetail(); }
}
const storedTrendAxis = new Map();
const metricNumber = value => Number(value).toLocaleString(undefined, {maximumFractionDigits:2});
function metricGroups(series) {
  const groups = new Map();
  for (const item of series) {
    const unit = item.unit === 'br/min' ? 'breaths/min' : item.unit || '';
    const key = `${item.metric}::${unit}`;
    const group = groups.get(key) || {key, metric:item.metric, label:item.label, unit, axes:new Map()};
    const points = group.axes.get(item.axis) || [];
    points.push(...item.points);
    group.axes.set(item.axis, points);
    groups.set(key, group);
  }
  for (const group of groups.values()) {
    for (const [axis, raw] of group.axes) {
      const points = axis === 'mission_phase'
        ? [...raw.reduce((map, p) => {
            const old = map.get(p.phase_index);
            if (!old || (p.imported_at || '') > (old.imported_at || '') || ((p.imported_at || '') === (old.imported_at || '') && p.id > old.id)) map.set(p.phase_index, p);
            return map;
          }, new Map()).values()]
        : [...new Map(raw.map(p => [p.id, p])).values()];
      points.sort((a,b) => axis === 'mission_phase' ? a.phase_index-b.phase_index : Date.parse(a.measured_at)-Date.parse(b.measured_at) || a.id-b.id);
      group.axes.set(axis, points);
    }
  }
  return [...groups.values()].sort((a,b) => ({hr_bpm:0,respi_rate:1}[a.metric] ?? 2)-({hr_bpm:0,respi_rate:1}[b.metric] ?? 2) || a.label.localeCompare(b.label));
}
function storedMetricChart(series, range = {}) {
  const points = series.points.map(p => ({...p, x:series.axis === 'mission_phase' ? p.phase_index : Date.parse(p.measured_at)})).filter(p => Number.isFinite(p.x) && Number.isFinite(p.value)).slice(-10).map((point, position) => ({...point, position}));
  if (!points.length) return '<p>No observations available.</p>';
  const ys = points.map(p => p.value);
  const ranged = Number.isFinite(range.lower) && Number.isFinite(range.upper);
  const low = Math.min(...ys, ...(ranged ? [range.lower] : [])), high = Math.max(...ys, ...(ranged ? [range.upper] : []));
  const pad = Math.max((high-low)*.2, Math.abs(low)*.01, .01);
  const x = position => points.length === 1 ? 260 : 60+position/(points.length-1)*400;
  const y = value => 110-(value-low+pad)/(high-low+2*pad)*90;
  const label = p => series.axis === 'mission_phase' ? p.mission_phase : time(p.measured_at);
  const segments = [];
  for (const point of points) {
    const last = segments[segments.length-1];
    if (last && (series.axis !== 'mission_phase' || point.x-last[last.length-1].x === 1)) last.push(point);
    else segments.push([point]);
  }
  return `<svg class="vital-chart stored-metric-chart" viewBox="0 0 500 135" role="img" aria-label="${escapeHTML(series.label)} readings in ${escapeHTML(series.unit || '')}">
    ${ranged ? `<rect x="60" y="15" width="400" height="105" fill="#fcdada"/><rect x="60" y="${y(range.upper)}" width="400" height="${y(range.lower)-y(range.upper)}" fill="#d3f8df"/><path d="M60 ${y(range.upper)}H460" stroke="#c73535"/><path d="M60 ${y(range.lower)}H460" stroke="#f0a020" stroke-dasharray="6 4"/>` : ''}
    <path d="M60 15V120H460" fill="none" stroke="#334e7c"/>
    <text x="52" y="${y(ranged ? range.upper : high)+4}" text-anchor="end">${metricNumber(ranged ? range.upper : high)}</text><text x="52" y="${y(ranged ? range.lower : low)+4}" text-anchor="end">${metricNumber(ranged ? range.lower : low)}</text>
    ${segments.map(segment => `<polyline points="${segment.map(p => `${x(p.position)},${y(p.value)}`).join(' ')}" fill="none" stroke="#ef3b3b" stroke-width="2.5"/>`).join('')}
    ${points.map(point => `<circle cx="${x(point.position)}" cy="${y(point.value)}" r="4.5" fill="#ef3b3b"><title>${escapeHTML(label(point))}: ${point.value} ${escapeHTML(series.unit || '')}</title></circle>`).join('')}</svg>
    <div class="chart-time-bounds"><span>${escapeHTML(label(points[0]))}</span><span>${points.length > 1 ? escapeHTML(label(points[points.length-1])) : ''}</span></div>`;
}
function storedTrends(id, vitals = []) {
  const cached = storedTrendCache.get(id);
  if (!cached) return '<p role="status">Loading measurements…</p>';
  if (cached.error) return '<p role="status">Unable to load metric trends. Use Refresh data to retry.</p>';
  const groups = metricGroups(cached.data.series);
  if (!groups.length) return '<p>No measurements recorded.</p>';
  return groups.map(group => {
    const stateKey = `${id}:${group.key}`;
    const axis = group.axes.has(storedTrendAxis.get(stateKey)) ? storedTrendAxis.get(stateKey) : group.axes.has('timestamp') ? 'timestamp' : 'mission_phase';
    const points = group.axes.get(axis);
    const range = vitals.find(m => m.key === ({hr_bpm:'heart_rate',respi_rate:'respiratory_rate'}[group.metric])) || {};
    const displayLabel = range.label || group.label;
    return `<div class="vital-trend stored-metric"><div><h3>${escapeHTML(displayLabel)}</h3><strong>${metricNumber(points[points.length-1].value)} <small>${escapeHTML(group.unit)}</small></strong>
      ${group.axes.size > 1 ? `<label class="metric-axis-label">View <select data-metric-axis="${escapeHTML(stateKey)}" aria-label="Time axis for ${escapeHTML(displayLabel)}">${[...group.axes.keys()].map(key => `<option value="${key}" ${axis === key ? 'selected' : ''}>${key === 'timestamp' ? 'Recorded time' : 'Mission phases'}</option>`).join('')}</select></label>` : ''}
      </div><div>${storedMetricChart({...group, axis, points}, range)}<details><summary>Measurement values</summary><table><thead><tr><th>${axis === 'timestamp' ? 'Timestamp (UTC)' : 'Mission phase'}</th><th>${escapeHTML(group.unit || 'Value')}</th></tr></thead><tbody>${points.map(point => `<tr><td>${escapeHTML(axis === 'mission_phase' ? point.mission_phase : time(point.measured_at))}</td><td>${metricNumber(point.value)}</td></tr>`).join('')}</tbody></table></details></div></div>`;
  }).join('') + '<p class="muted">Latest 10 readings, equally spaced by observation order. Timestamps are UTC. Green bands show configured ranges.</p>';
}

function renderDetail() {
  const member = snapshot.crew.find(m => m.id === selectedId);
  if (!member) { $('detail-content').innerHTML = '<p>Crew member is no longer available.</p>'; return; }
  loadStoredTrends(member.id);
  const alerts = member.issues || snapshot.alerts.filter(a => a.crew_id === member.id);
  const vitals = [vital(member, 'heart_rate', 'Heart Rate', 'bpm'), vital(member, 'respiratory_rate', 'Respiratory Rate', 'br/min')];
  const readings = member.manual_measurements || [];
  const bodySrc = BODY_IMAGES[member.id];
  const info = profiles[member.id] || {};
  const facts = [['calendar','Age', info.age], ['drop','Blood Type', info.blood_type],
                 ['ruler','Height', info.height_m != null ? info.height_m.toFixed(2) + 'm' : null],
                 ['weight','Weight', info.weight_kg != null ? info.weight_kg + 'kg' : null]];
  const summary = alerts.map(a => `<li class="${a.severity === 'warning' ? 'dot-yellow' : 'dot-red'}">${escapeHTML(a.message)}</li>`).join('')
    || `<li class="${member.status === 'unknown' ? 'dot-yellow' : 'dot-green'}">${member.status === 'unknown' ? 'Insufficient readings to determine status.' : 'No readings outside configured ranges.'}</li>`;
  $('detail-content').innerHTML = `<header class="profile-header"><strong>Bionotate</strong><h1 id="detail-title">Crew Profile</h1><span class="timestamp">Updated ${escapeHTML(time(snapshot.generated_at))}</span></header>
  ${failed ? '<p role="status">Refresh failed; showing last retrieved snapshot.</p>' : ''}
  <div class="profile-grid">
    <section class="body-panel" aria-label="Crew illustration and latest vitals">
      <span class="body-caption">${escapeHTML(member.name)}</span>
      <div class="body-figure ${bodySrc ? 'full-body' : 'headshot'}"><img src="${bodySrc || portrait(member.id)}" alt="Picture of ${escapeHTML(member.name)}" ${photoFallback}></div>
      <div class="body-vitals">${vitals.map(m => `<div class="vital-callout ${outOfRange(m) ? 'out' : ''}"><span>${icon(metricIcon(m.key))}${m.key === 'heart_rate' ? 'Heart Rate' : 'Respiratory Rate'}</span><strong>${escapeHTML(m.value ?? '—')} <small>${escapeHTML(m.unit)}</small>${trendArrow(m)}</strong></div>`).join('')}</div>
    </section>
    <div class="profile-side">
      <section class="profile-panel identity-panel ${escapeHTML(member.display)}">
        <div class="identity-top"><div><h2>${escapeHTML(member.name)}</h2><p>${escapeHTML(member.role)}<span>${escapeHTML(member.id)}</span></p></div><span class="badge">${statusLabel(member.display)}</span></div>
        <dl class="profile-facts">${facts.map(([ic, label, value]) => `<div>${icon(ic)}<span><dt>${label}</dt><dd>${escapeHTML(value ?? '—')}</dd></span></div>`).join('')}</dl>
        <p class="timestamp">Observed ${escapeHTML(observed(member.observed_at))}</p>
      </section>
      <section class="profile-panel status-summary"><h2>${icon('clipboard')} Status Summary</h2><ul>${summary}</ul></section>
    </div>
    <section class="profile-panel trends-panel">
      <div class="section-heading"><h2>${icon('trend')} Key Vitals (Trend)</h2><div class="report-actions"><button type="button" class="refresh-action" data-profile-refresh>${icon('refresh')} Refresh data</button><a class="video-action" href="/upload">${icon('play')} Video analysis ${icon('external')}</a></div></div>
      <div class="profile-data-grid">
        <div>${storedTrends(member.id, vitals)}</div>
        <section class="profile-actions"><h2>${icon('medkit')} Recommended Actions</h2>
          <p class="action-row muted">Recommendations are not configured yet.</p>
          <a class="action-row action-link" href="/measurements">${icon('plus')} Add manual measurement ${icon('external')}</a>
          <h3>Saved measurements</h3>
          ${readings.map(m => `<div class="action-row saved-reading"><strong>${escapeHTML(m.label)}</strong><span>${escapeHTML(m.value)} ${escapeHTML(m.unit || '')}</span><small>Measured ${escapeHTML(time(m.measured_at))}</small></div>`).join('') || '<p class="action-row muted">No manual measurements recorded.</p>'}
          <p class="muted">Manual readings are stored in measurements.</p>
        </section>
      </div>
    </section>
  </div>`;
}

async function refresh() {
  if (loading) return;
  loading = true; $('refresh').disabled = true;
  try {
    const response = await fetch('/api/dashboard', {cache:'no-store', signal:AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    snapshot = await response.json(); classify(snapshot); failed = false;
    try {
      sessionStorage.setItem('bionotate.dashboard', JSON.stringify({at:Date.now(), data:snapshot}));
      sessionStorage.setItem('bionotate.crew', JSON.stringify({at:Date.now(), data:snapshot.crew.map(({id,name,role}) => ({id,name,role}))}));
    } catch (_) {}
    render();
    $('connection').textContent = snapshot.mode === 'live'
      ? `Updated ${time(snapshot.generated_at)}`
      : `Demo replay as of ${time(snapshot.demo_as_of)} · No live sensor connection`;
  } catch (error) {
    failed = true;
    $('connection').textContent = `Unable to refresh data. ${snapshot ? 'Showing last retrieved snapshot; readings may be outdated.' : 'No crew data available.'} Use Refresh data to retry.`;
    if (selectedId && snapshot) renderDetail();
  } finally { loading = false; $('refresh').disabled = false; }
}
$('refresh').addEventListener('click', refresh);
$('filter').addEventListener('change', () => snapshot && render());
document.addEventListener('change', event => {
  const key = event.target.dataset.metricAxis;
  if (key) { storedTrendAxis.set(key, event.target.value); if (selectedId) renderDetail(); }
});
document.addEventListener('click', event => {
  if (event.target.closest('[data-profile-refresh]')) { storedTrendCache.clear(); refresh(); return; }
  const button = event.target.closest('[data-member]');
  if (button) { selectedId = button.dataset.member; renderDetail(); if (!$('detail').open) $('detail').showModal(); }
});
$('close').addEventListener('click', () => $('detail').close());
$('detail').addEventListener('close', () => { selectedId = null; });
// Demo profile details (age, blood type, height, weight) kept beside the crew photos.
let profiles = {};
fetch('/ui-assets/crew/profiles.json', {cache:'no-cache'}).then(r => r.ok ? r.json() : {}).then(data => { profiles = data; if (selectedId) renderDetail(); }).catch(() => {});
// Render the last successful response before waiting for the network on navigation.
try {
  const saved = JSON.parse(sessionStorage.getItem('bionotate.dashboard'));
  if (saved && Date.now() - saved.at < 60000) {
    snapshot = saved.data; classify(snapshot); render();
    $('connection').textContent = `Saved data from ${time(snapshot.generated_at)} · Refreshing…`;
  }
} catch (_) {}
refresh();
setInterval(refresh, 15000);
