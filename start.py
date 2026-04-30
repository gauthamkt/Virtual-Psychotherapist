"""
start.py — Launch script for the MindSpace Virtual Psychotherapist.

Handles:
  • Starting Ollama server in the background (if not already running)
  • Validating all models (Whisper, Coqui TTS, Ollama)
  • Initialising the database
  • Running pre-flight checks on every module
  • Starting Flask on port 5000 with auto-open browser
  • Graceful shutdown (Ctrl+C) with subprocess cleanup

Usage:
    python start.py
    python start.py --port 8080
    python start.py --no-browser
"""

from __future__ import annotations

import argparse
import atexit
import logging
import os
import signal
import subprocess
import requests
import sys
import time
import webbrowser
from typing import Any, Dict, List, Optional
from transformers import pipeline

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger: logging.Logger = logging.getLogger("start")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OLLAMA_URL: str = "http://localhost:11434"
FLASK_HOST: str = "0.0.0.0"
DEFAULT_PORT: int = 5000

# Track background processes for cleanup
_subprocesses: List[subprocess.Popen] = []


# ========================== UTILITIES ======================================

def _print_banner() -> None:
    """Print a startup banner."""
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║      🧠 MindSpace — Virtual Psychotherapist ║")
    print("  ║              Starting up...                  ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()


def _status(label: str, ok: bool, detail: str = "") -> None:
    """Print a status line."""
    icon: str = "✅" if ok else "❌"
    msg: str = f"  {icon}  {label}"
    if detail:
        msg += f"  — {detail}"
    print(msg)


def _is_ollama_running() -> bool:
    """Check if Ollama is reachable."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _start_ollama() -> Optional[subprocess.Popen]:
    """Start the Ollama server in the background."""
    logger.info("Starting Ollama server...")

    # Check if 'ollama' command exists
    ollama_cmd: Optional[str] = None
    for cmd in ["ollama", "ollama.exe"]:
        try:
            subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                timeout=5,
            )
            ollama_cmd = cmd
            break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if not ollama_cmd:
        logger.warning("Ollama binary not found on PATH.")
        return None

    try:
        proc = subprocess.Popen(
            [ollama_cmd, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _subprocesses.append(proc)

        # Wait for it to come up
        for _ in range(15):
            time.sleep(1)
            if _is_ollama_running():
                logger.info("Ollama server started (PID %d).", proc.pid)
                return proc

        logger.warning("Ollama started but not responding after 15 seconds.")
        return proc

    except Exception as exc:
        logger.error("Failed to start Ollama: %s", exc)
        return None


def _check_ollama_model(model: str) -> bool:
    """Check if a specific model is available in Ollama."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            models = r.json().get("models", [])
            return any(model in m.get("name", "") for m in models)
    except Exception:
        pass
    return False


# ========================== PRE-FLIGHT CHECKS =============================

def _check_whisper() -> bool:
    """Verify Whisper is importable."""
    try:
        import whisper  # type: ignore[import-untyped]
        return True
    except ImportError:
        return False


def _check_coqui_tts() -> bool:
    """Verify Coqui TTS is importable."""
    try:
        from TTS.api import TTS  # type: ignore[import-untyped]
        return True
    except ImportError:
        return False


def _check_pyttsx3() -> bool:
    """Verify pyttsx3 is importable."""
    try:
        import pyttsx3  # type: ignore[import-untyped]
        return True
    except ImportError:
        return False


def _check_emotion_models() -> bool:
    """Verify emotion detection imports work."""
    try:
        from transformers import pipeline
        # Check if model exists locally
        model_path = "models/emotion-model"
        if os.path.exists(model_path):
            return True
        else:
            logger.warning("Emotion model not found. Run setup_emotion_model.py")
            return False
    except ImportError:
        logger.warning("Transformers not installed. Run: pip install transformers")
        return False


def _check_ffmpeg() -> bool:
    """Verify FFmpeg is installed and in PATH."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
            check=True,
        )
        return True
    except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return False


def _check_database() -> bool:
    """Verify database module works (import check)."""
    try:
        from database import init_db
        return True
    except ImportError:
        return False


def _check_llm_handler() -> bool:
    """Verify LLM handler imports work."""
    try:
        from llm_handler import get_response
        return True
    except ImportError:
        return False


def _check_flask_app() -> bool:
    """Verify the Flask app can be created."""
    try:
        from app import create_app
        return True
    except ImportError:
        return False


def run_preflight_checks() -> Dict[str, bool]:
    """
    Run all pre-flight checks and return a status map.

    Returns:
        Dict mapping check names to pass/fail booleans.
    """
    print("\n  ─── Pre-flight checks ───\n")

    checks: Dict[str, bool] = {}

    # Ollama
    ollama_ok = _is_ollama_running()
    if not ollama_ok:
        print("  ⏳  Ollama not running — attempting to start...")
        _start_ollama()
        ollama_ok = _is_ollama_running()
    checks["Ollama server"] = ollama_ok
    _status("Ollama server", ollama_ok,
            "running" if ollama_ok else "not reachable")

    # Ollama model
    if ollama_ok:
        model_ok = _check_ollama_model("qwen:0.5b")
        if not model_ok:
            model_ok = _check_ollama_model("mistral")
        checks["Ollama model"] = model_ok
        _status("Ollama model", model_ok,
                "qwen:0.5b/mistral available" if model_ok else "no model found — run 'ollama pull qwen:0.5b'")
    else:
        checks["Ollama model"] = False
        _status("Ollama model", False, "skipped (server not running)")

    # Whisper
    whisper_ok = _check_whisper()
    checks["Whisper STT"] = whisper_ok
    _status("Whisper STT", whisper_ok,
            "ready" if whisper_ok else "not installed (pip install openai-whisper)")

    # FFmpeg
    ffmpeg_ok = _check_ffmpeg()
    checks["FFmpeg"] = ffmpeg_ok
    _status("FFmpeg", ffmpeg_ok,
            "ready" if ffmpeg_ok else "not found (required for STT/TTS)")

    # Coqui TTS
    coqui_ok = _check_coqui_tts()
    pyttsx3_ok = _check_pyttsx3()
    tts_ok = coqui_ok or pyttsx3_ok
    checks["TTS engine"] = tts_ok
    if coqui_ok:
        _status("TTS engine", True, "Coqui TTS ready")
    elif pyttsx3_ok:
        _status("TTS engine", True, "pyttsx3 fallback ready")
    else:
        _status("TTS engine", False, "no TTS engine available")

    # Emotion detection
    emo_ok = _check_emotion_models()
    checks["Emotion detection"] = emo_ok
    _status("Emotion detection", emo_ok,
            "ready" if emo_ok else "import failed")

    # Database
    db_ok = _check_database()
    checks["Database"] = db_ok
    _status("Database", db_ok,
            "In-memory storage ready" if db_ok else "import failed")

    # LLM handler
    llm_ok = _check_llm_handler()
    checks["LLM handler"] = llm_ok
    _status("LLM handler", llm_ok,
            "ready" if llm_ok else "import failed")

    # Flask app
    flask_ok = _check_flask_app()
    checks["Flask app"] = flask_ok
    _status("Flask app", flask_ok,
            "ready" if flask_ok else "import failed")

    # Summary
    total = len(checks)
    passed = sum(checks.values())
    print(f"\n  ─── {passed}/{total} checks passed ───\n")

    return checks


# ========================== INIT DATABASE =================================

def init_database() -> None:
    """Initialize the database if it doesn't exist."""
    try:
        from database import init_db
        init_db()
        logger.info("Database initialized.")
    except Exception as exc:
        logger.error("Database initialization failed: %s", exc)


# ========================== CLEANUP =======================================

def cleanup() -> None:
    """Terminate all background subprocesses."""
    for proc in _subprocesses:
        if proc.poll() is None:
            logger.info("Terminating subprocess PID %d...", proc.pid)
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
    _subprocesses.clear()


def signal_handler(signum: int, frame: Any) -> None:
    """Handle Ctrl+C gracefully."""
    print("\n\n  👋 Shutting down MindSpace... Goodbye!\n")
    cleanup()
    sys.exit(0)


# ========================== MAIN ==========================================

def main() -> None:
    """Entry point for the startup script."""
    parser = argparse.ArgumentParser(
        description="Start the MindSpace Virtual Psychotherapist",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"Flask server port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Don't auto-open the browser",
    )
    parser.add_argument(
        "--skip-checks", action="store_true",
        help="Skip pre-flight checks",
    )
    args = parser.parse_args()

    # Register cleanup handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    _print_banner()

    # Pre-flight checks
    if not args.skip_checks:
        checks = run_preflight_checks()

        # Abort if critical checks fail
        critical = ["Flask app", "FFmpeg"]
        for name in critical:
            if not checks.get(name, False):
                print(f"\n  ❌ Critical check failed: {name}")
                if name == "FFmpeg":
                    print("     FFmpeg is required for voice recording and processing.")
                    print("     Download it from https://ffmpeg.org/download.html and add 'bin' to your PATH.")
                print("     Please fix the issue and try again.\n")
                sys.exit(1)
    else:
        print("  ⏩ Skipping pre-flight checks.\n")

    # Initialize database
    init_database()

    # Start Flask
    url: str = f"http://localhost:{args.port}"
    print(f"  🚀 Starting MindSpace on {url}\n")

    # Auto-open browser (delayed to let Flask start)
    if not args.no_browser:
        import threading
        def _open_browser():
            time.sleep(2.5)
            webbrowser.open(url)
        threading.Thread(target=_open_browser, daemon=True).start()

    # Import and run Flask app
    try:
        from app import create_app
        app = create_app()
        app.run(host=FLASK_HOST, port=args.port, debug=False)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    finally:
        cleanup()


if __name__ == "__main__":
    main()
