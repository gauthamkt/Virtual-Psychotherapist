"""
stt_handler.py – Speech-to-Text handler for the offline psychotherapist app.

Provides two transcription engines:
  • **Whisper** (primary) — OpenAI's open-source model for high-accuracy
    offline transcription with language auto-detection.
  • **Vosk** (fallback) — lightweight, low-memory alternative for
    resource-constrained environments.

Audio pre-processing pipeline:
  1. Format conversion (webm/mp3/ogg → wav via pydub)
  2. Resample to 16 kHz mono
  3. Amplitude normalisation
  4. Silence removal via WebRTC VAD

Usage:
    from stt_handler import transcribe_audio, transcribe_stream

    result = transcribe_audio("recording.webm")
    # {"transcript": "...", "confidence": 0.94, "language": "en", "duration": 3.2}

    text = transcribe_stream(raw_audio_bytes)
"""

from __future__ import annotations

import io
import json
import logging
import os
import struct
import tempfile
import wave
from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUPPORTED_FORMATS: set[str] = {"webm", "wav", "mp3", "ogg"}
TARGET_SAMPLE_RATE: int = 16_000
TARGET_CHANNELS: int = 1
TARGET_SAMPLE_WIDTH: int = 2  # 16-bit

MIN_DURATION_SEC: float = 0.5
MAX_DURATION_WARN_SEC: float = 120.0

WHISPER_MODEL_SIZE: str = "base"  # "base" or "small"

# ---------------------------------------------------------------------------
# Lazy-loaded model caches
# ---------------------------------------------------------------------------
_whisper_model: Any = None
_vosk_model: Any = None


# ========================== PUBLIC FUNCTIONS ===============================

