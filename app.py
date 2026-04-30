"""
app.py – Flask backend for the offline virtual psychotherapist application.

Integrates:
  • llm_handler  — Ollama-based conversational AI (Dr. Maya persona)
  • stt_handler  — Speech-to-text (Whisper / Vosk)
  • tts_handler  — Text-to-speech (Coqui / pyttsx3)
  • emotion      — Multi-layer emotion detection (VADER + HuggingFace)
  • database     — SQLAlchemy / SQLite persistence

Run with:
    python app.py
    # or: flask run --host=0.0.0.0 --port=5000
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

import requests
from flask import (
    Blueprint,
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_file,
)
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Local module imports
# ---------------------------------------------------------------------------
from transformers import pipeline
from database import (
    init_db,
    create_session as db_create_session,
    end_session as db_end_session,
    save_message,
    get_history as db_get_history,
    log_emotion,
    get_emotion_trend,
    get_resources,
    export_session,
)

# Initialize emotion detection pipeline
emotion_classifier = None
try:
    emotion_classifier = pipeline(
        "text-classification",
        model="models/emotion-model",
        top_k=None
    )
    emotion_classifier = pipeline(
        "text-classification", 
        model="j-hartmann/emotion-english-distilroberta-base"
    )
    print("✅ Local emotion detection loaded")
except Exception as e:
    print(f"❌ Failed to load emotion model: {e}")
    print("💡 Run: python setup_emotion_model.py")
from llm_handler import get_response, is_crisis_detected
from stt_handler import transcribe_audio as stt_transcribe
from tts_handler import synthesize as tts_synthesize

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL: str = "http://localhost:11434"
ALLOWED_AUDIO_EXTENSIONS: set[str] = {"wav", "mp3", "ogg", "webm", "flac", "m4a"}

# ---------------------------------------------------------------------------
# In-memory conversation context (for LLM history window)
# ---------------------------------------------------------------------------
conversation_cache: Dict[str, List[Dict[str, str]]] = {}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------
api_bp = Blueprint("api", __name__, url_prefix="/api")


# ========================== MIDDLEWARE / HOOKS =============================

@api_bp.before_request
def log_request_info() -> None:
    """Log every incoming request."""
    logger.info(
        "→ %s %s  [Content-Type: %s]",
        request.method,
        request.path,
        request.content_type or "N/A",
    )


@api_bp.after_request
def log_response_info(response: Response) -> Response:
    """Log the outgoing response status."""
    logger.info(
        "← %s %s  [Status: %s]",
        request.method,
        request.path,
        response.status_code,
    )
    return response


# ========================== ROUTE HANDLERS ================================

# ------- Health check ------------------------------------------------------

@api_bp.route("/health", methods=["GET"])
def health_check() -> tuple[Response, int]:
    """
    GET /api/health

    Returns app health and Ollama connectivity status.
    """
    ollama_ok: bool = False
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        ollama_ok = r.status_code == 200
    except requests.ConnectionError:
        pass

    status: str = "healthy" if ollama_ok else "degraded"
    return jsonify({
        "status": status,
        "timestamp": time.time(),
        "ollama_reachable": ollama_ok,
    }), 200 if ollama_ok else 503


# ------- Session management -----------------------------------------------

@api_bp.route("/session/new", methods=["POST"])
def new_session() -> tuple[Response, int]:
    """
    POST /api/session/new

    Creates a new therapy session in the database.

    Returns JSON: { "session_id": <int> }
    """
    data: Optional[Dict[str, Any]] = request.get_json(silent=True)
    user_name: str = data.get("user_name", "Guest") if data else "Guest"

    session_id: int = db_create_session(user_name)
    conversation_cache[str(session_id)] = []

    logger.info("Created session %d for user '%s'.", session_id, user_name)
    return jsonify({"session_id": session_id}), 201


@api_bp.route("/session/<int:session_id>/end", methods=["POST"])
def end_session(session_id: int) -> tuple[Response, int]:
    """
    POST /api/session/<session_id>/end

    Ends a session and computes the average emotion score.
    """
    db_end_session(session_id)
    conversation_cache.pop(str(session_id), None)
    return jsonify({"status": "session_ended", "session_id": session_id}), 200


# ------- Chat -------------------------------------------------------------

@api_bp.route("/chat", methods=["POST"])
def chat() -> tuple[Response, int]:
    """
    POST /api/chat

    Expects JSON:
        { "message": "<text>", "session_id": "<id>" }

    Returns JSON:
        { "reply": "<text>", "emotion": "<label>", "emotion_data": {...}, "is_crisis": bool }
    """
    data: Optional[Dict[str, Any]] = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    message: Optional[str] = data.get("message")
    session_id: Optional[str] = data.get("session_id")

    if not message or not isinstance(message, str):
        return jsonify({"error": "'message' is required and must be a string."}), 400
    if not session_id:
        return jsonify({"error": "'session_id' is required."}), 400

    sid: str = str(session_id)

    # Ensure conversation cache exists
    if sid not in conversation_cache:
        conversation_cache[sid] = []

    # --- Detect emotion (Initial pass on User Message) ---
    def detect_emotion_local(text: str) -> Dict[str, Any]:
        """Detect emotion using local model"""
        global emotion_classifier
        if emotion_classifier is None:
            return {"label": "neutral", "confidence": 0.0, "polarity": 0.0}
        
        try:
            result = emotion_classifier(text)
            if result and len(result) > 0:
                return {
                    "label": result[0]["label"],
                    "confidence": float(result[0]["score"]),
                    "polarity": 0.0  # Could be enhanced later
                }
            else:
                return {"label": "neutral", "confidence": 0.0, "polarity": 0.0}
        except Exception as e:
            logger.error("Local emotion detection failed: %s", e)
            return {"label": "neutral", "confidence": 0.0, "polarity": 0.0}

    user_emotion_data: Dict[str, Any] = detect_emotion_local(message)

    crisis: bool = user_emotion_data.get("is_crisis", False) or is_crisis_detected(message)
    user_emotion_data["is_crisis"] = crisis

    # --- Build history for LLM ---
    history: List[Dict[str, str]] = conversation_cache[sid]

    # --- Get LLM response ---
    try:
        reply: str = get_response(message, user_emotion_data, history)
        if not isinstance(reply, str):
            # In case streaming generator is returned, consume it
            reply = "".join(reply)
    except Exception as exc:
        logger.error("LLM response failed: %s", exc)
        reply = (
            "I'm here for you, and I want to help. I'm having a small technical "
            "difficulty right now, but please know that your feelings are valid. "
            "Could you try sharing that again?"
        )

    # --- Detect emotion (Second pass on Combined Context) ---
    # Analyze the AI's reply to determine the final emotional delivery
    try:
        combined_text = f"{message} {reply}"
        final_emotion_data: Dict[str, Any] = detect_emotion(combined_text)
    except Exception as exc:
        logger.error("Final emotion detection failed: %s", exc)
        final_emotion_data = user_emotion_data

    emotion_label: str = final_emotion_data.get("label", "neutral")
    final_emotion_data["is_crisis"] = crisis

    # --- Update conversation cache ---
    conversation_cache[sid].append({"role": "user", "content": message})
    conversation_cache[sid].append({"role": "assistant", "content": reply})

    # --- Persist to database ---
    try:
        save_message(session_id, "user", message, user_emotion_data)
        save_message(session_id, "therapist", reply, final_emotion_data)
        log_emotion(
            int(session_id) if str(session_id).isdigit() else 0,
            emotion_label,
            final_emotion_data.get("confidence", 0.0),
            final_emotion_data.get("polarity", 0.0),
        )
    except Exception as exc:
        logger.error("Database persistence failed: %s", exc)

    return jsonify({
        "reply": reply,
        "emotion": emotion_label,
        "emotion_data": final_emotion_data,
        "is_crisis": crisis,
    }), 200


# ------- Voice input (STT) ------------------------------------------------

@api_bp.route("/voice-input", methods=["POST"])
def voice_input() -> tuple[Response, int]:
    """
    POST /api/voice-input

    Expects multipart/form-data with an audio file under field 'audio'.

    Returns JSON: { "transcript": "<text>" }
    """
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided. Use form field 'audio'."}), 400

    audio_file = request.files["audio"]
    if not audio_file.filename:
        return jsonify({"error": "Uploaded file has no filename."}), 400

    ext: str = audio_file.filename.rsplit(".", 1)[-1].lower() if "." in audio_file.filename else ""
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        return jsonify({
            "error": f"Unsupported audio format '.{ext}'. "
                     f"Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}"
        }), 415

    # Save to temp file for stt_handler
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp_path: str = tmp.name
        audio_file.save(tmp)

    try:
        result: Dict[str, Any] = stt_transcribe(tmp_path, engine="whisper")
        transcript: str = result.get("transcript", "")
    except Exception as exc:
        logger.error("STT transcription failed: %s", exc)
        return jsonify({"error": "Audio transcription failed."}), 500
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return jsonify({
        "transcript": transcript,
        "confidence": result.get("confidence", 0.0),
        "language": result.get("language", "en"),
        "duration": result.get("duration", 0.0),
    }), 200


# ------- Text-to-speech (TTS) ---------------------------------------------

@api_bp.route("/speak", methods=["POST"])
def speak() -> tuple[Response, int] | Response:
    """
    POST /api/speak

    Expects JSON: { "text": "<text>", "emotion": "<label>" }

    Returns audio/wav file.
    """
    data: Optional[Dict[str, Any]] = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    text: Optional[str] = data.get("text")
    if not text or not isinstance(text, str):
        return jsonify({"error": "'text' is required and must be a non-empty string."}), 400

    emotion: str = data.get("emotion", "neutral")

    try:
        output_path: str = tts_synthesize(text, emotion=emotion)
        return send_file(
            output_path,
            mimetype="audio/mpeg",
            as_attachment=True,
            download_name="therapist_response.mp3",
        )
    except Exception as exc:
        logger.error("TTS synthesis failed: %s", exc)
        return jsonify({"error": "Speech synthesis failed."}), 500


# ------- History -----------------------------------------------------------

@api_bp.route("/history/<session_id>", methods=["GET"])
def get_history(session_id: str) -> tuple[Response, int]:
    """
    GET /api/history/<session_id>

    Returns the message history for the given session.
    """
    limit: int = request.args.get("limit", 50, type=int)

    try:
        sid: int = int(session_id)
    except ValueError:
        return jsonify({"error": "session_id must be an integer."}), 400

    messages: List[Dict[str, Any]] = db_get_history(sid, limit=limit)
    return jsonify({
        "session_id": sid,
        "messages": messages,
    }), 200


# ------- Emotion trend -----------------------------------------------------

@api_bp.route("/emotion-trend/<int:session_id>", methods=["GET"])
def emotion_trend(session_id: int) -> tuple[Response, int]:
    """
    GET /api/emotion-trend/<session_id>

    Returns emotion trend analytics for a session.
    """
    trend: Dict[str, Any] = get_emotion_trend(session_id)
    return jsonify(trend), 200


# ------- Resources ---------------------------------------------------------

@api_bp.route("/resources/<emotion_label>", methods=["GET"])
def resources(emotion_label: str) -> tuple[Response, int]:
    """
    GET /api/resources/<emotion_label>

    Returns support resources matching an emotion.
    """
    items: List[Dict[str, Any]] = get_resources(emotion_label.lower())
    return jsonify({"emotion": emotion_label, "resources": items}), 200


# ------- Session export ----------------------------------------------------

@api_bp.route("/session/<int:session_id>/export", methods=["GET"])
def session_export(session_id: int) -> tuple[Response, int]:
    """
    GET /api/session/<session_id>/export

    Returns a full session export as JSON.
    """
    data: Dict[str, Any] = export_session(session_id)
    if "error" in data:
        return jsonify(data), 404
    return jsonify(data), 200


# ========================== ERROR HANDLERS ================================

@api_bp.errorhandler(400)
def bad_request(error: Any) -> tuple[Response, int]:
    return jsonify({"error": "Bad request.", "details": str(error)}), 400

@api_bp.errorhandler(404)
def not_found(error: Any) -> tuple[Response, int]:
    return jsonify({"error": "The requested resource was not found."}), 404

@api_bp.errorhandler(405)
def method_not_allowed(error: Any) -> tuple[Response, int]:
    return jsonify({"error": "Method not allowed."}), 405

@api_bp.errorhandler(500)
def internal_error(error: Any) -> tuple[Response, int]:
    logger.exception("Unhandled server error: %s", error)
    return jsonify({"error": "An internal server error occurred."}), 500


# ========================== APP FACTORY ===================================

def create_app() -> Flask:
    """
    Application factory.

    Creates the Flask app, initialises the database, warms up ML models,
    registers blueprints, and enables CORS.
    """
    app = Flask(__name__)

    # Enable CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register blueprint
    app.register_blueprint(api_bp)

    # Serve frontend landing page
    @app.route("/")
    def index():
        """Serve the landing page."""
        return render_template("landing.html")

    # Serve chat interface
    @app.route("/chat")
    def chat_page():
        """Serve the main chat interface."""
        return render_template("index.html")

    # App-level error handlers
    @app.errorhandler(404)
    def global_not_found(error: Any) -> tuple[Response, int]:
        return jsonify({"error": "The requested resource was not found."}), 404

    @app.errorhandler(500)
    def global_internal_error(error: Any) -> tuple[Response, int]:
        logger.exception("Unhandled server error: %s", error)
        return jsonify({"error": "An internal server error occurred."}), 500

    # --- Startup tasks ---
    with app.app_context():
        # Initialise database (create tables + seed resources)
        init_db()
        logger.info("Database initialised.")

        # Warm up emotion detection models
        try:
            emotion_warmup()
            logger.info("Emotion detection models warmed up.")
        except Exception as exc:
            logger.warning("Emotion model warmup failed (will lazy-load): %s", exc)

    logger.info("✅ MindSpace Psychotherapist API ready.")
    return app


# ========================== ENTRY POINT ===================================

if __name__ == "__main__":
    app: Flask = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
