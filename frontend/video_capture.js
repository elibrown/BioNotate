/* Local webcam recorder for Model 1. The existing upload flow handles the resulting File. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const startButton = $('camera-start');
  const stopButton = $('camera-stop');
  const preview = $('camera-preview');
  const status = $('camera-status');
  const timer = $('camera-timer');
  const fileInput = $('video');
  if (!startButton || !stopButton || !preview || !status || !timer || !fileInput) return;

  const MIN_SECONDS = 30;
  const MAX_SECONDS = 120;
  let stream = null;
  let recorder = null;
  let ticker = null;
  let startedAt = 0;
  let playbackUrl = null;
  window.astroRecordedVideo = null;

  function show(message) { status.textContent = message; }
  function formatSeconds(total) {
    const s = Math.max(0, Math.floor(total));
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  }
  function stopTracks() {
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
  }
  function clearPlayback() {
    if (playbackUrl) URL.revokeObjectURL(playbackUrl);
    playbackUrl = null;
    preview.pause();
    preview.srcObject = null;
    preview.removeAttribute('src');
    preview.hidden = true;
    preview.controls = false;
  }
  function stopTimer() {
    if (ticker) clearInterval(ticker);
    ticker = null;
  }
  function stopRecording() {
    if (recorder && recorder.state === 'recording') recorder.stop();
    stopTimer();
    startButton.disabled = false;
    stopButton.disabled = true;
  }

  startButton.addEventListener('click', async () => {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      show('Your browser cannot record video here. Open this page on localhost in Chrome or Edge, or upload a file.');
      return;
    }
    const mimeType = [
      'video/webm;codecs=vp8', 'video/webm;codecs=vp9',
      'video/webm', 'video/mp4'
    ].find(type => MediaRecorder.isTypeSupported(type));
    if (!mimeType) {
      show('No supported recording format. Try Chrome or Edge, or upload a video file.');
      return;
    }
    startButton.disabled = true;
    window.astroRecordedVideo = null;
    clearPlayback();
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } },
        audio: false
      });
      preview.srcObject = stream;
      preview.muted = true;
      preview.autoplay = true;
      preview.playsInline = true;
      preview.hidden = false;
      await preview.play();

      const chunks = [];
      const active = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 2500000 });
      recorder = active;
      let recordingError = null;
      active.ondataavailable = event => { if (event.data && event.data.size) chunks.push(event.data); };
      active.onerror = event => { recordingError = event.error?.message || 'Recording failed.'; };
      active.onstop = () => {
        const elapsed = (Date.now() - startedAt) / 1000;
        stopTracks();
        stopTimer();
        startButton.disabled = false;
        stopButton.disabled = true;
        preview.pause();
        preview.srcObject = null;
        preview.autoplay = false;
        const actualType = active.mimeType || mimeType;
        const extension = actualType.includes('mp4') ? 'mp4' : 'webm';
        const blob = new Blob(chunks, { type: actualType });
        if (recordingError || blob.size === 0) {
          preview.hidden = true;
          show(recordingError || 'The video is empty. Please try recording again.');
          return;
        }
        playbackUrl = URL.createObjectURL(blob);
        preview.src = playbackUrl;
        preview.controls = true;
        preview.hidden = false;
        preview.load();
        if (elapsed < MIN_SECONDS) {
          show(`Only ${Math.floor(elapsed)} seconds recorded. Model 1 needs at least 30 seconds of usable footage. Please record again.`);
          return;
        }
        const clip = new File([blob], `camera-${Date.now()}.${extension}`, { type: actualType });
        window.astroRecordedVideo = clip;
        fileInput.value = '';
        show(`Video ready: ${Math.round(blob.size / 1048576 * 10) / 10} MB, ${Math.floor(elapsed)} seconds. Choose an astronaut and click Upload.`);
      };
      active.start(1000);
      startedAt = Date.now();
      stopButton.disabled = false;
      show('Recording. Keep your face visible and reasonably still for at least 30 seconds (60 seconds recommended).');
      timer.textContent = `00:00 / ${formatSeconds(MAX_SECONDS)}`;
      ticker = setInterval(() => {
        const elapsed = (Date.now() - startedAt) / 1000;
        timer.textContent = `${formatSeconds(Math.min(elapsed, MAX_SECONDS))} / ${formatSeconds(MAX_SECONDS)}`;
        if (elapsed >= MAX_SECONDS) stopRecording();
      }, 250);
    } catch (error) {
      stopTimer();
      stopTracks();
      clearPlayback();
      startButton.disabled = false;
      stopButton.disabled = true;
      show(`Camera unavailable: ${error.message}. Allow camera access or upload an existing video.`);
    }
  });

  stopButton.addEventListener('click', stopRecording);
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) {
      window.astroRecordedVideo = null;
      if (!recorder || recorder.state === 'inactive') clearPlayback();
      show('Selected uploaded video file. Click Upload to analyze it.');
    }
  });
  window.addEventListener('pagehide', () => {
    stopTimer();
    if (recorder && recorder.state === 'recording') recorder.stop();
    stopTracks();
    if (playbackUrl) URL.revokeObjectURL(playbackUrl);
  });
})();
