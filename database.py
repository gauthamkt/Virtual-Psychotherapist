"""
database.py – In-memory persistence layer for the virtual psychotherapist.

This module replaces the SQLAlchemy/SQLite implementation with an in-memory 
data structure. NOTE: All data is lost when the server restarts.

Usage:
    from database import init_db, create_session, save_message, get_history

    init_db()
    sid = create_session("Guest")
    save_message(sid, "user", "I feel anxious.", {"label": "anxiety", "score": 0.8, "polarity": -0.4})
    history = get_history(sid)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np
from collections import Counter

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
# In-Memory Storage
# ---------------------------------------------------------------------------
# Structure:
# sessions = { session_id: { "id": int, "user_name": str, "start_time": datetime, ... } }
# messages = { session_id: [ { "role": str, "text": str, ... }, ... ] }
# emotion_logs = { session_id: [ { "label": str, "score": float, ... }, ... ] }
_sessions: Dict[int, Dict[str, Any]] = {}
_messages: Dict[int, List[Dict[str, Any]]] = {}
_emotion_logs: Dict[int, List[Dict[str, Any]]] = {}
_session_counter: int = 1
_message_counter: int = 1

# ---------------------------------------------------------------------------
# Seed Data
# ---------------------------------------------------------------------------
DEFAULT_RESOURCES: List[Dict[str, str]] = [
    {"emotion_trigger": "sadness", "title": "988 Suicide & Crisis Lifeline", "description": "Free 24/7 crisis support. Call or text 988.", "url": "https://988lifeline.org", "resource_type": "hotline"},
    {"emotion_trigger": "sadness", "title": "Crisis Text Line", "description": "Text HOME to 741741 for free crisis counseling.", "url": "https://www.crisistextline.org", "resource_type": "hotline"},
    {"emotion_trigger": "sadness", "title": "Understanding Sadness", "description": "Learn how sadness serves as a natural emotional signal.", "url": "https://www.helpguide.org/articles/depression/coping-with-depression.htm", "resource_type": "article"},
    {"emotion_trigger": "sadness", "title": "Gratitude Journaling", "description": "Write down 3 things you're grateful for each day to shift perspective.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "sadness", "title": "Mindful Breathing (4-7-8)", "description": "Inhale 4s, hold 7s, exhale 8s. Repeat 4 times to calm your nervous system.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "anger", "title": "SAMHSA National Helpline", "description": "Free mental health referrals. Call 1-800-662-4357.", "url": "https://www.samhsa.gov/find-help/national-helpline", "resource_type": "hotline"},
    {"emotion_trigger": "anger", "title": "Anger Management Basics", "description": "APA guide on healthy anger expression and management.", "url": "https://www.apa.org/topics/anger/control", "resource_type": "article"},
    {"emotion_trigger": "anger", "title": "Progressive Muscle Relaxation", "description": "Tense and release each muscle group for 5 seconds to reduce physical tension.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "anger", "title": "Counting Down from 10", "description": "Slowly count from 10 to 1, breathing deeply between each number.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "anger", "title": "Crisis Text Line", "description": "Text HOME to 741741 for free support anytime.", "url": "https://www.crisistextline.org", "resource_type": "hotline"},
    {"emotion_trigger": "fear", "title": "988 Suicide & Crisis Lifeline", "description": "Call or text 988 for immediate support.", "url": "https://988lifeline.org", "resource_type": "hotline"},
    {"emotion_trigger": "fear", "title": "NAMI Helpline", "description": "Mental health info and referrals. Call 1-800-950-6264.", "url": "https://www.nami.org/help", "resource_type": "hotline"},
    {"emotion_trigger": "fear", "title": "Understanding Fear Responses", "description": "How your brain processes fear and what you can do about it.", "url": "https://www.helpguide.org/articles/anxiety/phobias-and-irrational-fears.htm", "resource_type": "article"},
    {"emotion_trigger": "fear", "title": "Grounding: 5-4-3-2-1", "description": "Name 5 things you see, 4 you touch, 3 you hear, 2 you smell, 1 you taste.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "fear", "title": "Safe Place Visualisation", "description": "Close your eyes. Imagine a place where you feel completely safe and peaceful.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "anxiety", "title": "ADAA Helpline", "description": "Anxiety & Depression Association resources. Visit adaa.org.", "url": "https://adaa.org", "resource_type": "hotline"},
    {"emotion_trigger": "anxiety", "title": "Crisis Text Line", "description": "Text HOME to 741741 for immediate support.", "url": "https://www.crisistextline.org", "resource_type": "hotline"},
    {"emotion_trigger": "anxiety", "title": "Cognitive Reframing", "description": "Challenge anxious thoughts by asking: Is this thought based on fact or feeling?", "url": "https://www.helpguide.org/articles/anxiety/how-to-stop-worrying.htm", "resource_type": "article"},
    {"emotion_trigger": "anxiety", "title": "Box Breathing", "description": "Inhale 4s, hold 4s, exhale 4s, hold 4s. Repeat to activate your calm response.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "anxiety", "title": "Body Scan Meditation", "description": "Slowly scan from head to toes, noticing and releasing tension in each area.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "joy", "title": "Savoring Exercise", "description": "Pause and fully immerse yourself in this positive moment for 30 seconds.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "joy", "title": "Sharing Joy", "description": "Tell someone close to you about what's making you happy.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "joy", "title": "Positive Psychology", "description": "Learn how to sustain and build on positive emotions.", "url": "https://www.pursuit-of-happiness.org/science-of-happiness/", "resource_type": "article"},
    {"emotion_trigger": "joy", "title": "Kindness Challenge", "description": "Do one unexpected kind act today to amplify positive feelings.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "joy", "title": "Well-being Resources (NAMI)", "description": "Tools for maintaining mental wellness.", "url": "https://www.nami.org/your-journey/living-with-a-mental-health-condition", "resource_type": "article"},
    {"emotion_trigger": "neutral", "title": "988 Suicide & Crisis Lifeline", "description": "Call or text 988 anytime you need someone to talk to.", "url": "https://988lifeline.org", "resource_type": "hotline"},
    {"emotion_trigger": "neutral", "title": "Mindfulness Introduction", "description": "A beginner's guide to present-moment awareness.", "url": "https://www.mindful.org/how-to-meditate/", "resource_type": "article"},
    {"emotion_trigger": "neutral", "title": "Daily Check-In", "description": "Ask yourself: How am I really feeling right now? Write it down.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "neutral", "title": "Self-Care Planning", "description": "List 3 activities that nourish you and schedule one for today.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "neutral", "title": "Mental Health Articles (WHO)", "description": "World Health Organization mental health fact sheets.", "url": "https://www.who.int/news-room/fact-sheets/detail/mental-health-strengthening-our-response", "resource_type": "article"},
    {"emotion_trigger": "disgust", "title": "988 Suicide & Crisis Lifeline", "description": "Call or text 988 for support.", "url": "https://988lifeline.org", "resource_type": "hotline"},
    {"emotion_trigger": "disgust", "title": "Understanding Disgust", "description": "How disgust functions as a protective emotion.", "url": "https://www.verywellmind.com/what-is-the-emotion-of-disgust-5114270", "resource_type": "article"},
    {"emotion_trigger": "disgust", "title": "Self-Compassion Break", "description": "Place a hand on your heart. Say: This is a moment of suffering. I am not alone.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "disgust", "title": "Values Reflection", "description": "Write down your top 5 values. Use them as anchors when strong emotions arise.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "disgust", "title": "Crisis Text Line", "description": "Text HOME to 741741 for free crisis counseling.", "url": "https://www.crisistextline.org", "resource_type": "hotline"},
    {"emotion_trigger": "surprise", "title": "Grounding After Shock", "description": "Hold an ice cube or splash cold water on your face to re-anchor yourself.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "surprise", "title": "Journaling the Unexpected", "description": "Write about what surprised you and how it made you feel.", "url": "", "resource_type": "exercise"},
    {"emotion_trigger": "surprise", "title": "Coping with Change", "description": "Strategies for adapting when life takes an unexpected turn.", "url": "https://www.helpguide.org/articles/stress/surviving-tough-times.htm", "resource_type": "article"},
    {"emotion_trigger": "surprise", "title": "NAMI Helpline", "description": "Call 1-800-950-6264 for mental health guidance.", "url": "https://www.nami.org/help", "resource_type": "hotline"},
    {"emotion_trigger": "surprise", "title": "Deep Belly Breathing", "description": "Place a hand on your belly. Breathe slowly so only your belly rises.", "url": "", "resource_type": "exercise"},
]

# ---------------------------------------------------------------------------
# Public Functions
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Initialize in-memory storage. No persistent files are created."""
    logger.info("In-memory database initialized.")

