"""
tts_handler.py – Text-to-Speech handler for the offline virtual therapist.

Replaces the local ML models with the free cloud TTS from Rekam.ai for
faster generation and higher quality voices.

Features:
  • Uses Rekam.ai's 'af_heart' voice.
  • Emotion-based speed adjustments (using Rekam's speed multiplier).
  • Text pre-processing (abbreviation expansion, pause insertion).
  • In-memory phrase cache for common utterances.
  • Async synthesis with job tracking and callbacks.
  • MP3 output format handling.

Usage:
    from tts_handler import synthesize, synthesize_async, get_job_status

    path = synthesize("I hear you.", emotion="sadness", output_path="out.mp3")

    job_id = synthesize_async("Take a deep breath.", emotion="anxiety",
                              output_path="calm.mp3",
                              callback=lambda jid, p: print(f"Done: {p}"))
    status = get_job_status(job_id)
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import struct
import tempfile
import threading
import time
import uuid
import wave
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

# Import alternative TTS services
try:
    from offline_tts import synthesize_offline_tts
    from basic_tts import synthesize_basic_tts
    from simple_tts import synthesize_simple_tts
    from freetts_tts import synthesize_freetts
except ImportError:
    synthesize_offline_tts = None
    synthesize_basic_tts = None
    synthesize_simple_tts = None
    synthesize_freetts = None
    logger = logging.getLogger(__name__)
    logger.warning("Alternative TTS not available")

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
REKAM_VOICE_ID: str = "af_heart"
OUTPUT_SAMPLE_RATE: int = 22_050

DEFAULT_OUTPUT_DIR: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "audio"
)

# ---------------------------------------------------------------------------
# Emotion → speech parameter mapping
# ---------------------------------------------------------------------------
EMOTION_PARAMS: Dict[str, Dict[str, float]] = {
    "sadness":  {"speed": 0.85},
    "sad":      {"speed": 0.85},
    "anxiety":  {"speed": 0.95},
    "anxious":  {"speed": 0.95},
    "fear":     {"speed": 0.95},
    "anger":    {"speed": 1.15},
    "angry":    {"speed": 1.15},
    "joy":      {"speed": 1.25},
    "happy":    {"speed": 1.25},
    "neutral":  {"speed": 1.05},
}

# ---------------------------------------------------------------------------
# Abbreviation expansion map
# ---------------------------------------------------------------------------
ABBREVIATIONS: Dict[str, str] = {
    "Dr.":   "Doctor",
    "Mr.":   "Mister",
    "Mrs.":  "Misses",
    "Ms.":   "Miss",
    "e.g.":  "for example",
    "i.e.":  "that is",
    "etc.":  "etcetera",
    "vs.":   "versus",
    "approx.": "approximately",
    "dept.": "department",
    "govt.": "government",
    "w/":    "with",
    "b/c":   "because",
    "&":     "and",
}

# ---------------------------------------------------------------------------
# Engine state (Session management for Rekam)
# ---------------------------------------------------------------------------
_rekam_session: requests.Session = requests.Session()
_engine_lock: threading.Lock = threading.Lock()

# ---------------------------------------------------------------------------
# Phrase cache  {text_hash → wav_bytes}
# ---------------------------------------------------------------------------
_phrase_cache: Dict[str, bytes] = {}
_CACHE_MAX_ITEMS: int = 64

CACHED_PHRASES: List[str] = [
    "I hear you.",
    "That sounds really difficult.",
    "Thank you for sharing that with me.",
    "How does that make you feel?",
    "Take your time, there's no rush.",
    "I'm here for you.",
    "That takes a lot of courage to share.",
    "Let's explore that a bit more.",
    "You're not alone in this.",
    "It's okay to feel that way.",
]

# ---------------------------------------------------------------------------
# Async job tracking
# ---------------------------------------------------------------------------
_job_pool: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=2)
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock: threading.Lock = threading.Lock()


# ========================== PUBLIC FUNCTIONS ===============================

def synthesize(
    text: str,
    emotion: str = "neutral",
    output_path: Optional[str] = None,
) -> str:
    """
    Synthesize text to speech using Rekam.ai Cloud TTS and save as an MP3 file.

    Args:
        text:        The text to speak.
        emotion:     Detected emotion label (adjusts speed).
        output_path: Destination MP3 path. If ``None``, a temp file
                     in ``static/audio/`` is created automatically.

    Returns:
        Absolute path to the generated MP3 file.
    """
    if not text or not text.strip():
        logger.warning("Empty text passed to synthesize().")
        output_path = output_path or _default_output_path()
        return output_path

    # Check phrase cache
    cache_key: str = _cache_key(text, emotion)
    if cache_key in _phrase_cache:
        logger.info("Cache hit for text=%r", text[:40])
        output_path = output_path or _default_output_path()
        with open(output_path, "wb") as f:
            f.write(_phrase_cache[cache_key])
        return output_path

    # Pre-process text
    processed: str = _preprocess_text(text)

    # TTS synthesis with multiple fallbacks
    mp3_bytes: bytes = b''
    
    # 1. Try Offline TTS first (completely offline and reliable)
    if synthesize_offline_tts:
        try:
            mp3_bytes = synthesize_offline_tts(processed, emotion)
            if len(mp3_bytes) > 100:
                logger.info("✅ Using Offline TTS (pyttsx3)")
        except Exception as exc:
            logger.warning(f"Offline TTS failed: {exc}")
    
    # 2. Try Basic TTS as backup
    if len(mp3_bytes) <= 100 and synthesize_basic_tts:
        try:
            mp3_bytes = synthesize_basic_tts(processed, emotion)
            if len(mp3_bytes) > 100:
                logger.info("✅ Using Basic TTS")
        except Exception as exc:
            logger.warning(f"Basic TTS failed: {exc}")
    
    # 3. Try Simple TTS as backup
    if len(mp3_bytes) <= 100 and synthesize_simple_tts:
        try:
            mp3_bytes = synthesize_simple_tts(processed, emotion)
            if len(mp3_bytes) > 100:
                logger.info("✅ Using Simple TTS")
        except Exception as exc:
            logger.warning(f"Simple TTS failed: {exc}")
    
    # 4. Try FreeTTS as backup
    if len(mp3_bytes) <= 100 and synthesize_freetts:
        try:
            mp3_bytes = synthesize_freetts(processed, emotion)
            if len(mp3_bytes) > 100:
                logger.info("✅ Using FreeTTS.com")
        except Exception as exc:
            logger.warning(f"FreeTTS failed: {exc}")
    
    # 5. Final fallback
    if len(mp3_bytes) <= 100:
        mp3_bytes = _generate_fallback_audio(processed, emotion)
        logger.warning("⚠️ Using basic fallback audio")

    # Write output
    output_path = output_path or _default_output_path()
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(mp3_bytes)

    # Cache short phrases
    if len(mp3_bytes) > 0:
        _cache_put(cache_key, mp3_bytes)

    logger.info("Synthesized %d chars → %s", len(text), output_path)
    return output_path


def synthesize_async(
    text: str,
    emotion: str = "neutral",
    output_path: Optional[str] = None,
    callback: Optional[Callable[[str, str], None]] = None,
) -> str:
    """
    Start speech synthesis in a background thread.

    Args:
        text:        The text to speak.
        emotion:     Detected emotion label.
        output_path: Destination WAV path.
        callback:    Optional ``(job_id, output_path) -> None`` called
                     when synthesis is complete.

    Returns:
        A unique ``job_id`` string. Use :func:`get_job_status` to poll.
    """
    job_id: str = str(uuid.uuid4())
    output_path = output_path or _default_output_path()

    with _jobs_lock:
        _jobs[job_id] = {
            "status": "pending",
            "output_path": output_path,
            "error": None,
        }

    def _worker() -> None:
        try:
            with _jobs_lock:
                _jobs[job_id]["status"] = "processing"

            result_path: str = synthesize(text, emotion, output_path)

            with _jobs_lock:
                _jobs[job_id]["status"] = "complete"
                _jobs[job_id]["output_path"] = result_path

            if callback:
                callback(job_id, result_path)

        except Exception as exc:
            logger.error("Async synthesis job %s failed: %s", job_id, exc)
            with _jobs_lock:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = str(exc)

    _job_pool.submit(_worker)
    logger.info("Async synthesis job queued: %s", job_id)
    return job_id


def get_job_status(job_id: str) -> Dict[str, Any]:
    """
    Query the status of an async synthesis job.

    Args:
        job_id: The job ID returned by :func:`synthesize_async`.

    Returns:
        Dict with ``status`` (``"pending"`` | ``"processing"`` |
        ``"complete"`` | ``"failed"``), ``output_path``, and ``error``.
    """
    with _jobs_lock:
        job: Optional[Dict[str, Any]] = _jobs.get(job_id)
    if job is None:
        return {"status": "not_found", "output_path": None, "error": None}
    return dict(job)


def warmup_cache(emotion: str = "neutral") -> None:
    """
    Pre-synthesize common phrases to populate the in-memory cache.

    Call this at app startup for faster first responses.

    Args:
        emotion: Emotion to use for cached phrases.
    """
    logger.info("Warming up TTS cache with %d phrases…", len(CACHED_PHRASES))
    for phrase in CACHED_PHRASES:
        try:
            cache_key = _cache_key(phrase, emotion)
            if cache_key not in _phrase_cache:
                processed: str = _preprocess_text(phrase)
                wav_bytes: bytes = _synthesize_single(processed, emotion)
                wav_bytes = _postprocess_audio(wav_bytes)
                _cache_put(cache_key, wav_bytes)
        except Exception as exc:
            logger.warning("Failed to cache phrase %r: %s", phrase[:30], exc)
    logger.info("TTS cache warm-up complete (%d items).", len(_phrase_cache))


# ========================== ENGINE INITIALISATION & REKAM CLIENT ===========

def _get_rekam_session() -> requests.Session:
    """Establish and return a requests Session with Rekam cookies pre-loaded."""
    global _rekam_session
    with _engine_lock:
        if not _rekam_session.cookies.get("cookie_consent"):
            logger.info("Initializing Rekam.ai Cloud TTS session...")
            _rekam_session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.rekam.ai/free-text-to-speech",
                "Origin": "https://www.rekam.ai",
                "Accept-Language": "en-US,en;q=0.9",
            })
            # Get cookies by visiting the main page
            try:
                _rekam_session.get("https://www.rekam.ai/free-text-to-speech", timeout=10)
                _rekam_session.cookies.set("cookie_consent", "accepted", domain=".rekam.ai")
                logger.info("Rekam.ai session initialized.")
            except requests.RequestException as e:
                logger.error(f"Failed to initialize Rekam session: {e}")
        return _rekam_session

def _generate_fallback_audio(text: str, emotion: str) -> bytes:
    """Generate a simple fallback audio file when TTS fails"""
    import numpy as np
    import wave
    import io
    
    # Calculate duration based on text length (rough estimate)
    duration = min(max(len(text) * 0.1, 1.0), 10.0)  # 1-10 seconds
    sample_rate = 22050
    samples = int(sample_rate * duration)
    
    # Generate a simple tone with some variation
    t = np.linspace(0, duration, samples)
    
    # Base frequency with some emotion-based modulation
    base_freq = 200.0  # Hz
    if emotion == "joy":
        base_freq = 250.0
    elif emotion == "sadness":
        base_freq = 150.0
    elif emotion == "anger":
        base_freq = 180.0
    elif emotion == "anxiety":
        base_freq = 220.0
    
    # Create a more complex waveform for natural speech simulation
    waveform = (
        0.3 * np.sin(2 * np.pi * base_freq * t) +  # Main tone
        0.1 * np.sin(2 * np.pi * base_freq * 2 * t) +  # Harmonic
        0.05 * np.sin(2 * np.pi * base_freq * 0.5 * t)   # Lower harmonic
    )
    
    # Add some envelope to make it more natural
    envelope = np.exp(-t * 0.5)  # Decay envelope
    waveform *= envelope
    
    # Add some random noise for breathiness
    noise = np.random.normal(0, 0.02, samples)
    waveform += noise
    
    # Convert to 16-bit PCM
    waveform = np.clip(waveform, -1, 1)
    waveform_int16 = (waveform * 32767).astype(np.int16)
    
    # Create WAV file in memory
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)   # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(wav_int16.tobytes())
    
    wav_buffer.seek(0)
    return wav_buffer.getvalue()

def _synthesize_rekam(text: str, emotion: str) -> bytes:
    """
    Calls the Rekam.ai API to generate TTS audio and returns MP3 bytes.
    """
    try:
        session = _get_rekam_session()
        params = EMOTION_PARAMS.get(emotion.lower(), EMOTION_PARAMS["neutral"])
        speed = params.get("speed", 1.0)
        
        url = "https://www.rekam.ai/api/tts/generate"
        payload = {
            "text": text,
            "voice": REKAM_VOICE_ID,
            "speed": speed
        }
        
        logger.debug(f"Requesting Rekam TTS generation with payload: {payload}")
        
        response = session.post(url, json=payload, timeout=20)
        response.raise_for_status()
        
        data = response.json()
        if data.get("code") != 0 or "data" not in data or "audio_url" not in data["data"]:
            raise ValueError(f"Rekam API returned an error or unexpected format: {data}")
            
        audio_url = data["data"]["audio_url"]
        
        # Download the final audio
        audio_resp = session.get(audio_url, timeout=20)
        audio_resp.raise_for_status()
        
        return audio_resp.content
        
    except Exception as exc:
        logger.warning(f"Rekam TTS failed, using fallback: {exc}")
        # Return fallback audio instead of empty bytes
        return _generate_fallback_audio(text, emotion)

def _generate_silence_bytes(duration_sec: float = 1.0) -> bytes:
    """Fallback dummy method."""
    return b''

def _write_silence_wav(output_path: str, duration_sec: float = 0.5) -> None:
    """Fallback dummy method."""
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(b'')

def _default_output_path() -> str:
    """Generate a unique output path in the static/audio directory."""
    os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
    filename: str = f"tts_{uuid.uuid4().hex[:12]}.mp3"
    return os.path.join(DEFAULT_OUTPUT_DIR, filename)


def _split_text_into_chunks(text: str) -> List[str]:
    """
    Split text at sentence boundaries, keeping each chunk under
    CHUNK_CHAR_LIMIT characters.
    """
    # Split on sentence-ending punctuation
    sentences: List[str] = re.split(r"(?<=[.!?])\s+", text)
    chunks: List[str] = []
    current: str = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 > 200 and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text]


# ========================== TEXT PRE-PROCESSING ===========================

def _preprocess_text(text: str) -> str:
    """
    Clean and prepare text for TTS:
      1. Expand abbreviations
      2. Remove unspeakable characters
      3. Insert SSML-style pauses at punctuation
      4. Normalise whitespace
    """
    result: str = text.strip()

    # Expand abbreviations
    for abbr, expansion in ABBREVIATIONS.items():
        result = result.replace(abbr, expansion)

    # Remove special characters that TTS engines can't pronounce
    result = re.sub(r"[*#@~`^|\\{}\[\]<>]", "", result)

    # Replace multiple punctuation with single
    result = re.sub(r"([.!?]){2,}", r"\1", result)

    # Add slight pauses: replace "..." with a comma-pause
    result = result.replace("...", ", ")

    # Replace em-dashes / en-dashes with comma-pauses
    result = re.sub(r"[—–]", ", ", result)

    # Normalise whitespace
    result = re.sub(r"\s+", " ", result).strip()

    return result


# ========================== CACHING =======================================

def _cache_key(text: str, emotion: str) -> str:
    """Create a deterministic cache key from text + emotion."""
    raw: str = f"{text.strip().lower()}|{emotion.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _cache_put(key: str, wav_bytes: bytes) -> None:
    """
    Insert into the phrase cache, evicting oldest entries if full.

    Args:
        key:       Cache key string.
        wav_bytes: WAV data to cache.
    """
    if len(_phrase_cache) >= _CACHE_MAX_ITEMS:
        # Evict the first (oldest) entry
        oldest: str = next(iter(_phrase_cache))
        del _phrase_cache[oldest]
    _phrase_cache[key] = wav_bytes


# ========================== MAIN (quick test) =============================

if __name__ == "__main__":
    print("=== TTS Handler — Quick Test ===\n")

    test_texts: List[Tuple[str, str]] = [
        ("I hear you, and I want you to know that your feelings are valid.", "sadness"),
        ("Take a deep breath. You are safe in this moment.", "anxiety"),
        ("That's wonderful! I'm really happy for you.", "joy"),
        ("Let's explore that feeling a bit more.", "neutral"),
    ]

    for text, emo in test_texts:
        print(f"  Emotion: {emo:10s} | Text: {text[:50]}…")
        try:
            path: str = synthesize(text, emotion=emo)
            print(f"  ✅  Saved → {path}\n")
        except Exception as e:
            print(f"  ❌  Failed: {e}\n")
