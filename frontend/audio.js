"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const TASKS = [
    { field: "counting_normal", title: "Count from 1 to 20 normally", detail: "Count clearly at a comfortable, natural pace.", target: "Recommended duration: about 10 seconds" },
    { field: "counting_fast", title: "Count from 1 to 20 quickly", detail: "Count clearly from 1 to 20 faster than usual.", target: "Recommended duration: about 6 seconds" },
    { field: "vowel_a", title: 'Sustain “aaa”', detail: 'Hold the “aaa” sound at a comfortable pitch without stopping.', target: "Record for at least 5 seconds" },
    { field: "vowel_e", title: 'Sustain “eee”', detail: 'Hold the “eee” sound at a comfortable pitch without stopping.', target: "Record for at least 5 seconds" },
    { field: "vowel_o", title: 'Sustain “ooo”', detail: 'Hold the “ooo” sound at a comfortable pitch without stopping.', target: "Record for at least 5 seconds" }
  ];
  const MAX_BYTES = 10 * 1024 * 1024; // Entire request, not per clip.
  const FORMAT_OPTIONS = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus"];
  const files = Array(TASKS.length).fill(null);
  let step = 0;
  let recorder = null;
  let micStream = null;
  let previewUrl = null;
  let timerInterval = null;
  let startedAt = 0;
  let recording = false;
  let requestingMic = false;
  let submitting = false;
  let rosterReady = false;

  const status = message => { $("audio-status").textContent = message; };
  const count = () => files.filter(Boolean).length;
  const totalBytes = () => files.reduce((sum, file) => sum + (file?.size || 0), 0);
  const allReady = () => count() === TASKS.length;
  const busy = () => recording || requestingMic || submitting;

  function hideResult() { $("audio-result").hidden = true; }
  function closePreview() {
    $("audio-preview").pause();
    $("audio-preview").removeAttribute("src");
    $("audio-preview").load();
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }
  function showPreview() {
    closePreview();
    const file = files[step];
    $("audio-preview").hidden = !file;
    if (file) {
      previewUrl = URL.createObjectURL(file);
      $("audio-preview").src = previewUrl;
    }
  }
  function renderChecklist() {
    const list = $("audio-review-list");
    list.replaceChildren();
    TASKS.forEach((task, index) => {
      const item = document.createElement("li");
      item.textContent = `${task.title}: ${files[index] ? "Ready" : "Not recorded"}`;
      list.appendChild(item);
    });
  }
  function render() {
    const task = TASKS[step];
    $("audio-progress").textContent = `Step ${step + 1} of ${TASKS.length}`;
    $("audio-completed").textContent = `${count()} of ${TASKS.length} completed`;
    $("audio-progress-bar").value = count();
    $("audio-task-title").textContent = task.title;
    $("audio-task-detail").textContent = task.detail;
    $("audio-task-target").textContent = task.target;
    $("audio-record").disabled = requestingMic || submitting;
    $("audio-record").textContent = recording ? "Stop recording" : "Start recording";
    $("audio-record").classList.toggle("is-recording", recording);
    $("audio-record").setAttribute("aria-pressed", String(recording));
    $("audio-retry").disabled = busy() || !files[step];
    $("audio-file").disabled = busy();
    $("audio-prev").disabled = busy() || step === 0;
    $("audio-next").hidden = step === TASKS.length - 1;
    $("audio-next").disabled = busy() || !files[step];
    $("audio-send").disabled = busy() || !allReady();
    $("audio-astronaut").disabled = busy() || !rosterReady;
    $("audio-submit-help").textContent = !allReady()
      ? "Complete all five recordings to submit."
      : !$("audio-astronaut").value.trim()
        ? "All recordings are ready. Select an astronaut above before submitting."
        : "All recordings are ready to submit.";
    renderChecklist();
  }
  function changeStep(next) {
    if (busy() || next < 0 || next >= TASKS.length) return;
    step = next;
    $("audio-file").value = "";
    $("audio-timer").textContent = "00:00";
    showPreview();
    render();
    status(files[step] ? "Review your recording, retry it, or continue." : "Record this clip or select a compatible file.");
  }
  function saveFile(file) {
    if (!file || file.size === 0) { status("The recording is empty. Please try again."); return; }
    if (!/\.(wav|webm|ogg|opus)$/i.test(file.name)) {
      status("Unsupported file type. Use WAV, WebM/Opus or Ogg/Opus.");
      return;
    }
    const newTotal = totalBytes() - (files[step]?.size || 0) + file.size;
    if (newTotal > MAX_BYTES) {
      status("The five recordings must total no more than 10 MiB. Please retry with shorter clips.");
      return;
    }
    files[step] = file;
    hideResult();
    showPreview();
    render();
    status(`${TASKS[step].title} saved. Listen to it, then continue when ready.`);
  }
  function stopMic() {
    micStream?.getTracks().forEach(track => track.stop());
    micStream = null;
  }
  function stopTimer() {
    if (timerInterval !== null) clearInterval(timerInterval);
    timerInterval = null;
  }
  function updateTimer() {
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    $("audio-timer").textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
    if (seconds >= 120 && recorder?.state === "recording") recorder.stop();
  }

  $("audio-record").addEventListener("click", async () => {
    if (recording) {
      if (recorder?.state === "recording") recorder.stop();
      return;
    }
    if (busy()) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      status("Microphone recording requires a supported browser using HTTPS or localhost.");
      return;
    }
    const mimeType = FORMAT_OPTIONS.find(type => MediaRecorder.isTypeSupported(type));
    if (!mimeType) {
      status("This browser cannot record WebM/Opus or Ogg/Opus. Use Chrome/Edge or upload a WAV file.");
      return;
    }
    requestingMic = true;
    status("Waiting for microphone permission. Allow microphone access in your browser to start recording.");
    render();
    try {
      let expired = false;
      let permissionTimer;
      const permission = navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
        if (expired) {
          stream.getTracks().forEach(track => track.stop());
          throw new Error("Microphone request expired. Please try recording again.");
        }
        return stream;
      });
      try {
        micStream = await Promise.race([
          permission,
          new Promise((resolve, reject) => {
            permissionTimer = setTimeout(() => {
              expired = true;
              reject(new Error("Microphone permission is still pending. Check the browser microphone permission, then try again."));
            }, 20000);
          })
        ]);
      } finally {
        clearTimeout(permissionTimer);
      }
      const activeRecorder = new MediaRecorder(micStream, { mimeType });
      const chunks = [];
      let recorderError = null;
      recorder = activeRecorder;
      activeRecorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      activeRecorder.onerror = event => { recorderError = event.error?.message || "Recording failed."; };
      activeRecorder.onstop = () => {
        const elapsed = (Date.now() - startedAt) / 1000;
        recording = false;
        stopTimer();
        stopMic();
        recorder = null;
        if (recorderError) {
          status(recorderError);
        } else if (step >= 2 && elapsed < 5) {
          status("Hold this vowel for at least 5 seconds. Please record it again.");
        } else {
          const extension = mimeType.startsWith("audio/ogg") ? "ogg" : "webm";
          const clip = new File(chunks, `${TASKS[step].field}.${extension}`, { type: mimeType });
          saveFile(clip);
        }
        render();
      };
      activeRecorder.start();
      recording = true;
      startedAt = Date.now();
      $("audio-timer").textContent = "00:00";
      timerInterval = setInterval(updateTimer, 250);
      status("Recording. Speak clearly, then press Stop recording.");
    } catch (error) {
      stopMic();
      status(`Microphone unavailable: ${error.message}`);
    } finally {
      requestingMic = false;
      render();
    }
  });

  $("audio-file").addEventListener("change", event => {
    if (!busy() && event.target.files[0]) saveFile(event.target.files[0]);
  });
  $("audio-retry").addEventListener("click", () => {
    if (busy()) return;
    files[step] = null;
    hideResult();
    $("audio-file").value = "";
    showPreview();
    render();
    status("Previous clip cleared. Record it again or choose a file.");
  });
  $("audio-prev").addEventListener("click", () => changeStep(step - 1));
  $("audio-next").addEventListener("click", () => {
    if (files[step]) changeStep(step + 1);
  });
  $("audio-astronaut").addEventListener("change", render);
  async function loadAstronauts() {
    rosterReady = false;
    $("audio-roster-retry").hidden = true;
    $("audio-roster-status").textContent = "Loading available astronauts…";
    render();
    try {
      const response = await fetch("/api/dashboard", {cache:"no-store", signal:AbortSignal.timeout(10000)});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const dashboard = await response.json();
      if (dashboard.mode !== "live") throw new Error("Audio submissions require the database crew roster.");
      $("audio-astronaut").replaceChildren(
        new Option("Select an astronaut", ""),
        ...dashboard.crew.map(member => new Option(`${member.name} · ${member.id}`, member.id))
      );
      rosterReady = dashboard.crew.length > 0;
      $("audio-roster-status").textContent = rosterReady ? "" : "No astronauts available in the database.";
      $("audio-roster-retry").hidden = rosterReady;
    } catch (error) {
      $("audio-astronaut").replaceChildren(new Option("Astronauts unavailable", ""));
      $("audio-roster-status").textContent = `Could not load astronauts: ${error.message}`;
      $("audio-roster-retry").hidden = false;
    }
    render();
  }
  $("audio-roster-retry").addEventListener("click", loadAstronauts);

  $("audio-send").addEventListener("click", async () => {
    if (busy() || !allReady()) return;
    const astronautId = $("audio-astronaut").value.trim();
    if (!astronautId) {
      status("Select an astronaut before submitting. Your five recordings are still saved on this page.");
      $("audio-astronaut").focus();
      $("audio-astronaut").scrollIntoView({behavior:"smooth", block:"center"});
      $("audio-astronaut").reportValidity();
      return;
    }
    if (totalBytes() > MAX_BYTES) { status("All recordings together must fit within 10 MiB."); return; }
    const form = new FormData();
    form.append("astronaut_id", astronautId);
    TASKS.forEach((task, i) => form.append(task.field, files[i], files[i].name));
    submitting = true;
    hideResult();
    render();
    status("Submitting all five recordings for analysis...");
    try {
      const response = await fetch("/api/audio", { method: "POST", body: form, signal: AbortSignal.timeout(120000) });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = payload?.detail;
        throw new Error(typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `HTTP ${response.status}`);
      }
      const result = payload?.result ?? payload;
      if (result?.status === "rejected") {
        const guidance = {
          clipping: "Move the microphone farther away or lower the input gain.",
          low_snr: "Find a quieter place and try again.",
          vowel_too_short: "Hold each vowel for at least 5 seconds.",
          too_little_speech: "Count all the way to 20 and hold the vowel sounds longer."
        };
        $("audio-result-title").textContent = "Recording needs attention";
        const advice = result.advice || guidance[result.reason] ||
          "Please review and retry the recordings.";

        $("audio-result-message").textContent = [
          result.log_message || "The audio could not be analyzed.",
          advice
        ].filter(Boolean).join(" ");
        $("audio-result").hidden = false;
        status("The model rejected the recording quality. You can retry individual clips.");
      } else if (result?.status === "ok") {
        $("audio-result-title").textContent = "Assessment submitted";
        $("audio-result-message").textContent = `${result.log_message || "Audio analysis completed."} Results are research-only and are not a diagnosis.`;
        $("audio-result").hidden = false;
        status("All five recordings were analyzed successfully.");
      } else {
        throw new Error("The server did not return an analysis status. Check that the updated audio API is deployed.");
      }
    } catch (error) {
      status(error.name === "TimeoutError" ? "Analysis timed out after two minutes. The server may still finish processing; check the dashboard before submitting again." : `Could not complete assessment: ${error.message}`);
    } finally {
      submitting = false;
      render();
    }
  });

  window.addEventListener("pagehide", () => {
    stopTimer();
    if (recorder?.state === "recording") recorder.stop();
    stopMic();
    closePreview();
  });
  render();
  showPreview();
  loadAstronauts();
})();
