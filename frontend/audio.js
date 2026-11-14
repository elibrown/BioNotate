"use strict";
(() => {
  const $ = id => document.getElementById(id);
  let audioFile, recorder, stream, previewURL;
  function selectAudio(file) {
    audioFile = file;
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = URL.createObjectURL(file);
    $('audio-preview').src = previewURL;
    $('audio-preview').hidden = false;
    $('audio-send').disabled = false;
    $('audio-status').textContent = 'Ready to save. No audio analysis is performed yet.';
  }
  $('audio-file').addEventListener('change', event => {
    if (event.target.files[0]) selectAudio(event.target.files[0]);
  });
  $('record').addEventListener('click', async () => {
    try {
      if (!navigator.mediaDevices || !window.MediaRecorder) throw new Error('Microphone recording requires a supported browser on localhost or HTTPS.');
      stream = await navigator.mediaDevices.getUserMedia({audio:true});
      recorder = new MediaRecorder(stream);
      const chunks = [];
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => {
        const type = recorder.mimeType;
        const extension = type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm';
        selectAudio(new File(chunks, `recording.${extension}`, {type}));
        stream.getTracks().forEach(track => track.stop());
        $('record').disabled = false; $('stop').disabled = true; $('audio-file').disabled = false;
      };
      recorder.start();
      $('record').disabled = true; $('stop').disabled = false;
      $('audio-file').disabled = true; $('audio-send').disabled = true;
      $('audio-status').textContent = 'Recording… press Stop recording when finished.';
    } catch (error) {
      stream?.getTracks().forEach(track => track.stop());
      $('audio-status').textContent = error.message;
    }
  });
  $('stop').addEventListener('click', () => { if (recorder?.state === 'recording') recorder.stop(); });
  $('audio-send').addEventListener('click', async () => {
    if (!audioFile) return;
    if (audioFile.size > 20 * 1024 * 1024) { $('audio-status').textContent = 'Audio must be at most 20 MiB.'; return; }
    const form = new FormData(); form.append('file', audioFile);
    const astronaut = $('audio-astronaut').value.trim();
    if (astronaut) form.append('astronaut_id', astronaut);
    $('audio-send').disabled = true;
    $('audio-status').textContent = 'Saving audio…';
    try {
      const response = await fetch('/api/audio', {method:'POST', body:form});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      $('audio-status').textContent = `Audio saved (${data.size_bytes} bytes). Audio analysis is not connected yet.`;
    } catch (error) { $('audio-status').textContent = `Could not save: ${error.message}`; }
    finally { $('audio-send').disabled = false; }
  });
  window.addEventListener('pagehide', () => {
    stream?.getTracks().forEach(track => track.stop());
    if (previewURL) URL.revokeObjectURL(previewURL);
  });
})();