def transcribe_audio(
    file_path: str,
    engine: str = "whisper",
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Transcribe an audio file to text.

    Args:
        file_path: Path to the audio file (webm, wav, mp3, or ogg).
        engine:    Transcription engine — ``"whisper"`` (default) or ``"vosk"``.
        language:  Force a specific language (e.g. ``"en"``). If ``None``,
                   the engine auto-detects the language.

    Returns:
        A dict with keys:
            - ``transcript``  (str):   The transcribed text.
            - ``confidence``  (float): Estimated confidence [0.0–1.0].
            - ``language``    (str):   Detected / forced language code.
            - ``duration``    (float): Audio duration in seconds.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        ValueError:        If the format is unsupported or duration is too short.
        RuntimeError:      If the chosen engine is unavailable.
    """
    # --- Validate file ---
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    ext: str = _get_extension(file_path)
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported audio format '.{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"
        )

    logger.info("Transcribing '%s' with engine='%s'", file_path, engine)

    try:
        # --- Convert / pre-process ---
        try:
            wav_path: str = _preprocess_audio(file_path)
        except Exception as exc:
            logger.error("Audio pre-processing failed: %s", exc)
            return {
                "transcript": "[Error: Audio processing failed. Ensure FFmpeg is installed.]",
                "confidence": 0.0,
                "language": language or "unknown",
                "duration": 0.0,
            }

        # --- Duration validation ---
        duration: float = _get_wav_duration(wav_path)
        if duration < MIN_DURATION_SEC:
            logger.warning("Audio too short (%.2f s). Minimum is %.1f s.", duration, MIN_DURATION_SEC)
            return {
                "transcript": "",
                "confidence": 0.0,
                "language": language or "unknown",
                "duration": duration,
            }
        if duration > MAX_DURATION_WARN_SEC:
            logger.warning(
                "Audio is very long (%.1f s > %.0f s). Transcription may be slow.",
                duration, MAX_DURATION_WARN_SEC,
            )

        # --- Dispatch to engine ---
        if engine.lower() == "whisper":
            result = _transcribe_whisper(wav_path, language)
        elif engine.lower() == "vosk":
            result = _transcribe_vosk(wav_path, language)
        else:
            raise ValueError(f"Unknown engine '{engine}'. Use 'whisper' or 'vosk'.")

        result["duration"] = round(duration, 2)
        return result

    finally:
        # Clean up temp WAV if we created one
        if wav_path != file_path and os.path.exists(wav_path):
            os.unlink(wav_path)


def transcribe_stream(
    audio_bytes: bytes,
    engine: str = "whisper",
    language: Optional[str] = None,
) -> str:
    """
    Transcribe raw audio bytes (e.g. from a real-time stream or WebSocket).

    The bytes are written to a temporary WAV file, pre-processed,
    and then sent through the chosen engine.

    Args:
        audio_bytes: Raw audio data (assumed 16-bit PCM, 16 kHz, mono
                     unless a valid WAV/RIFF header is present).
        engine:      ``"whisper"`` (default) or ``"vosk"``.
        language:    Optional forced language code.

    Returns:
        The transcribed text as a plain string.
    """
    if not audio_bytes or len(audio_bytes) < 44:
        logger.warning("Received empty or near-empty audio stream.")
        return ""

    # Write bytes to a temp file so we can reuse transcribe_audio()
    suffix: str = ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path: str = tmp.name

        # If bytes don't start with RIFF header, wrap in a WAV container
        if audio_bytes[:4] != b"RIFF":
            _write_raw_pcm_as_wav(tmp, audio_bytes)
        else:
            tmp.write(audio_bytes)

    try:
        result: Dict[str, Any] = transcribe_audio(tmp_path, engine=engine, language=language)
        return result.get("transcript", "")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def is_audio_valid(file_path: str) -> bool:
    """
    Quick check to see if a file appears to be a valid, supported audio file.

    Args:
        file_path: Path to the file.

    Returns:
        ``True`` if the file exists, has a supported extension, and is non-empty.
    """
    if not os.path.isfile(file_path):
        return False
    if os.path.getsize(file_path) == 0:
        return False
    return _get_extension(file_path) in SUPPORTED_FORMATS


# ========================== WHISPER ENGINE ================================

def _load_whisper_model() -> Any:
    """Lazy-load the Whisper model (cached after first call)."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    try:
        import whisper  # type: ignore[import-untyped]
        logger.info("Loading Whisper model '%s'…", WHISPER_MODEL_SIZE)
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
        logger.info("Whisper model loaded successfully.")
        return _whisper_model
    except ImportError:
        raise RuntimeError(
            "Whisper is not installed. Install with: pip install openai-whisper"
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to load Whisper model: {exc}") from exc


def _transcribe_whisper(
    wav_path: str,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run Whisper transcription on a pre-processed WAV file.

    Args:
        wav_path: Path to the 16 kHz mono WAV file.
        language: Optional forced language code.

    Returns:
        Dict with ``transcript``, ``confidence``, and ``language``.
    """
    model = _load_whisper_model()

    options: Dict[str, Any] = {"fp16": False}
    if language:
        options["language"] = language

    try:
        result: Dict[str, Any] = model.transcribe(wav_path, **options)
    except Exception as exc:
        logger.error("Whisper transcription failed: %s", exc)
        return {"transcript": "", "confidence": 0.0, "language": language or "unknown"}

    transcript: str = result.get("text", "").strip()
    detected_language: str = result.get("language", language or "unknown")

    # Estimate confidence from segment-level probabilities
    segments: List[Dict[str, Any]] = result.get("segments", [])
    confidence: float = _estimate_whisper_confidence(segments)

    # Reject noise-only / very low confidence output
    if confidence < 0.25 or not transcript:
        logger.info("Transcript appears to be noise (confidence=%.2f).", confidence)
        return {
            "transcript": "",
            "confidence": confidence,
            "language": detected_language,
        }

    return {
        "transcript": transcript,
        "confidence": round(confidence, 3),
        "language": detected_language,
    }


def _estimate_whisper_confidence(segments: List[Dict[str, Any]]) -> float:
    """
    Compute a weighted-average confidence from Whisper segment data.

    Each segment has ``avg_logprob`` and ``no_speech_prob``.
    """
    if not segments:
        return 0.0

    total_weight: float = 0.0
    weighted_conf: float = 0.0

    for seg in segments:
        duration: float = seg.get("end", 0) - seg.get("start", 0)
        if duration <= 0:
            continue

        avg_logprob: float = seg.get("avg_logprob", -1.0)
        no_speech: float = seg.get("no_speech_prob", 0.5)

        # Convert log-prob to a 0-1 scale (logprob is typically -1 to 0)
        seg_confidence: float = max(0.0, min(1.0, 1.0 + avg_logprob))
        # Penalise high no-speech probability
        seg_confidence *= (1.0 - no_speech)

        weighted_conf += seg_confidence * duration
        total_weight += duration

    return weighted_conf / total_weight if total_weight > 0 else 0.0


# ========================== VOSK ENGINE ===================================

def _load_vosk_model() -> Any:
    """Lazy-load the Vosk model (cached after first call)."""
    global _vosk_model
    if _vosk_model is not None:
        return _vosk_model

    try:
        from vosk import Model, SetLogLevel  # type: ignore[import-untyped]
        SetLogLevel(-1)  # suppress Vosk's verbose logging

        # Vosk expects a model directory – try common locations
        model_paths: List[str] = [
            os.path.join(os.path.dirname(__file__), "vosk-model"),
            os.path.join(os.path.dirname(__file__), "model"),
            os.path.expanduser("~/.vosk/model"),
        ]

        for path in model_paths:
            if os.path.isdir(path):
                logger.info("Loading Vosk model from '%s'…", path)
                _vosk_model = Model(path)
                logger.info("Vosk model loaded successfully.")
                return _vosk_model

        raise FileNotFoundError(
            "No Vosk model directory found. Download a model from "
            "https://alphacephei.com/vosk/models and place it in one of: "
            f"{model_paths}"
        )
    except ImportError:
        raise RuntimeError(
            "Vosk is not installed. Install with: pip install vosk"
        )


def _transcribe_vosk(
    wav_path: str,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run Vosk transcription on a pre-processed WAV file.

    Args:
        wav_path: Path to the 16 kHz mono WAV file.
        language: Ignored for Vosk (model determines language).

    Returns:
        Dict with ``transcript``, ``confidence``, and ``language``.
    """
    from vosk import KaldiRecognizer  # type: ignore[import-untyped]

    model = _load_vosk_model()
    recognizer = KaldiRecognizer(model, TARGET_SAMPLE_RATE)
    recognizer.SetWords(True)

    transcript_parts: List[str] = []
    confidences: List[float] = []

    try:
        with wave.open(wav_path, "rb") as wf:
            while True:
                data: bytes = wf.readframes(4000)
                if len(data) == 0:
                    break
                if recognizer.AcceptWaveform(data):
                    partial: Dict[str, Any] = json.loads(recognizer.Result())
                    text: str = partial.get("text", "").strip()
                    if text:
                        transcript_parts.append(text)
                        # Extract word-level confidence
                        for word_info in partial.get("result", []):
                            confidences.append(word_info.get("conf", 0.0))

        # Final result
        final: Dict[str, Any] = json.loads(recognizer.FinalResult())
        final_text: str = final.get("text", "").strip()
        if final_text:
            transcript_parts.append(final_text)
            for word_info in final.get("result", []):
                confidences.append(word_info.get("conf", 0.0))

    except Exception as exc:
        logger.error("Vosk transcription failed: %s", exc)
        return {"transcript": "", "confidence": 0.0, "language": "en"}

    transcript: str = " ".join(transcript_parts).strip()
    avg_confidence: float = (
        sum(confidences) / len(confidences) if confidences else 0.0
    )

    return {
        "transcript": transcript,
        "confidence": round(avg_confidence, 3),
        "language": "en",  # Vosk model determines language at load time
    }


# ========================== AUDIO PRE-PROCESSING ==========================

def _get_extension(file_path: str) -> str:
    """Extract the lowercase file extension without the dot."""
    return file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""


def _preprocess_audio(file_path: str) -> str:
    """
    Full pre-processing pipeline:
      1. Convert to WAV (if needed) via pydub
      2. Resample to 16 kHz mono
      3. Normalise amplitude
      4. Remove silence with WebRTC VAD

    Args:
        file_path: Path to the original audio file.

    Returns:
        Path to the pre-processed WAV (may be a temp file).
    """
    try:
        from pydub import AudioSegment  # type: ignore[import-untyped]
    except ImportError:
        logger.warning(
            "pydub is not installed — skipping format conversion. "
            "Install with: pip install pydub"
        )
        return file_path

    ext: str = _get_extension(file_path)

    # --- Step 1: Load audio with pydub ---
    try:
        if ext == "wav":
            audio: AudioSegment = AudioSegment.from_wav(file_path)
        elif ext == "mp3":
            audio = AudioSegment.from_mp3(file_path)
        elif ext == "ogg":
            audio = AudioSegment.from_ogg(file_path)
        elif ext == "webm":
            audio = AudioSegment.from_file(file_path, format="webm")
        else:
            audio = AudioSegment.from_file(file_path)
    except Exception as exc:
        logger.error("Failed to load audio with pydub: %s", exc)
        if "ffprobe" in str(exc).lower() or "ffmpeg" in str(exc).lower():
            raise RuntimeError("FFmpeg/ffprobe not found. Required for non-WAV formats.") from exc
        raise exc

    # --- Step 2: Resample to 16 kHz mono ---
    audio = audio.set_frame_rate(TARGET_SAMPLE_RATE)
    audio = audio.set_channels(TARGET_CHANNELS)
    audio = audio.set_sample_width(TARGET_SAMPLE_WIDTH)

    # --- Step 3: Normalise amplitude ---
    audio = _normalize_audio(audio)

    # --- Step 4: Remove silence with VAD ---
    audio = _remove_silence_vad(audio)

    # --- Export to temp WAV ---
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path: str = tmp.name
    audio.export(tmp_path, format="wav")

    logger.info(
        "Pre-processed audio → %s (%.2f s, %d Hz, %d ch)",
        tmp_path,
        len(audio) / 1000.0,
        audio.frame_rate,
        audio.channels,
    )
    return tmp_path


def _normalize_audio(audio: Any) -> Any:
    """
    Normalise audio amplitude to a target of -20 dBFS.

    Args:
        audio: A pydub AudioSegment.

    Returns:
        The normalised AudioSegment.
    """
    target_dbfs: float = -20.0
    change_in_dbfs: float = target_dbfs - audio.dBFS
    return audio.apply_gain(change_in_dbfs)


def _remove_silence_vad(audio: Any) -> Any:
    """
    Remove silence / non-speech frames using WebRTC VAD.

    Falls back to pydub's simple silence removal if webrtcvad
    is not available.

    Args:
        audio: A pydub AudioSegment (16 kHz, mono, 16-bit).

    Returns:
        The AudioSegment with silence removed.
    """
    try:
        import webrtcvad  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("webrtcvad not installed — using pydub silence removal.")
        return _remove_silence_pydub(audio)

    vad = webrtcvad.Vad(2)  # aggressiveness 0-3 (2 = moderate)

    raw: bytes = audio.raw_data
    sample_rate: int = audio.frame_rate
    sample_width: int = audio.sample_width

    # VAD requires frames of 10, 20, or 30 ms
    frame_duration_ms: int = 30
    frame_size: int = int(sample_rate * frame_duration_ms / 1000) * sample_width
    voiced_frames: List[bytes] = []

    for i in range(0, len(raw) - frame_size + 1, frame_size):
        frame: bytes = raw[i : i + frame_size]
        try:
            if vad.is_speech(frame, sample_rate):
                voiced_frames.append(frame)
        except Exception:
            voiced_frames.append(frame)  # keep frame on error

    if not voiced_frames:
        logger.info("VAD removed all frames — audio appears to be silence/noise.")
        return audio  # return original to avoid empty audio

    from pydub import AudioSegment  # type: ignore[import-untyped]

    voiced_audio = AudioSegment(
        data=b"".join(voiced_frames),
        sample_width=sample_width,
        frame_rate=sample_rate,
        channels=TARGET_CHANNELS,
    )
    logger.info(
        "VAD: kept %.1f s of %.1f s (removed %.0f%% silence).",
        len(voiced_audio) / 1000.0,
        len(audio) / 1000.0,
        (1 - len(voiced_audio) / max(len(audio), 1)) * 100,
    )
    return voiced_audio


def _remove_silence_pydub(audio: Any) -> Any:
    """Fallback silence removal using pydub's built-in split_on_silence."""
    try:
        from pydub.silence import split_on_silence  # type: ignore[import-untyped]

        chunks = split_on_silence(
            audio,
            min_silence_len=500,   # ms
            silence_thresh=-40,    # dBFS
            keep_silence=200,      # ms padding
        )
        if not chunks:
            return audio

        from pydub import AudioSegment  # type: ignore[import-untyped]
        combined: AudioSegment = chunks[0]
        for chunk in chunks[1:]:
            combined += chunk
        return combined

    except Exception as exc:
        logger.debug("pydub silence removal failed: %s", exc)
        return audio


def _get_wav_duration(wav_path: str) -> float:
    """
    Get the duration of a WAV file in seconds.

    Args:
        wav_path: Path to the WAV file.

    Returns:
        Duration in seconds.
    """
    try:
        with wave.open(wav_path, "rb") as wf:
            frames: int = wf.getnframes()
            rate: int = wf.getframerate()
            return frames / float(rate) if rate > 0 else 0.0
    except Exception as exc:
        logger.warning("Could not read WAV duration: %s", exc)
        return 0.0


def _write_raw_pcm_as_wav(fp: Any, pcm_data: bytes) -> None:
    """
    Wrap raw 16-bit PCM bytes in a valid WAV container.

    Args:
        fp:       Open file handle to write to.
        pcm_data: Raw 16-bit signed PCM samples (16 kHz mono assumed).
    """
    num_channels: int = TARGET_CHANNELS
    sample_width: int = TARGET_SAMPLE_WIDTH
    frame_rate: int = TARGET_SAMPLE_RATE
    num_frames: int = len(pcm_data) // (num_channels * sample_width)

    with wave.open(fp, "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(frame_rate)
        wf.writeframes(pcm_data)


# ========================== MICROPHONE TEST ===============================

def test_microphone(duration_sec: int = 5, engine: str = "whisper") -> Dict[str, Any]:
    """
    Record audio from the default microphone for *duration_sec* seconds,
    then transcribe it — useful for quick integration testing.

    Args:
        duration_sec: How many seconds to record (default 5).
        engine:       ``"whisper"`` or ``"vosk"``.

    Returns:
        The transcription result dict.

    Requires:
        ``pip install sounddevice soundfile``
    """
    try:
        import sounddevice as sd  # type: ignore[import-untyped]
        import soundfile as sf    # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError(
            "Microphone test requires sounddevice and soundfile. "
            "Install with: pip install sounddevice soundfile"
        )

    logger.info("🎙️  Recording %d seconds from microphone…", duration_sec)
    print(f"🎙️  Recording for {duration_sec} seconds — speak now!")

    audio_data: np.ndarray = sd.rec(
        int(duration_sec * TARGET_SAMPLE_RATE),
        samplerate=TARGET_SAMPLE_RATE,
        channels=TARGET_CHANNELS,
        dtype="int16",
    )
    sd.wait()
    print("✅  Recording complete. Transcribing…")

    # Save to temp WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path: str = tmp.name
    sf.write(tmp_path, audio_data, TARGET_SAMPLE_RATE)

    try:
        result: Dict[str, Any] = transcribe_audio(tmp_path, engine=engine)
        print(f"\n📝  Transcript : {result['transcript']}")
        print(f"🎯  Confidence : {result['confidence']:.1%}")
        print(f"🌐  Language   : {result['language']}")
        print(f"⏱️   Duration   : {result['duration']:.2f} s")
        return result
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ========================== MAIN (for quick testing) ======================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Transcribe a file passed as argument
        path: str = sys.argv[1]
        eng: str = sys.argv[2] if len(sys.argv) > 2 else "whisper"
        result = transcribe_audio(path, engine=eng)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # Run microphone test
        test_microphone()
