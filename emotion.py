"""
emotion.py – Multi-layer emotion detection for the virtual psychotherapist.

Detection pipeline:
  • **Layer 1 (fast)** — VADER ``SentimentIntensityAnalyzer`` for real-time
    polarity scoring (positive / negative / neutral / compound).
  • **Layer 2 (accurate)** — HuggingFace ``transformers`` pipeline using
    ``j-hartmann/emotion-english-distilroberta-base`` for fine-grained
    emotion classification across seven labels.

Provides:
  • ``detect_emotion()``   – per-message emotion + crisis flag
  • ``analyze_trend()``    – conversation-level trend & volatility
  • ``analyze_session()``  – full-session emotional summary
  • ``warmup()``           – pre-load models at startup

Usage:
    from emotion import detect_emotion, analyze_trend, warmup

    warmup()                          # call once at app startup
    result = detect_emotion("I feel so overwhelmed and hopeless.")
    # {"label": "sadness", "confidence": 0.91, "polarity": -0.72,
    #  "intensity": "high", "is_crisis": True}
"""

from __future__ import annotations

import logging
import re
import time
import threading
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

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
HF_MODEL_NAME: str = "j-hartmann/emotion-english-distilroberta-base"

SUPPORTED_EMOTIONS: List[str] = [
    "joy", "sadness", "anger", "fear", "disgust", "surprise", "neutral",
]

CRISIS_KEYWORDS: set[str] = {
    "suicide", "suicidal", "kill myself", "end my life", "self-harm",
    "self harm", "cut myself", "cutting myself", "hurt myself",
    "hopeless", "no reason to live", "want to die", "wanna die",
    "don't want to live", "not worth living", "better off dead",
    "end it all", "take my life", "give up on life", "no hope",
    "can't go on", "nothing to live for", "wish i was dead",
    "wish i were dead", "no point in living",
}

# Intensity thresholds (based on confidence scores)
INTENSITY_HIGH: float = 0.75
INTENSITY_MEDIUM: float = 0.45

# Cache TTL in seconds
CACHE_TTL: int = 60

# ---------------------------------------------------------------------------
# Lazy-loaded model state
# ---------------------------------------------------------------------------
_vader_analyzer: Any = None
_hf_pipeline: Any = None
_models_lock: threading.Lock = threading.Lock()
_models_ready: bool = False

# ---------------------------------------------------------------------------
# Result cache  { text_hash → (result_dict, timestamp) }
# ---------------------------------------------------------------------------
_result_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
_cache_lock: threading.Lock = threading.Lock()


# ========================== PUBLIC API ====================================

def warmup() -> None:
    """
    Pre-load both detection models so the first real call has no latency.

    Call this once at application startup (e.g. in your Flask ``create_app``).
    """
    logger.info("Warming up emotion detection models…")
    _get_vader()
    _get_hf_pipeline()
    logger.info("Emotion models ready.")
    global _models_ready
    _models_ready = True


def detect_emotion(text: str) -> Dict[str, Any]:
    """
    Detect the dominant emotion in a text message.

    Runs a two-layer pipeline:
      1. VADER for polarity scoring (fast)
      2. HuggingFace transformer for emotion classification (accurate)

    Args:
        text: The user's message.

    Returns:
        A dict with keys:
            - ``label``      (str):   Dominant emotion label.
            - ``confidence`` (float): Model confidence [0.0–1.0].
            - ``polarity``   (float): VADER compound score [−1.0 … +1.0].
            - ``intensity``  (str):   ``"low"`` | ``"medium"`` | ``"high"``.
            - ``is_crisis``  (bool):  ``True`` if crisis keywords detected.
    """
    if not text or not text.strip():
        return _empty_result()

    # --- Check cache ---
    cache_key: str = _make_cache_key(text)
    cached: Optional[Dict[str, Any]] = _cache_get(cache_key)
    if cached is not None:
        logger.debug("Cache hit for emotion detection.")
        return cached

    # --- Layer 1: VADER polarity ---
    polarity: float = _vader_polarity(text)

    # --- Layer 2: HuggingFace classification ---
    label, confidence = _hf_classify(text)

    # --- Crisis detection ---
    is_crisis: bool = _check_crisis(text)

    # --- Intensity ---
    intensity: str = _compute_intensity(confidence, polarity)

    result: Dict[str, Any] = {
        "label": label,
        "confidence": round(confidence, 4),
        "polarity": round(polarity, 4),
        "intensity": intensity,
        "is_crisis": is_crisis,
    }

    # --- Cache the result ---
    _cache_put(cache_key, result)

    logger.info(
        "Emotion detected: %s (%.0f%%, polarity=%.2f, crisis=%s)",
        label, confidence * 100, polarity, is_crisis,
    )
    return result


