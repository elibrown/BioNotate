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
  function severityLabel(level) { return level ? displayLabel(level) : 'Pending'; }
  function listInto(parent, items, tag = 'ol') {
    const list = node(tag);
    for (const item of items || []) list.append(node('li', item));
    parent.append(list);
  }
  function resetAssessment() {
    state.assessmentId = null;
    state.latest = null;
    $('mada-context-info').textContent = 'When you submit an assessment, up to 12 recent metrics for the selected Patient are sent to MADA as historical context, not as a diagnosis.';
    $('mada-text').value = '';
    $('mada-image').value = '';
    $('mada-audio').value = '';
    state.recordFile = null;
    clearRecordedPreview();
    clear($('mada-checks'));
    $('mada-checks').hidden = true;
    $('mada-result').hidden = true;
    $('mada-submit').textContent = 'Analyze emergency';
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
      const select = $('mada-patient');
      clear(select);
      select.append(node('option', 'Select registered Patient…'));
      select.firstChild.value = '';
      for (const person of people) {
        const option = node('option', `${person.name} (${person.id})`);
        option.value = person.id;
        select.append(option);
      }
    } catch (error) { setMessage(`Cannot load patients: ${error.message}`); }
  }
  async function loadPatientRecord() {
    const id = $('mada-patient').value;
    const selected = $('mada-patient').selectedOptions[0];
    $('mada-patient-detail').textContent = id ? `Patient: ${selected.textContent}. This identity will be recorded with every assessment.` : 'Select the person receiving medical attention.';
    clear($('mada-trends'));
    clear($('mada-history'));
    $('mada-trend-summary').textContent = id ? 'Retrieving measurements…' : 'Select a patient to view measurements.';
    if (!id) return;
    const encoded = encodeURIComponent(id);
    try {
      const trend = await getJSON(`/api/patients/${encoded}/trends`);
      if ($('mada-patient').value === id) renderTrends(trend);
    } catch (error) { $('mada-trend-summary').textContent = error.message; }
    if (!state.enabled) {
      $('mada-history').textContent = 'MADA assessment history is disabled in this environment.';
      return;
    }
    try {
      const history = await getJSON(`/api/patients/${encoded}/mada-assessments`);
      if ($('mada-patient').value === id) renderHistory(history);
    } catch (error) { $('mada-history').textContent = error.message; }
  }
  function renderTrends(data) {
    $('mada-trend-summary').textContent = data.summary;
    const target = $('mada-trends'); clear(target);
    for (const m of data.metrics) {
      const card = node('article', '', 'mada-trend');
      card.append(node('span', `${displayLabel(m.source)} · ${m.observations} independent observation(s)`, 'meta'));
      card.append(node('strong', displayLabel(m.metric)));
      card.append(node('div', `Latest: ${m.latest.value} ${m.unit || ''} (${time(m.latest.measured_at)})`, 'meta'));
      card.append(node('div', m.delta === null ? 'Only one observation; no trend can be calculated.' :
        `${displayLabel(m.direction)} · Δ ${m.delta > 0 ? '+' : ''}${m.delta} ${m.unit || ''} since ${time(m.first.measured_at)}`, 'delta'));
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
        line.setAttribute('stroke', '#0472d3'); line.setAttribute('stroke-width', '3');
        line.setAttribute('stroke-linecap', 'round'); line.setAttribute('stroke-linejoin', 'round');
        svg.append(line); card.append(svg);
      }
      target.append(card);
    }
  }
  function renderHistory(items) {
    const target = $('mada-history'); clear(target);
    if (!items.length) { target.textContent = 'No saved emergency assessments for this Patient.'; return; }
    for (const item of items) {
      const card = node('article', '', 'mada-history-item');
      card.append(node('strong', `${severityLabel(item.latest_response?.severity)} · ${displayLabel(item.action)}`));
      card.append(node('div', `${time(item.updated_at)} · Responder: ${item.responder_id || 'not specified'}`));
      const open = node('button', 'Open / resume');
      open.type = 'button';
      open.addEventListener('click', async () => {
        try {
          const record = await getJSON(`/api/mada/assessments/${encodeURIComponent(item.id)}`);
          if (record.patient_id !== $('mada-patient').value) throw new Error('This assessment belongs to another Patient.');
          resetAssessment();
          state.assessmentId = record.id;
          state.latest = record.latest_response;
          $('mada-responder').value = record.responder_id || '';
          renderResult(record.latest_response);
          setMessage(`Loaded assessment from ${time(record.updated_at)}. You may submit follow-up information.`);
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
    if (check.status === 'UNVALIDATED') area.append(node('span', 'UNVALIDATED placeholder', 'unvalidated'));
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
      area.append(node('p', 'Attach or record the requested audio above. The answer “recorded” will be sent with it.'));
    } else {
      area.append(node('p', `Unsupported Check format: ${type || 'unknown'}. Please contact the project team.`));
    }
    return area;
  }
  function renderChecks(checks, warnings = []) {
    const target = $('mada-checks'); clear(target);
    target.hidden = !checks.length;
    if (!checks.length) return;
    target.append(node('h3', 'Requested Checks'));
    target.append(node('p', 'Complete the following observations, then submit the answers. Never invent a reading.'));
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
    $('mada-severity').className = `mada-status ${result.severity === 'life_threatening' ? 'down' : ''}`;
    const gcsAlert = $('mada-gcs-alert');
    gcsAlert.hidden = !result.gcs_alert;
    gcsAlert.textContent = result.gcs_alert?.message || '';
    const firstSteps = $('mada-first-steps'); clear(firstSteps);
    for (const step of result.first_steps || []) firstSteps.append(node('li', step));
    const modelMessage = $('mada-model-message');
    modelMessage.hidden = !result.degraded;
    modelMessage.textContent = result.degraded ? (result.message || 'MADA was unavailable. Guidance was retrieved without the model.') : '';
    const protocols = $('mada-protocols'); clear(protocols);
    for (const protocol of result.protocols || []) {
      const section = node('section', '', `mada-protocol ${protocol.severity === 'life_threatening' ? 'critical' : 'urgent'}`);
      section.append(node('span', severityLabel(protocol.severity), 'mada-status'));
      section.append(node('h3', protocol.title));
      // Verbatim text: neither summarize nor translate the official checklist.
      const protocolSteps = node('div', '', 'mada-verbatim');
      for (const step of protocol.steps || []) protocolSteps.append(node('p', step));
      section.append(protocolSteps);
      protocols.append(section);
    }
    $('mada-no-match').hidden = !result.no_protocol_match;
    $('mada-no-match').textContent = result.no_protocol_match ? (result.message || 'No protocol matched; request assessment by the Crew Medical Officer.') : '';
    $('mada-rationale').textContent = result.rationale || 'No model rationale provided.';
    const features = $('mada-features'); clear(features);
    for (const feature of result.observed_features || []) features.append(node('li', `Unconfirmed: ${feature}`));
    $('mada-result-disclaimer').textContent = result.disclaimer || 'Decision support only. Contact the Crew Medical Officer.';
    renderChecks(result.action === 'ask_checks' ? result.next_checks || [] : [], result.answer_warnings || []);
    $('mada-submit').textContent = result.action === 'ask_checks' ? 'Submit Check answers' : 'Send new information';
  }

  async function submit(event) {
    event.preventDefault();
    if (!state.enabled) { setMessage('MADA is disabled. Contact the project team to enable the local demo.'); return; }
    const patientId = $('mada-patient').value;
    if (!patientId) { setMessage('Choose the Patient from the crew roster first.'); return; }
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
        throw new Error('Enter a description, answer a Check, or attach a photo/audio recording.');
      }
      button.disabled = true; $('mada-patient').disabled = true;
      setMessage('MADA is analyzing the assessment. Keep this window open…');
      const response = await fetch('/api/mada/assess', { method: 'POST', body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(errorMessage(data, response.status));
      if (Number.isInteger(data.patient_context_metrics_sent)) {
        const n = data.patient_context_metrics_sent;
        $('mada-context-info').textContent = `${n} historical metric${n === 1 ? '' : 's'} supplied to MADA as patient context. This does not mean the agent interpreted them as a diagnosis.`;
      }
      state.assessmentId = data.assessment_id;
      state.latest = data.assessment;
      renderResult(data.assessment);
      setMessage(`Assessment saved for Patient ${data.patient.name} (${data.patient.id}) at ${time(data.saved_at)}.`);
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
          message: `MADA unavailable: ${error.message}. Contact the Crew Medical Officer.`,
          disclaimer: 'Model unavailable. Emergency steps below came from the protocol catalogue.'});
      }
    }
    finally { button.disabled = false; $('mada-patient').disabled = false; }
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
  $('mada-new').addEventListener('click', () => { resetAssessment(); setMessage('New assessment. Enter symptoms or upload media.'); });
  $('mada-record').addEventListener('click', startRecording);
  $('mada-stop').addEventListener('click', stopRecording);
  $('mada-audio').addEventListener('change', () => { state.recordFile = null; clearRecordedPreview(); });

  async function initialize() {
    await loadPatients();
    try {
      const status = await getJSON('/api/mada/status');
      state.enabled = !!(status.demo_enabled && status.configured);
      $('mada-status').textContent = state.enabled ? 'Demo model configured' : 'Model not configured / disabled';
      $('mada-status').classList.add(state.enabled ? 'ok' : 'down');
      setMessage(state.enabled ? 'Select a patient and describe the emergency.' :
        'MADA inference is disabled. Patient trend retrieval still works.');
      $('mada-submit').disabled = !state.enabled;
      if (state.enabled) {
        // Cache the service-provided first steps for a temporarily busy model.
        // A fresh response still takes precedence over this fallback.
        try {
          const catalogue = await getJSON('/api/mada/protocols');
          state.universalSteps = Array.isArray(catalogue.first_steps) ? catalogue.first_steps : [];
        } catch { /* The MADA server may still be starting. */ }
      }
    } catch (error) { $('mada-status').textContent = 'Status unavailable'; setMessage(error.message); }
  }
  initialize();
})();
