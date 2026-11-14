"use strict";
(() => {
  const $ = id => document.getElementById(id);
  let metrics = [], ready = false;
  async function read(response) {
    const data = await response.json();
    if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail.map(item => item.msg).join('; ') : data.detail || `HTTP ${response.status}`);
    return data;
  }
  function showUnit() {
    $('manual-unit').textContent = metrics.find(metric => metric.key === $('manual-metric').value)?.unit || '';
  }
  async function load() {
    $('manual-save').disabled = true;
    $('manual-status').textContent = 'Loading…';
    const now = new Date();
    $('manual-time').value = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0,16);
    try {
      const [catalogue, dashboard] = await Promise.all([
        fetch('/api/measurement-catalog', {cache:'no-store'}).then(read),
        fetch('/api/dashboard', {cache:'no-store'}).then(read),
      ]);
      metrics = catalogue.metrics;
      $('manual-astronaut').replaceChildren(...dashboard.crew.map(member => new Option(`${member.name} · ${member.id}`, member.id)));
      $('manual-metric').replaceChildren(...metrics.map(metric => new Option(metric.label, metric.key)));
      ready = dashboard.mode === 'live' && dashboard.crew.length > 0;
      showUnit();
      $('manual-status').textContent = ready ? 'Choose one metric and enter its value.' : 'Manual entry requires database mode and a crew roster.';
    } catch (error) { $('manual-status').textContent = `Unable to load: ${error.message}. Reload to retry.`; }
    $('manual-save').disabled = !ready;
  }
  $('manual-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!ready || $('manual-save').disabled) return;
    $('manual-save').disabled = true;
    $('manual-status').textContent = 'Saving…';
    try {
      const row = await fetch('/api/manual-measurements', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({astronaut_id:$('manual-astronaut').value,
          metric:$('manual-metric').value, value:Number($('manual-value').value),
          measured_at:new Date($('manual-time').value).toISOString()}),
      }).then(read);
      $('manual-status').textContent = `Saved one measurement: ${metrics.find(metric => metric.key === row.metric).label} ${row.value} ${row.unit}. View it in this crew member’s health details.`;
      $('manual-value').value = '';
    } catch (error) { $('manual-status').textContent = `Could not save: ${error.message}`; }
    finally { $('manual-save').disabled = !ready; }
  });
  $('manual-metric').addEventListener('change', showUnit);
  load();
})();