def analyze_trend(emotion_history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyse emotional trends across a conversation.

    Args:
        emotion_history: A list of emotion result dicts (as returned by
                         :func:`detect_emotion`), ordered chronologically.

    Returns:
        A dict with keys:
            - ``dominant_emotion`` (str):   The most frequent emotion.
            - ``emotion_distribution`` (dict): Label → proportion.
            - ``avg_polarity``    (float): Mean compound polarity.
            - ``polarity_trend``  (str):   ``"improving"`` | ``"declining"`` |
                                           ``"stable"``.
            - ``volatility``      (float): Standard deviation of polarity
                                           (higher = more mood swings).
            - ``crisis_count``    (int):   Number of messages flagged as crisis.
            - ``improvement``     (bool):  ``True`` if polarity is trending
                                           upward over the session.
    """
    if not emotion_history:
        return {
            "dominant_emotion": "neutral",
            "emotion_distribution": {},
            "avg_polarity": 0.0,
            "polarity_trend": "stable",
            "volatility": 0.0,
            "crisis_count": 0,
            "improvement": False,
        }

    labels: List[str] = [e.get("label", "neutral") for e in emotion_history]
    polarities: List[float] = [e.get("polarity", 0.0) for e in emotion_history]
    crisis_flags: List[bool] = [e.get("is_crisis", False) for e in emotion_history]

    # Dominant emotion
    counter: Counter = Counter(labels)
    dominant: str = counter.most_common(1)[0][0]

    # Distribution
    total: int = len(labels)
    distribution: Dict[str, float] = {
        lbl: round(cnt / total, 3) for lbl, cnt in counter.items()
    }

    # Polarity stats
    import numpy as np
    pol_array = np.array(polarities, dtype=np.float64)
    avg_polarity: float = float(np.mean(pol_array))
    volatility: float = float(np.std(pol_array))

    # Polarity trend (compare first half vs second half)
    polarity_trend: str = "stable"
    improvement: bool = False
    if len(polarities) >= 4:
        mid: int = len(polarities) // 2
        first_half: float = float(np.mean(pol_array[:mid]))
        second_half: float = float(np.mean(pol_array[mid:]))
        diff: float = second_half - first_half
        if diff > 0.1:
            polarity_trend = "improving"
            improvement = True
        elif diff < -0.1:
            polarity_trend = "declining"

    return {
        "dominant_emotion": dominant,
        "emotion_distribution": distribution,
        "avg_polarity": round(avg_polarity, 4),
        "polarity_trend": polarity_trend,
        "volatility": round(volatility, 4),
        "crisis_count": sum(crisis_flags),
        "improvement": improvement,
    }


def analyze_session(messages: List[str]) -> Dict[str, Any]:
    """
    Batch-process all user messages from a session and produce a
    comprehensive emotional summary.

    Args:
        messages: A list of raw user message strings.

    Returns:
        A dict containing:
            - ``message_count``     (int):  Number of messages analysed.
            - ``emotions``          (list): Per-message emotion results.
            - ``trend``             (dict): Output of :func:`analyze_trend`.
            - ``overall_sentiment`` (str):  ``"positive"`` | ``"negative"`` |
                                            ``"mixed"`` | ``"neutral"``.
            - ``key_concerns``      (list): Emotions with high intensity.
    """
    if not messages:
        return {
            "message_count": 0,
            "emotions": [],
            "trend": analyze_trend([]),
            "overall_sentiment": "neutral",
            "key_concerns": [],
        }

    # Detect emotion for each message
    emotions: List[Dict[str, Any]] = [detect_emotion(msg) for msg in messages]

    # Trend analysis
    trend: Dict[str, Any] = analyze_trend(emotions)

    # Overall sentiment bucket
    avg_pol: float = trend["avg_polarity"]
    if avg_pol > 0.15:
        overall: str = "positive"
    elif avg_pol < -0.15:
        overall = "negative"
    elif trend["volatility"] > 0.3:
        overall = "mixed"
    else:
        overall = "neutral"

    # Key concerns: high-intensity negative emotions
    key_concerns: List[Dict[str, Any]] = [
        {"message_index": i, "emotion": e["label"], "confidence": e["confidence"]}
        for i, e in enumerate(emotions)
        if e["intensity"] == "high" and e["label"] in ("sadness", "anger", "fear", "disgust")
    ]

    return {
        "message_count": len(messages),
        "emotions": emotions,
        "trend": trend,
        "overall_sentiment": overall,
        "key_concerns": key_concerns,
    }


# ========================== MODEL LOADERS =================================

def _get_vader() -> Any:
    """Lazy-load and cache the VADER SentimentIntensityAnalyzer."""
    global _vader_analyzer

    if _vader_analyzer is not None:
        return _vader_analyzer

    with _models_lock:
        if _vader_analyzer is not None:
            return _vader_analyzer

        try:
            import nltk  # type: ignore[import-untyped]

            # Download VADER lexicon if missing (silent)
            try:
                nltk.data.find("sentiment/vader_lexicon.zip")
            except LookupError:
                logger.info("Downloading VADER lexicon…")
                nltk.download("vader_lexicon", quiet=True)

            from nltk.sentiment.vader import SentimentIntensityAnalyzer  # type: ignore
            _vader_analyzer = SentimentIntensityAnalyzer()
            logger.info("VADER analyser loaded.")
            return _vader_analyzer

        except ImportError:
            logger.warning(
                "nltk is not installed. VADER layer will be skipped. "
                "Install with: pip install nltk"
            )
            return None


def _get_hf_pipeline() -> Any:
    """Lazy-load and cache the HuggingFace emotion classification pipeline."""
    global _hf_pipeline

    if _hf_pipeline is not None:
        return _hf_pipeline

    with _models_lock:
        if _hf_pipeline is not None:
            return _hf_pipeline

        try:
            from transformers import pipeline  # type: ignore[import-untyped]
            logger.info("Loading HuggingFace model '%s'…", HF_MODEL_NAME)
            _hf_pipeline = pipeline(
                "text-classification",
                model=HF_MODEL_NAME,
                top_k=None,         # return all labels with scores
                truncation=True,
                max_length=512,
            )
            logger.info("HuggingFace emotion model loaded.")
            return _hf_pipeline

        except ImportError:
            logger.warning(
                "transformers is not installed. HuggingFace layer disabled. "
                "Install with: pip install transformers torch"
            )
            return None
        except Exception as exc:
            logger.error("Failed to load HuggingFace model: %s", exc)
            return None


# ========================== DETECTION LAYERS ==============================

def _vader_polarity(text: str) -> float:
    """
    Get the VADER compound polarity score.

    Args:
        text: Raw user text.

    Returns:
        Compound score in [−1.0, +1.0]. Returns 0.0 if VADER is unavailable.
    """
    analyzer = _get_vader()
    if analyzer is None:
        return 0.0

    try:
        scores: Dict[str, float] = analyzer.polarity_scores(text)
        return scores.get("compound", 0.0)
    except Exception as exc:
        logger.warning("VADER scoring failed: %s", exc)
        return 0.0


def _hf_classify(text: str) -> Tuple[str, float]:
    """
    Classify emotion using the HuggingFace transformer model.

    Args:
        text: Raw user text.

    Returns:
        Tuple of ``(label, confidence)``. Falls back to polarity-based
        guessing if the model is unavailable.
    """
    pipe = _get_hf_pipeline()
    if pipe is None:
        # Fallback: derive a rough label from VADER polarity
        return _fallback_classify(text)

    try:
        # Truncate very long texts to avoid OOM
        input_text: str = text[:1024]
        results: List[Dict[str, Any]] = pipe(input_text)[0]  # type: ignore

        # results is a list of {"label": ..., "score": ...} dicts
        if not results:
            return "neutral", 0.5

        # Pick the top-scoring label
        best: Dict[str, Any] = max(results, key=lambda x: x["score"])
        label: str = best["label"].lower()
        confidence: float = best["score"]

        # Normalise label to our supported set
        label = _normalise_label(label)
        return label, confidence

    except Exception as exc:
        logger.error("HuggingFace classification failed: %s", exc)
        return _fallback_classify(text)


def _fallback_classify(text: str) -> Tuple[str, float]:
    """
    Rough emotion classification based on VADER polarity alone.

    Used when the HuggingFace model is unavailable.
    """
    polarity: float = _vader_polarity(text)

    if polarity >= 0.5:
        return "joy", 0.6
    elif polarity >= 0.1:
        return "neutral", 0.5
    elif polarity >= -0.1:
        return "neutral", 0.5
    elif polarity >= -0.5:
        return "sadness", 0.55
    else:
        return "sadness", 0.65


def _normalise_label(label: str) -> str:
    """Map model output labels to our standard emotion set."""
    label = label.lower().strip()

    label_map: Dict[str, str] = {
        "joy":      "joy",
        "happy":    "joy",
        "happiness": "joy",
        "sadness":  "sadness",
        "sad":      "sadness",
        "anger":    "anger",
        "angry":    "anger",
        "fear":     "fear",
        "afraid":   "fear",
        "disgust":  "disgust",
        "surprise": "surprise",
        "surprised": "surprise",
        "neutral":  "neutral",
    }
    return label_map.get(label, "neutral")


# ========================== CRISIS DETECTION ==============================

def _check_crisis(text: str) -> bool:
    """
    Check for crisis-related keywords in the user's message.

    Args:
        text: Raw user text.

    Returns:
        ``True`` if any crisis keyword is found.
    """
    lowered: str = text.lower()
    return any(keyword in lowered for keyword in CRISIS_KEYWORDS)


# ========================== HELPERS =======================================

def _compute_intensity(confidence: float, polarity: float) -> str:
    """
    Derive an intensity level from model confidence and polarity strength.

    Args:
        confidence: Emotion classifier confidence [0.0–1.0].
        polarity:   VADER compound polarity [−1.0 … +1.0].

    Returns:
        ``"low"`` | ``"medium"`` | ``"high"``.
    """
    combined: float = (confidence + abs(polarity)) / 2.0

    if combined >= INTENSITY_HIGH:
        return "high"
    elif combined >= INTENSITY_MEDIUM:
        return "medium"
    else:
        return "low"


def _empty_result() -> Dict[str, Any]:
    """Return a neutral/empty emotion result."""
    return {
        "label": "neutral",
        "confidence": 0.0,
        "polarity": 0.0,
        "intensity": "low",
        "is_crisis": False,
    }


# ========================== CACHING =======================================

def _make_cache_key(text: str) -> str:
    """Create a normalised cache key from text."""
    return text.strip().lower()


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    """Retrieve a cached result if it exists and hasn't expired."""
    with _cache_lock:
        entry: Optional[Tuple[Dict[str, Any], float]] = _result_cache.get(key)
        if entry is None:
            return None
        result, timestamp = entry
        if time.time() - timestamp > CACHE_TTL:
            del _result_cache[key]
            return None
        return result


def _cache_put(key: str, result: Dict[str, Any]) -> None:
    """Store a result in the cache with current timestamp."""
    with _cache_lock:
        # Evict stale entries if cache grows too large
        if len(_result_cache) > 500:
            _evict_stale_cache()
        _result_cache[key] = (result, time.time())


def _evict_stale_cache() -> None:
    """Remove expired entries from the cache (called under lock)."""
    now: float = time.time()
    stale_keys: List[str] = [
        k for k, (_, ts) in _result_cache.items() if now - ts > CACHE_TTL
    ]
    for k in stale_keys:
        del _result_cache[k]


# ========================== MAIN (quick test) =============================

if __name__ == "__main__":
    print("=== Emotion Detection — Quick Test ===\n")

    warmup()

    test_messages: List[str] = [
        "I feel so happy today, everything is going well!",
        "I've been really anxious and can't stop worrying.",
        "I'm so angry at how they treated me.",
        "I just feel empty and hopeless. Nothing matters anymore.",
        "That's an interesting observation, tell me more.",
        "I want to end it all, I can't go on like this.",
        "The sunset was surprisingly beautiful today.",
    ]

    emotion_history: List[Dict[str, Any]] = []

    for msg in test_messages:
        result = detect_emotion(msg)
        emotion_history.append(result)
        crisis_flag: str = " ⚠️ CRISIS" if result["is_crisis"] else ""
        print(
            f"  [{result['intensity']:6s}] {result['label']:10s} "
            f"({result['confidence']:.0%}, pol={result['polarity']:+.2f})"
            f"{crisis_flag}"
        )
        print(f"         → {msg[:60]}")
        print()

    print("--- Trend Analysis ---")
    trend = analyze_trend(emotion_history)
    print(f"  Dominant emotion : {trend['dominant_emotion']}")
    print(f"  Avg polarity     : {trend['avg_polarity']:+.3f}")
    print(f"  Polarity trend   : {trend['polarity_trend']}")
    print(f"  Volatility       : {trend['volatility']:.3f}")
    print(f"  Crisis messages  : {trend['crisis_count']}")
    print(f"  Improvement      : {trend['improvement']}")
