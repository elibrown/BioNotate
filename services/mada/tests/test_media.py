from __future__ import annotations

import io
import wave

import av
import numpy as np
import pytest

from mada_agent.media import MediaError, decode_audio


def _webm_opus(seconds: float) -> bytes:
    buf = io.BytesIO()
    with av.open(buf, "w", format="webm") as out:
        stream = out.add_stream("libopus", rate=48000, layout="mono")
        t = np.arange(int(seconds * 48000)) / 48000
        pcm = (0.3 * np.sin(2 * np.pi * 300 * t) * 32767).astype(np.int16).reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(pcm, format="s16", layout="mono")
        frame.sample_rate = 48000
        for pkt in stream.encode(frame):
            out.mux(pkt)
        for pkt in stream.encode(None):
            out.mux(pkt)
    return buf.getvalue()


def test_browser_webm_opus_converts_to_16k_mono_wav():
    wav, secs = decode_audio(_webm_opus(3.0), "audio/webm;codecs=opus", max_s=30)
    w = wave.open(io.BytesIO(wav))
    assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
    assert 2.8 < secs < 3.3


def test_corrupt_audio_is_400():
    with pytest.raises(MediaError) as e:
        decode_audio(b"\x00" * 1000, "audio/webm", max_s=30)
    assert e.value.status_code == 400
