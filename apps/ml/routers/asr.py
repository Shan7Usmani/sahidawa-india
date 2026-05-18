from fastapi import APIRouter, UploadFile, File, HTTPException
import noisereduce as nr
import numpy as np
import tempfile
import warnings
import soundfile as sf
import logging
import os

from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/asr", tags=["ASR"])

logger.info("Loading Whisper model...")
model = WhisperModel("medium", device="cpu", compute_type="int8")
logger.info("Whisper model loaded ✅")


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Accepts an audio file upload.
    Returns transcribed text in the detected language + language code.
    """
    allowed_types = [
        "audio/wav", "audio/x-wav", "audio/mpeg",
        "audio/ogg", "audio/mp4", "audio/webm", "audio/flac"
    ]

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="File uploaded is not a supported audio format."
        )

    try:
        contents = await file.read()

        suffix = os.path.splitext(file.filename)[-1] or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        audio_data, sample_rate = sf.read(tmp_path)

        # Convert stereo to mono if needed
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        audio_data = audio_data.astype(np.float32)

        # Noise reduction (same logic as test_whisper.py)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            reduced_audio = nr.reduce_noise(y=audio_data, sr=sample_rate)
            
            
        segments, info = model.transcribe(
            reduced_audio,
            language=None,
            task="transcribe",
            beam_size=8,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=300,
                speech_pad_ms=400,
                threshold=0.3
            )
        )

        transcript = " ".join(seg.text for seg in segments).strip()

        logger.info(f"Transcription complete. Detected language: {info.language}, length: {len(transcript)}")

        return {
            "transcription": transcript,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "filename": file.filename
        }

    except Exception as e:
        logger.error(f"ASR error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to transcribe audio: {str(e)}")

    finally:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)