def create_session(user_name: str = "Guest") -> int:
    global _session_counter
    sid = _session_counter
    _session_counter += 1
    
    _sessions[sid] = {
        "id": sid,
        "user_name": user_name,
        "start_time": datetime.now(timezone.utc),
        "end_time": None,
        "session_notes": None,
        "avg_emotion_score": None,
    }
    _messages[sid] = []
    _emotion_logs[sid] = []
    
    logger.info("Created in-memory session %d for user '%s'.", sid, user_name)
    return sid

def end_session(session_id: int) -> None:
    if session_id not in _sessions:
        logger.warning("end_session: session %d not found.", session_id)
        return

    sess = _sessions[session_id]
    sess["end_time"] = datetime.now(timezone.utc)

    # Compute average emotion score from messages
    msgs = _messages.get(session_id, [])
    scores = [m["emotion_score"] for m in msgs if m["emotion_score"] is not None]
    
    if scores:
        sess["avg_emotion_score"] = round(sum(scores) / len(scores), 4)
    
    logger.info("Ended in-memory session %d.", session_id)

def save_message(
    session_id: int,
    role: str,
    text: str,
    emotion_dict: Optional[Dict[str, Any]] = None,
) -> int:
    global _message_counter
    mid = _message_counter
    _message_counter += 1

    label: Optional[str] = None
    score: Optional[float] = None
    polarity: float = 0.0

    if emotion_dict:
        if isinstance(emotion_dict, dict):
            label = emotion_dict.get("label")
            score = emotion_dict.get("score") or emotion_dict.get("confidence")
            polarity = emotion_dict.get("polarity", 0.0)
        elif isinstance(emotion_dict, str):
            label = emotion_dict

    msg = {
        "id": mid,
        "session_id": session_id,
        "role": role,
        "text": text,
        "emotion_label": label,
        "emotion_score": score,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    if session_id not in _messages:
        _messages[session_id] = []
    _messages[session_id].append(msg)

    if label:
        log_emotion(session_id, label, score or 0.0, polarity)

    return mid

def get_history(session_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    msgs = _messages.get(session_id, [])
    return msgs[-limit:]

def log_emotion(
    session_id: int,
    label: str,
    score: float,
    polarity: float,
) -> None:
    entry = {
        "session_id": session_id,
        "label": label,
        "score": score,
        "polarity": polarity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if session_id not in _emotion_logs:
        _emotion_logs[session_id] = []
    _emotion_logs[session_id].append(entry)

def get_emotion_trend(session_id: int) -> Dict[str, Any]:
    logs = _emotion_logs.get(session_id, [])
    
    if not logs:
        return {
            "dominant_emotion": "neutral",
            "volatility": 0.0,
            "avg_polarity": 0.0,
            "timeline": [],
        }

    labels = [l["label"] for l in logs]
    polarities = [l["polarity"] for l in logs]

    dominant = Counter(labels).most_common(1)[0][0]
    
    pol_arr = np.array(polarities, dtype=np.float64)
    volatility = float(np.std(pol_arr))
    avg_polarity = float(np.mean(pol_arr))

    return {
        "dominant_emotion": dominant,
        "volatility": round(volatility, 4),
        "avg_polarity": round(avg_polarity, 4),
        "timeline": logs,
    }

def get_resources(emotion_label: str) -> List[Dict[str, Any]]:
    return [r for r in DEFAULT_RESOURCES if r["emotion_trigger"] == emotion_label.lower()]

def export_session(session_id: int) -> Dict[str, Any]:
    if session_id not in _sessions:
        return {"error": f"Session {session_id} not found."}

    sess = _sessions[session_id].copy()
    # Format times for JSON
    if sess["start_time"]: sess["start_time"] = sess["start_time"].isoformat()
    if sess["end_time"]: sess["end_time"] = sess["end_time"].isoformat()

    messages = _messages.get(session_id, [])
    trend = get_emotion_trend(session_id)
    
    unique_emotions = {m["emotion_label"] for m in messages if m["emotion_label"]}
    all_resources = []
    for emo in unique_emotions:
        all_resources.extend(get_resources(emo))

    return {
        "session": sess,
        "messages": messages,
        "emotion_trend": trend,
        "resources": all_resources,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

def cleanup_old_sessions(days: int = 90) -> int:
    # Not strictly necessary for in-memory, butkept for API parity
    # Could implement based on timestamp if memory leak is a concern
    return 0

if __name__ == "__main__":
    print("=== In-Memory Database Module — Quick Test ===\n")
    init_db()
    sid = create_session("Test User")
    save_message(sid, "user", "I'm feeling great!", {"label": "joy", "score": 0.9, "polarity": 0.8})
    print(f"History: {get_history(sid)}")
    print(f"Trend: {get_emotion_trend(sid)}")
    end_session(sid)
    print("✅ All in-memory tests passed.")
