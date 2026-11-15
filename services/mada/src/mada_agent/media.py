"""Image and audio preparation for the model server.

Images are downscaled to `max_px` on the long edge and re-encoded as JPEG data URIs. Audio of any
format PyAV can decode (WAV, WebM/Opus, Ogg/Opus, MP3, M4A) is converted to 16 kHz mono 16-bit WAV.
Nothing is written to disk.
"""

from __future__ import annotations

import base64
import io
import wave

import numpy as np

AUDIO_RATE = 16_000
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "image/bmp", "image/gif"}
AUDIO_TYPES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/webm", "video/webm", "audio/ogg",
               "audio/opus", "audio/mpeg", "audio/mp3", "audio/mp4", "audio/x-m4a", "audio/aac"}


class MediaError(ValueError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _base_type(content_type: str | None) -> str:
    return (content_type or "").split(";")[0].strip().lower()


def prepare_image(data: bytes, content_type: str | None, max_px: int) -> str:
    """Return a JPEG data URI no larger than max_px on its long edge."""
    from PIL import Image, UnidentifiedImageError

    ctype = _base_type(content_type)
    if ctype and ctype not in IMAGE_TYPES and ctype != "application/octet-stream":
        raise MediaError(415, f"unsupported image type {ctype!r}; send JPEG, PNG or WebP")
    if not data:
        raise MediaError(400, "image file is empty")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaError(400, "image could not be decoded") from exc
    img = img.convert("RGB")
    img.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def decode_audio(data: bytes, content_type: str | None, max_s: float) -> tuple[bytes, float]:
    """Decode any supported audio to 16 kHz mono 16-bit WAV bytes. Returns (wav_bytes, seconds)."""
    import av

    ctype = _base_type(content_type)
    if ctype and ctype not in AUDIO_TYPES and ctype != "application/octet-stream":
        raise MediaError(415, f"unsupported audio type {ctype!r}; send WAV, WebM/Opus or Ogg/Opus")
    if not data:
        raise MediaError(400, "audio file is empty")
    chunks: list[np.ndarray] = []
    n = 0
    limit = int((max_s + 0.5) * AUDIO_RATE)
    try:
        with av.open(io.BytesIO(data)) as container:
            if not container.streams.audio:
                raise MediaError(400, "file has no audio track")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=AUDIO_RATE)
            for frame in container.decode(audio=0):
                for out in resampler.resample(frame):
                    arr = out.to_ndarray().reshape(-1)
                    chunks.append(arr)
                    n += arr.size
                    if n > limit:
                        raise MediaError(413, f"audio is longer than {max_s:.0f} s")
            for out in resampler.resample(None):
                arr = out.to_ndarray().reshape(-1)
                chunks.append(arr)
                n += arr.size
    except MediaError:
        raise
    except Exception as exc:  # PyAV raises many error types for corrupt input
        raise MediaError(400, "audio could not be decoded") from exc
    if n > limit:
        raise MediaError(413, f"audio is longer than {max_s:.0f} s")
    if n == 0:
        raise MediaError(400, "audio contains no samples")
    pcm = np.concatenate(chunks).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(AUDIO_RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue(), n / AUDIO_RATE


def wav_base64(wav: bytes) -> str:
    return base64.b64encode(wav).decode()
