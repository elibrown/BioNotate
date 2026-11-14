"use strict";
(() => {
  const element = id => document.getElementById(id);
  const dialog = element('manual-dialog');
  let groups = [];
  let databaseMode = false;

  function fillOptions(select, rows) {
    select.replaceChildren(...rows.map(([value, label]) => new Option(label, value)));
  }

  function renderFields() {
    const group = groups.find(item => item.id === element('manual-group').value);
    element('manual-note').textContent = group?.note || '';
    element('manual-fields').replaceChildren(...(group?.fields || []).map(field => {
      const label = document.createElement('label');
      label.textContent = `${field.label} (${field.unit})`;
      const input = document.createElement('input');
      input.type = 'number'; input.step = 'any'; input.name = field.key;
      label.append(input);
      return label;
    }));
    element('manual-save').disabled = !databaseMode || !group?.fields.length;
  }

  async function readJSON(response) {
    const data = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map(item => item.msg).join('; ') : data.detail;
      throw new Error(detail || `Request failed (${response.status})`);
    }
    return data;
  }

  async function openManual() {
    if (!dialog.open) dialog.showModal();
    element('manual-status').textContent = 'Loading crew and measurement groups…';
    element('manual-save').disabled = true;
    const now = new Date();
    element('manual-time').value = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    try {
      const [catalogue, snapshot] = await Promise.all([
        fetch('/api/measurement-catalog').then(readJSON),
        fetch('/api/dashboard').then(readJSON),
      ]);
      groups = catalogue.groups;
      databaseMode = snapshot.mode === 'live';
      fillOptions(element('manual-astronaut'), snapshot.crew.map(member => [member.id, `${member.name} · ${member.id}`]));
      fillOptions(element('manual-group'), groups.map(group => [group.id, `${group.id.split('_')[0]} · ${group.label}`]));
      renderFields();
      element('manual-status').textContent = databaseMode
        ? 'Choose a group and enter one or more values.'
        : 'Manual entry requires database mode. Disable ASTROHEALTH_DASHBOARD=demo first.';
    } catch (error) {
      databaseMode = false;
      element('manual-status').textContent = `Unable to load: ${error.message}. Close and reopen to retry.`;
    }
  }

  async function saveManual(event) {
    event.preventDefault();
    if (!databaseMode || element('manual-save').disabled) return;
    const values = {};
    for (const input of element('manual-fields').querySelectorAll('input')) {
      if (input.value !== '') values[input.name] = Number(input.value);
    }
    if (!Object.keys(values).length) {
      element('manual-status').textContent = 'Enter at least one measurement.';
      return;
    }
    element('manual-save').disabled = true;
    element('manual-status').textContent = 'Saving…';
    try {
      const rows = await fetch('/api/manual-measurements', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({astronaut_id: element('manual-astronaut').value,
          group_id: element('manual-group').value, values,
          measured_at: new Date(element('manual-time').value).toISOString()}),
      }).then(readJSON);
      element('manual-status').textContent = `Saved ${rows.length} measurement(s). Open this astronaut’s health details to view them.`;
      element('manual-fields').querySelectorAll('input').forEach(input => { input.value = ''; });
      document.dispatchEvent(new Event('measurements-saved'));
    } catch (error) {
      element('manual-status').textContent = `Could not save: ${error.message}`;
    } finally { renderSaveState(); }
  }

  function renderSaveState() {
    element('manual-save').disabled = !databaseMode || !groups.find(item => item.id === element('manual-group').value)?.fields.length;
  }
  element('add-measurement').addEventListener('click', openManual);
  element('manual-close').addEventListener('click', () => dialog.close());
  element('manual-group').addEventListener('change', renderFields);
  element('manual-form').addEventListener('submit', saveManual);
})();
