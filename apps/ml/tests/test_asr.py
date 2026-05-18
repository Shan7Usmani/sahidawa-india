import pytest
import io
import wave
import numpy as np
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import app

client = TestClient(app)


# ── Helper: generate a silent WAV in memory (no real audio file needed) ──────

def make_silent_wav(duration_seconds: int = 2, sample_rate: int = 16000) -> bytes:
    """Creates a valid WAV file with silence — enough for Whisper to accept."""
    buffer = io.BytesIO()
    samples = np.zeros(int(sample_rate * duration_seconds), dtype=np.int16)
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return buffer.getvalue()


# ── 1. Router registration ────────────────────────────────────────────────────

def test_asr_router_registered():
    """Confirms /asr/transcribe exists and is reachable (not 404)."""
    wav_bytes = make_silent_wav()
    response = client.post(
        "/asr/transcribe",
        files={"file": ("test.wav", wav_bytes, "audio/wav")}
    )
    assert response.status_code != 404, "/asr/transcribe route not registered in main.py"


# ── 2. Response shape ─────────────────────────────────────────────────────────

def test_response_has_required_fields():
    """Acceptance criteria: must return transcription + language code."""
    wav_bytes = make_silent_wav()
    response = client.post(
        "/asr/transcribe",
        files={"file": ("test.wav", wav_bytes, "audio/wav")}
    )
    assert response.status_code == 200
    data = response.json()

    assert "transcription" in data,        "Missing field: transcription"
    assert "language" in data,             "Missing field: language"
    assert "language_probability" in data, "Missing field: language_probability"
    assert "filename" in data,             "Missing field: filename"


def test_transcription_is_string():
    wav_bytes = make_silent_wav()
    response = client.post(
        "/asr/transcribe",
        files={"file": ("test.wav", wav_bytes, "audio/wav")}
    )
    data = response.json()
    assert isinstance(data["transcription"], str)


def test_language_probability_in_range():
    wav_bytes = make_silent_wav()
    response = client.post(
        "/asr/transcribe",
        files={"file": ("test.wav", wav_bytes, "audio/wav")}
    )
    prob = response.json()["language_probability"]
    assert 0.0 <= prob <= 1.0, f"language_probability out of range: {prob}"


def test_filename_echoed_back():
    wav_bytes = make_silent_wav()
    response = client.post(
        "/asr/transcribe",
        files={"file": ("my_audio.wav", wav_bytes, "audio/wav")}
    )
    assert response.json()["filename"] == "my_audio.wav"


# ── 3. Input validation ───────────────────────────────────────────────────────

def test_rejects_non_audio_file():
    """Must return 400 for non-audio content types."""
    fake = io.BytesIO(b"not audio")
    response = client.post(
        "/asr/transcribe",
        files={"file": ("notes.txt", fake, "text/plain")}
    )
    assert response.status_code == 400

def test_rejects_image_file():
    fake = io.BytesIO(b"\xff\xd8\xff")  # JPEG magic bytes
    response = client.post(
        "/asr/transcribe",
        files={"file": ("photo.jpg", fake, "image/jpeg")}
    )
    assert response.status_code == 400

def test_missing_file_returns_422():
    """FastAPI returns 422 if required field is absent."""
    response = client.post("/asr/transcribe")
    assert response.status_code == 422


# ── 4. Accepted audio content types ──────────────────────────────────────────

@pytest.mark.parametrize("content_type", [
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/ogg",
    "audio/webm",
])
def test_accepted_audio_types(content_type):
    """All declared audio types should pass validation (not return 400)."""
    wav_bytes = make_silent_wav()
    response = client.post(
        "/asr/transcribe",
        files={"file": ("audio.wav", wav_bytes, content_type)}
    )
    # 200 or 500 (model may fail on silent audio) — but NOT 400
    assert response.status_code != 400, \
        f"Content type {content_type} was incorrectly rejected"


# ── 5. Health check (confirms server is up) ───────────────────────────────────

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


# ── 6. Real audio fixtures (run only if files exist) ─────────────────────────

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

@pytest.mark.skipif(
    not os.path.exists(os.path.join(FIXTURES_DIR, "hindi_sample.wav")),
    reason="Hindi fixture not found"
)
def test_hindi_language_detection():
    with open(os.path.join(FIXTURES_DIR, "hindi_sample.wav"), "rb") as f:
        response = client.post(
            "/asr/transcribe",
            files={"file": ("hindi_sample.wav", f, "audio/wav")}
        )
    assert response.status_code == 200
    assert response.json()["language"] in ["hi", "ur"], \
    f"Expected hi or ur, got: {response.json()['language']}"

@pytest.mark.skipif(
    not os.path.exists(os.path.join(FIXTURES_DIR, "tamil_sample.wav")),
    reason="Tamil fixture not found"
)
def test_tamil_language_detection():
    with open(os.path.join(FIXTURES_DIR, "tamil_sample.wav"), "rb") as f:
        response = client.post(
            "/asr/transcribe",
            files={"file": ("tamil_sample.wav", f, "audio/wav")}
        )
    assert response.status_code == 200
    assert response.json()["language"] == "ta"

@pytest.mark.skipif(
    not os.path.exists(os.path.join(FIXTURES_DIR, "bengali_sample.wav")),
    reason="Bengali fixture not found"
)
def test_bengali_language_detection():
    with open(os.path.join(FIXTURES_DIR, "bengali_sample.wav"), "rb") as f:
        response = client.post(
            "/asr/transcribe",
            files={"file": ("bengali_sample.wav", f, "audio/wav")}
        )
    assert response.status_code == 200
    assert response.json()["language"] == "bn"