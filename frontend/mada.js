/* MADA assessment UI. All model-supplied strings are rendered with textContent.
   Never reinterpret or translate the protocol and first-step instructions. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = { assessmentId: null, latest: null, enabled: false,
    mediaRecorder: null, stream: null, recordFile: null, timerId: null, started: 0, objectUrl: null, universalSteps: [] };

  function node(tag, text = '', cls = '') {
    const e = document.createElement(tag);
    if (text !== null && text !== undefined) e.textContent = String(text);
    if (cls) e.className = cls;
    return e;
  }
  function clear(element) { element.replaceChildren(); }
  function errorMessage(data, code) {
    if (typeof data?.detail === 'string') return data.detail;
    return `Request failed (HTTP ${code}).`;
  }
  async function getJSON(path) {
    const r = await fetch(path, { cache: 'no-store' });
    const data = await r.json();
    if (!r.ok) throw new Error(errorMessage(data, r.status));
    return data;
  }
  function setMessage(msg) { $('mada-message').textContent = msg; }
  function time(iso) {
    if (!iso) return '—';
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
  }
  function displayLabel(key) { return String(key).replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase()); }
  function severityLabel(level) {
    return { life_threatening: 'Life-threatening', urgent: 'Urgent' }[level] || 'Not decided yet';
  }
  function severityClass(level) { return { life_threatening: 'red', urgent: 'yellow' }[level] || ''; }
  const SOURCE_NAMES = { cardioresp: 'From video', voicebiomarker: 'From voice', manual: 'Entered by hand', shared_demo: 'Demo reading' };
  function sourceLabel(source) { return SOURCE_NAMES[source] || displayLabel(source); }
  function shortTime(iso) {
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? (iso || '—') : date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  function listInto(parent, items, tag = 'ol') {
    const list = node(tag);
    for (const item of items || []) list.append(node('li', item));
    parent.append(list);
  }
  function resetAssessment() {
    state.assessmentId = null;
    state.latest = null;
    $('mada-context-info').textContent = 'When you ask for help, up to 12 recent readings are shared with the assistant as background.';
    $('mada-text').value = '';
    $('mada-image').value = '';
    $('mada-audio').value = '';
    state.recordFile = null;
    clearRecordedPreview();
    clear($('mada-checks'));
    $('mada-checks').hidden = true;
    $('mada-result').hidden = true;
    $('mada-submit').textContent = 'Get emergency steps';
  }
  function clearRecordedPreview() {
    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
    state.objectUrl = null;
    $('mada-preview').hidden = true;
    $('mada-preview').removeAttribute('src');
  }

  async function loadPatients() {
    try {
      const people = await getJSON('/api/patients');
      const select = $('mada-patient'), crew = $('mada-crew');
      clear(select); clear(crew);
      select.append(node('option', 'No one selected'));
      select.firstChild.value = '';
      for (const person of people) {
        const option = node('option', `${person.name} (${person.id})`);
        option.value = person.id;
        select.append(option);
        // A small crew card with the same photos as the dashboard.
        const card = node('button', '', 'crew-pick');
        card.type = 'button';
        card.setAttribute('role', 'radio');
        card.setAttribute('aria-checked', 'false');
        card.dataset.id = person.id;
        const img = node('img');
        img.src = `/ui-assets/crew/${encodeURIComponent(person.id)}.jpg`;
        img.alt = '';
        img.onerror = () => { img.onerror = null; img.src = '/ui-assets/portrait-placeholder.svg'; };
        const who = node('span', '', 'who');
        who.append(node('strong', person.name), node('small', `${person.role || 'Crew'} · ${person.id}`));
        card.append(img, who, node('span', '✓', 'tick'));
        card.addEventListener('click', () => {
          if (select.disabled || select.value === person.id) return;
          select.value = person.id;
          select.dispatchEvent(new Event('change'));
        });
        crew.append(card);
      }
    } catch (error) { setMessage(`Cannot load the crew list: ${error.message}`); }
  }
  async function loadPatientRecord() {
    const id = $('mada-patient').value;
    const selected = $('mada-patient').selectedOptions[0];
    for (const card of $('mada-crew').children) card.setAttribute('aria-checked', String(card.dataset.id === id));
    $('mada-patient-detail').hidden = !id;
    $('mada-patient-detail').textContent = id ? `Helping ${selected.textContent}. Everything you send is saved to their record.` : '';
    clear($('mada-trends'));
    clear($('mada-history'));
    $('mada-trend-summary').textContent = id ? 'Loading measurements…' : 'Choose a crew member to see their measurements.';
    if (!id) return;
    const encoded = encodeURIComponent(id);
    try {
      const trend = await getJSON(`/api/patients/${encoded}/trends`);
      if ($('mada-patient').value === id) renderTrends(trend);
    } catch (error) { $('mada-trend-summary').textContent = error.message; }
    if (!state.enabled) {
      $('mada-history').textContent = 'History appears here once the assistant is switched on.';
      return;
    }
    try {
      const history = await getJSON(`/api/patients/${encoded}/mada-assessments`);
      if ($('mada-patient').value === id) renderHistory(history);
    } catch (error) { $('mada-history').textContent = error.message; }
  }
  function renderTrends(data) {
    $('mada-trend-summary').textContent = data.metrics.length
      ? 'Latest reading of each measurement. These show changes only, not a diagnosis.'
      : 'No measurements recorded for this crew member yet.';
    const target = $('mada-trends'); clear(target);
    for (const m of data.metrics) {
      const card = node('article', '', 'mada-trend');
      const row = node('div', '', 'row');
      const value = node('span', m.latest.value, 'value');
      if (m.unit) value.append(node('small', m.unit));
      row.append(node('strong', m.label || displayLabel(m.metric)), value);
      card.append(row);
      card.append(node('div', `${sourceLabel(m.source)} · ${shortTime(m.latest.measured_at)}`, 'meta'));
      if (m.delta !== null) {
        const word = { increasing: 'Up', decreasing: 'Down', stable: 'No change' }[m.direction] || displayLabel(m.direction);
        card.append(node('div', `${word}${m.delta ? ` ${Math.abs(m.delta)} ${m.unit || ''}` : ''} over ${m.observations} readings`, 'delta'));
      }
      if (m.points.length > 1) {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 260 54');
        svg.setAttribute('role', 'img');
        svg.setAttribute('aria-label', `Trend for ${m.metric}: ${m.points.map(p => p.value).join(', ')}`);
        const values = m.points.map(p => p.value), min = Math.min(...values), max = Math.max(...values);
        const span = max - min || 1;
        const pts = values.map((v, i) => `${8 + 244 * i / (values.length - 1)},${44 - ((v - min) / span) * 34}`).join(' ');
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
        line.setAttribute('points', pts); line.setAttribute('fill', 'none');
        line.setAttribute('stroke', '#0472d3'); line.setAttribute('stroke-width', '2.5');
        line.setAttribute('stroke-linecap', 'round'); line.setAttribute('stroke-linejoin', 'round');
        svg.append(line); card.append(svg);
      }
      target.append(card);
    }
  }
  function renderHistory(items) {
    const target = $('mada-history'); clear(target);
    if (!items.length) { target.textContent = 'No past emergencies for this crew member.'; return; }
    for (const item of items) {
      const card = node('article', '', 'mada-history-item');
      card.append(node('strong', `${severityLabel(item.latest_response?.severity)} · ${item.action === 'ask_checks' ? 'waiting for answers' : 'finished'}`));
      card.append(node('span', `${shortTime(item.updated_at)} · Helped by ${item.responder_id || 'not recorded'}`));
      const open = node('button', 'Open', 'mada-button');
      open.type = 'button';
      open.addEventListener('click', async () => {
        try {
          const record = await getJSON(`/api/mada/assessments/${encodeURIComponent(item.id)}`);
          if (record.patient_id !== $('mada-patient').value) throw new Error('This record belongs to another crew member.');
          resetAssessment();
          state.assessmentId = record.id;
          state.latest = record.latest_response;
          $('mada-responder').value = record.responder_id || '';
          renderResult(record.latest_response);
          setMessage(`Opened the record from ${shortTime(record.updated_at)}. You can add more information.`);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        } catch (error) { setMessage(error.message); }
      });
      card.append(open); target.append(card);
    }
  }

  function renderCheckField(check) {
    const area = node('fieldset', '', 'mada-check');
    area.dataset.checkId = check.id;
    area.append(node('legend', check.title || check.id));
    if (check.status === 'UNVALIDATED') area.append(node('span', 'Not yet medically reviewed', 'unvalidated'));
    if (check.instruction) area.append(node('p', check.instruction));
    const answer = check.answer || {}, type = answer.type;
    if (type === 'choice') {
      const select = node('select'); select.dataset.answerType = type;
      const empty = node('option', 'Select an answer…'); empty.value = ''; select.append(empty);
      for (const opt of answer.options || []) {
        const option = node('option', displayLabel(opt)); option.value = opt; select.append(option);
      }
      area.append(select);
    } else if (type === 'multi_choice') {
      const list = node('div'); list.dataset.answerType = type;
      for (const opt of answer.options || []) {
        const label = node('label', '', 'check-option');
        const input = node('input'); input.type = 'checkbox'; input.value = opt;
        label.append(input, node('span', displayLabel(opt))); list.append(label);
      }
      area.append(list);
    } else if (type === 'number') {
      const input = node('input'); input.type = 'number'; input.step = 'any';
      if (Array.isArray(answer.plausible)) { input.min = answer.plausible[0]; input.max = answer.plausible[1]; }
      input.dataset.answerType = type; input.placeholder = `Value ${answer.unit ? `(${answer.unit})` : ''}`;
      area.append(input);
    } else if (type === 'gcs') {
      const fields = node('div', '', 'gcs-fields'); fields.dataset.answerType = type;
      for (const part of ['eye', 'verbal', 'motor']) {
        const label = node('label', displayLabel(part));
        const select = node('select'); select.dataset.gcsPart = part;
        const empty = node('option', 'Select…'); empty.value = ''; select.append(empty);
        for (const level of answer.components?.[part] || []) {
          const opt = node('option', `${level.score}: ${level.rating} — ${level.criterion}`);
          opt.value = String(level.score); select.append(opt);
        }
        label.append(select); fields.append(label);
      }
      area.append(fields);
    } else if (type === 'audio') {
      area.dataset.audioCheck = 'true';
      area.append(node('p', 'Record or attach a voice note below; it will be sent as the answer.'));
    } else {
      area.append(node('p', `Unsupported Check format: ${type || 'unknown'}. Please contact the project team.`));
    }
    return area;
  }
  function renderChecks(checks, warnings = []) {
    const target = $('mada-checks'); clear(target);
    target.hidden = !checks.length;
    if (!checks.length) return;
    target.append(node('h3', 'The assistant needs a few more details'));
    target.append(node('p', 'Check these on the crew member, then send your answers. Leave anything you could not check blank.'));
    for (const check of checks) {
      const field = renderCheckField(check);
      const specific = warnings.filter(w => w.check_id === check.id || w.id === check.id);
      for (const warn of specific) field.append(node('p', warn.message || warn.reason || 'This answer needs to be repeated.'));
      target.append(field);
    }
  }
  function collectCheckAnswers() {
    const answers = {};
    for (const field of $('mada-checks').querySelectorAll('fieldset[data-check-id]')) {
      const id = field.dataset.checkId;
      const typed = field.querySelector('[data-answer-type]');
      if (field.dataset.audioCheck) {
        if ($('mada-audio').files[0] || state.recordFile) answers[id] = 'recorded';
      } else if (typed?.dataset.answerType === 'choice') {
        if (typed.value) answers[id] = typed.value;
      } else if (typed?.dataset.answerType === 'multi_choice') {
        const choices = Array.from(typed.querySelectorAll('input:checked'), el => el.value);
        if (choices.length) answers[id] = choices;
      } else if (typed?.dataset.answerType === 'number') {
        if (typed.value !== '') answers[id] = Number(typed.value);
      } else if (typed?.dataset.answerType === 'gcs') {
        const gcs = {}, fields = Array.from(typed.querySelectorAll('select[data-gcs-part]'));
        for (const select of fields) if (select.value) gcs[select.dataset.gcsPart] = select.value === 'NT' ? 'NT' : Number(select.value);
        if (Object.keys(gcs).length === 3) answers[id] = gcs;
        else if (Object.keys(gcs).length) throw new Error('Complete all three GCS components or leave them all blank.');
      }
    }
    return answers;
  }
  function renderResult(result) {
    $('mada-result').hidden = false;
    $('mada-severity').textContent = severityLabel(result.severity);
    $('mada-severity').className = `mada-badge ${severityClass(result.severity)}`;
    const gcsAlert = $('mada-gcs-alert');
    gcsAlert.hidden = !result.gcs_alert;
    gcsAlert.textContent = result.gcs_alert?.message || '';
    const firstSteps = $('mada-first-steps'); clear(firstSteps);
    for (const step of result.first_steps || []) firstSteps.append(node('li', step));
    const modelMessage = $('mada-model-message');
    modelMessage.hidden = !result.degraded;
    modelMessage.textContent = result.degraded ? (result.message || 'The AI model was unavailable, so these steps come straight from the protocol list.') : '';
    const protocols = $('mada-protocols'); clear(protocols);
    for (const protocol of result.protocols || []) {
      const section = node('section', '', `mada-protocol ${protocol.severity === 'life_threatening' ? 'critical' : 'urgent'}`);
      section.append(node('span', severityLabel(protocol.severity), `mada-badge ${severityClass(protocol.severity)}`));
      section.append(node('h4', protocol.title));
      // Verbatim text: neither summarize nor translate the official checklist.
      const protocolSteps = node('div', '', 'mada-verbatim');
      for (const step of protocol.steps || []) protocolSteps.append(node('p', step));
      section.append(protocolSteps);
      protocols.append(section);
    }
    $('mada-no-match').hidden = !result.no_protocol_match;
    $('mada-no-match').textContent = result.no_protocol_match ? (result.message || 'No matching emergency procedure was found. Ask the Crew Medical Officer to assess.') : '';
    $('mada-rationale').textContent = result.rationale || 'The assistant did not give a reason.';
    const features = $('mada-features'); clear(features);
    for (const feature of result.observed_features || []) features.append(node('li', `Noticed, not confirmed: ${feature}`));
    $('mada-result-disclaimer').textContent = result.disclaimer || 'Suggestions only. Contact the Crew Medical Officer.';
    renderChecks(result.action === 'ask_checks' ? result.next_checks || [] : [], result.answer_warnings || []);
    $('mada-submit').textContent = result.action === 'ask_checks' ? 'Send answers' : 'Send more information';
  }

  async function submit(event) {
    event.preventDefault();
    if (!state.enabled) { setMessage('The assistant is offline, so it cannot answer yet.'); return; }
    const patientId = $('mada-patient').value;
    if (!patientId) { setMessage('First choose who needs help.'); return; }
    const button = $('mada-submit');
    try {
      const answers = collectCheckAnswers();
      const form = new FormData();
      form.append('patient_id', patientId);
      const responder = $('mada-responder').value.trim();
      if (responder) form.append('responder_id', responder);
      if (state.assessmentId) form.append('assessment_id', state.assessmentId);
      form.append('text', $('mada-text').value.trim());
      form.append('check_answers', JSON.stringify(answers));
      if ($('mada-image').files[0]) form.append('image', $('mada-image').files[0]);
      const audio = state.recordFile || $('mada-audio').files[0];
      if (audio) form.append('audio', audio);
      if (![...form.values()].some(x => x instanceof File) && !form.get('text') && !Object.keys(answers).length) {
        throw new Error('Describe what is happening, answer a question, or add a photo or voice note.');
      }
      button.disabled = true; $('mada-patient').disabled = true;
      setMessage('The assistant is thinking. This can take up to a minute; keep this page open…');
      const response = await fetch('/api/mada/assess', { method: 'POST', body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(errorMessage(data, response.status));
      if (Number.isInteger(data.patient_context_metrics_sent)) {
        const n = data.patient_context_metrics_sent;
        $('mada-context-info').textContent = `${n} recent reading${n === 1 ? ' was' : 's were'} shared with the assistant as background.`;
      }
      state.assessmentId = data.assessment_id;
      state.latest = data.assessment;
      renderResult(data.assessment);
      setMessage(`Saved to ${data.patient.name}'s record at ${shortTime(data.saved_at)}.`);
      $('mada-text').value = '';
      $('mada-image').value = '';
      $('mada-audio').value = '';
      state.recordFile = null; clearRecordedPreview();
      await loadPatientRecord();
      $('mada-result').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      setMessage(error.message);
      // If the model is down/busy, keep universal safety steps visible when
      // they were previously obtained from the MADA service (never invent them).
      if (state.universalSteps.length && !state.latest) {
        renderResult({action: 'finalize', first_steps: state.universalSteps,
          severity: null, protocols: [], next_checks: [], degraded: true,
          message: `The assistant could not answer (${error.message}). Contact the Crew Medical Officer.`,
          disclaimer: 'The AI model was unavailable. The steps above come straight from the protocol list.'});
      }
    }
    finally { button.disabled = !state.enabled; $('mada-patient').disabled = false; }
  }

  function stopRecording() {
    if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') state.mediaRecorder.stop();
    clearInterval(state.timerId); state.timerId = null;
    $('mada-record').disabled = false; $('mada-stop').disabled = true;
  }
  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setMessage('This browser cannot record audio. Upload an audio file instead.'); return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      state.stream = stream;
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find(type => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks = [];
      recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach(t => t.stop()); state.stream = null;
        const type = recorder.mimeType || 'audio/webm';
        const ext = type.includes('mp4') ? 'm4a' : 'webm';
        const blob = new Blob(chunks, { type });
        if (!blob.size) { setMessage('No audio was captured. Retry recording.'); return; }
        state.recordFile = new File([blob], `assessment.${ext}`, { type });
        $('mada-audio').value = '';
        clearRecordedPreview();
        state.objectUrl = URL.createObjectURL(blob);
        $('mada-preview').src = state.objectUrl;
        $('mada-preview').hidden = false;
        setMessage(`Audio recorded (${Math.round(blob.size / 1024)} KB).`);
      };
      recorder.onerror = () => setMessage('Audio recording failed. Upload a file instead.');
      recorder.start(); state.mediaRecorder = recorder; state.started = Date.now();
      $('mada-record').disabled = true; $('mada-stop').disabled = false;
      state.timerId = setInterval(() => {
        const seconds = Math.min(30, Math.floor((Date.now() - state.started) / 1000));
        $('mada-timer').textContent = `00:${String(seconds).padStart(2, '0')} / 00:30`;
        if (seconds >= 30) stopRecording();
      }, 250);
      setMessage('Recording. Stop within 30 seconds.');
    } catch (error) { setMessage(`Microphone unavailable: ${error.message}`); }
  }

  $('mada-patient').addEventListener('change', () => { resetAssessment(); loadPatientRecord(); });
  $('mada-form').addEventListener('submit', submit);
  $('mada-new').addEventListener('click', () => { resetAssessment(); setMessage('Started over. Describe what is happening.'); });
  $('mada-record').addEventListener('click', startRecording);
  $('mada-stop').addEventListener('click', stopRecording);
  $('mada-audio').addEventListener('change', () => { state.recordFile = null; clearRecordedPreview(); });

  async function initialize() {
    await loadPatients();
    try {
      const status = await getJSON('/api/mada/status');
      // The backend reports one of: online, offline, not_configured, disabled.
      // The model server address itself only lives on the backend (MADA_SERVICE_URL).
      const model = status.model || (status.demo_enabled && status.configured ? 'online' : 'disabled');
      state.enabled = model === 'online';
      $('mada-status-text').textContent = state.enabled ? 'Assistant online' : 'Assistant offline';
      $('mada-status').classList.add(state.enabled ? 'online' : 'offline');
      const offline = {
        disabled: 'The AI model is not switched on for this site yet. You can still choose a crew member and look at their recent measurements.',
        not_configured: 'The AI model is switched on, but no server address is set (MADA_SERVICE_URL). You can still look at measurements.',
        offline: 'The AI model server is set up but not answering right now. It may still be starting; try again in a minute.',
      }[model];
      $('mada-offline').hidden = state.enabled;
      if (offline) $('mada-offline-text').textContent = offline;
      setMessage(state.enabled ? 'Choose who needs help and describe what is happening.' :
        'The assistant is offline, so sending is turned off for now.');
      $('mada-submit').disabled = !state.enabled;
      if (state.enabled) {
        // Cache the service-provided first steps for a temporarily busy model.
        // A fresh response still takes precedence over this fallback.
        try {
          const catalogue = await getJSON('/api/mada/protocols');
          state.universalSteps = Array.isArray(catalogue.first_steps) ? catalogue.first_steps : [];
        } catch { /* The MADA server may still be starting. */ }
      }
    } catch (error) { $('mada-status-text').textContent = 'Status unknown'; setMessage(error.message); }
  }
  initialize();
})();
