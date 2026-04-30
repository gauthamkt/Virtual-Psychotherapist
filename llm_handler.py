"""
llm_handler.py – Offline LLM integration layer for the virtual psychotherapist.

Communicates with a locally-running Ollama instance to generate empathetic,
emotion-adaptive therapeutic responses under the persona of **Dr. Maya**.

Usage:
    from llm_handler import get_response, is_crisis_detected

    reply = get_response(
        user_message="I've been feeling really overwhelmed lately.",
        emotion={"label": "anxiety", "score": 0.87},
        history=[...],
    )
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Generator, List, Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OLLAMA_URL: str = "http://localhost:11434/api/chat"
PRIMARY_MODEL: str = "qwen:0.5b"
FALLBACK_MODEL: str = "mistral"
MAX_HISTORY_TURNS: int = 10          # keep last N exchanges (user+assistant pairs)
MAX_RETRIES: int = 3
RETRY_BACKOFF: float = 1.5          # seconds – multiplied on each retry
REQUEST_TIMEOUT: int = 120          # seconds

# ---------------------------------------------------------------------------
# Crisis-detection keywords (lowercase)
# ---------------------------------------------------------------------------
CRISIS_KEYWORDS: set[str] = {
    "suicide", "suicidal", "kill myself", "end my life", "self-harm",
    "self harm", "cut myself", "cutting myself", "hurt myself",
    "hopeless", "no reason to live", "want to die", "wanna die",
    "don't want to live", "not worth living", "better off dead",
    "end it all", "take my life",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt – Dr. Maya persona
# ---------------------------------------------------------------------------
SYSTEM_PROMPT: str = (
    "You are Dr. Maya, a compassionate and experienced virtual psychotherapist. "
    "Your approach is warm, non-judgmental, and deeply empathetic.\n\n"
    "Guidelines you MUST follow in every response:\n"
    "• Validate the user's emotions before anything else.\n"
    "• Use active listening — reflect back what the user has shared.\n"
    "• Ask open-ended questions to gently explore their feelings.\n"
    "• Keep responses to 2–4 sentences to feel natural and conversational.\n"
    "• NEVER diagnose, label, or prescribe medication.\n"
    "• If the user expresses thoughts of self-harm, suicide, or hopelessness, "
    "  acknowledge their pain, express genuine concern, and encourage them to "
    "  reach out to a crisis helpline such as 988 (Suicide & Crisis Lifeline) "
    "  or their local emergency services. Always provide at least one resource.\n"
    "• Adapt your tone to the user's emotional state (see emotion context below).\n"
)

# ---------------------------------------------------------------------------
# Emotion-adaptive tone instructions
# ---------------------------------------------------------------------------
EMOTION_TONE_MAP: Dict[str, str] = {
    "sadness": (
        "The user appears to be feeling sad. Respond with extra gentleness, "
        "warmth, and reassurance. Let them know it is okay to feel this way."
    ),
    "sad": (
        "The user appears to be feeling sad. Respond with extra gentleness, "
        "warmth, and reassurance. Let them know it is okay to feel this way."
    ),
    "anxiety": (
        "The user seems anxious. Use grounding, calming language. Speak slowly "
        "and steadily. Remind them that they are safe in this moment."
    ),
    "anxious": (
        "The user seems anxious. Use grounding, calming language. Speak slowly "
        "and steadily. Remind them that they are safe in this moment."
    ),
    "fear": (
        "The user seems fearful or worried. Use gentle reassurance and help "
        "them feel safe. Avoid escalating the intensity of the conversation."
    ),
    "anger": (
        "The user seems angry or frustrated. Stay calm and non-reactive. "
        "Acknowledge their frustration without judgment and gently explore "
        "what is underneath the anger."
    ),
    "angry": (
        "The user seems angry or frustrated. Stay calm and non-reactive. "
        "Acknowledge their frustration without judgment and gently explore "
        "what is underneath the anger."
    ),
    "joy": (
        "The user is expressing happiness or joy. Celebrate with them! "
        "Mirror their positive energy and ask what is contributing to "
        "this feeling."
    ),
    "happy": (
        "The user is expressing happiness or joy. Celebrate with them! "
        "Mirror their positive energy and ask what is contributing to "
        "this feeling."
    ),
    "neutral": (
        "The user's emotional state appears neutral. Maintain a warm, "
        "inviting tone and gently check in on how they are feeling today."
    ),
}


# ========================== PUBLIC FUNCTIONS ===============================

def is_crisis_detected(text: str) -> bool:
    """
    Scan the user's message for crisis-related keywords.

    Args:
        text: The raw user message.

    Returns:
        ``True`` if any crisis keyword is found, ``False`` otherwise.
    """
    lowered: str = text.lower()
    return any(keyword in lowered for keyword in CRISIS_KEYWORDS)


def get_response(
    user_message: str,
    emotion: Dict[str, Any],
    history: List[Dict[str, str]],
    *,
    stream: bool = False,
) -> str | Generator[str, None, None]:
    """
    Generate a therapeutic response from the local Ollama LLM.

    Args:
        user_message: The latest message from the user.
        emotion:      Detected emotion dict, e.g.
                      ``{"label": "sadness", "score": 0.92}``.
        history:      Full conversation history as a list of
                      ``{"role": "user"|"assistant", "content": "..."}`` dicts.
        stream:       If ``True``, return a generator that yields response
                      tokens incrementally.

    Returns:
        The assistant's reply as a ``str``, or a ``Generator[str]``
        if *stream* is ``True``.
    """
    messages: List[Dict[str, str]] = _build_messages(user_message, emotion, history)

    if stream:
        return _stream_response(messages)
    return _blocking_response(messages)


# ========================== INTERNAL HELPERS ==============================

def _build_messages(
    user_message: str,
    emotion: Dict[str, Any],
    history: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """
    Assemble the message list sent to Ollama, including the system prompt,
    emotion context, trimmed history, and the latest user message.

    Args:
        user_message: The user's current message.
        emotion:      Detected emotion dictionary.
        history:      Full conversation history.

    Returns:
        A list of message dicts ready for the Ollama API.
    """
    # --- System prompt + emotion-adaptive instruction ---
    emotion_label: str = emotion.get("label", "neutral").lower()
    emotion_score: float = emotion.get("score", 0.0)
    tone_instruction: str = EMOTION_TONE_MAP.get(
        emotion_label,
        EMOTION_TONE_MAP["neutral"],
    )

    system_content: str = (
        f"{SYSTEM_PROMPT}\n"
        f"[Emotion context] Detected emotion: {emotion_label} "
        f"(confidence: {emotion_score:.0%}).\n"
        f"{tone_instruction}\n"
    )

    # --- Crisis override ---
    if is_crisis_detected(user_message):
        system_content += (
            "\n⚠️  CRISIS DETECTED. The user may be in danger. "
            "Respond with immediate empathy, validate their pain, and "
            "strongly encourage them to contact a crisis resource:\n"
            "  • 988 Suicide & Crisis Lifeline (call or text 988)\n"
            "  • Crisis Text Line (text HOME to 741741)\n"
            "  • Emergency services (911 / local equivalent)\n"
            "Do NOT minimize their feelings. Express that you care.\n"
        )

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_content},
    ]

    # --- Trimmed history (last N exchanges = 2N messages) ---
    trimmed: List[Dict[str, str]] = history[-(MAX_HISTORY_TURNS * 2):]
    messages.extend(trimmed)

    # --- Current user message ---
    messages.append({"role": "user", "content": user_message})

    return messages


def _blocking_response(messages: List[Dict[str, str]]) -> str:
    """
    Send a non-streaming chat request to Ollama with retry logic
    and automatic model fallback.

    Args:
        messages: The assembled message list.

    Returns:
        The assistant's reply as a plain string.

    Raises:
        RuntimeError: If all retries and the fallback model fail.
    """
    for model in (PRIMARY_MODEL, FALLBACK_MODEL):
        result: Optional[str] = _request_with_retries(model, messages, stream=False)
        if result is not None:
            return result
        logger.warning("Model '%s' failed. Trying fallback…", model)

    error_msg: str = (
        "I'm sorry, I'm having trouble connecting to my language model right now. "
        "Please make sure Ollama is running and try again in a moment."
    )
    logger.error("All Ollama models failed after retries.")
    return error_msg


def _stream_response(
    messages: List[Dict[str, str]],
) -> Generator[str, None, None]:
    """
    Send a streaming chat request to Ollama with retry logic
    and automatic model fallback.

    Args:
        messages: The assembled message list.

    Yields:
        Individual content tokens as they arrive from the model.
    """
    for model in (PRIMARY_MODEL, FALLBACK_MODEL):
        try:
            payload: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": True,
            }
            resp = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                stream=True,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Streaming with model '%s' returned HTTP %s.",
                    model,
                    resp.status_code,
                )
                continue

            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    import json
                    chunk: Dict[str, Any] = json.loads(line)
                    token: str = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token
                except (ValueError, KeyError):
                    continue
            return  # successful stream — exit the generator

        except requests.ConnectionError:
            logger.warning("Cannot connect to Ollama for streaming with '%s'.", model)
        except requests.Timeout:
            logger.warning("Streaming request timed out with model '%s'.", model)

    # All models failed
    yield (
        "I'm sorry, I'm having trouble responding right now. "
        "Please ensure Ollama is running and try again."
    )


def _request_with_retries(
    model: str,
    messages: List[Dict[str, str]],
    *,
    stream: bool = False,
) -> Optional[str]:
    """
    Attempt a blocking request to Ollama, retrying on failure with
    exponential backoff.

    Args:
        model:    The Ollama model name to use.
        messages: The assembled message list.
        stream:   Whether to enable streaming (always ``False`` here).

    Returns:
        The assistant's response text on success, or ``None`` after
        exhausting all retries.
    """
    backoff: float = RETRY_BACKOFF

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            payload: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": stream,
            }
            resp = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code == 200:
                data: Dict[str, Any] = resp.json()
                content: str = (
                    data.get("message", {}).get("content", "").strip()
                )
                if content:
                    return content
                logger.warning(
                    "Model '%s' returned empty content (attempt %d/%d).",
                    model, attempt, MAX_RETRIES,
                )
            else:
                logger.warning(
                    "Ollama returned HTTP %s for model '%s' (attempt %d/%d).",
                    resp.status_code, model, attempt, MAX_RETRIES,
                )

        except requests.ConnectionError:
            logger.warning(
                "Connection to Ollama failed (attempt %d/%d).",
                attempt, MAX_RETRIES,
            )
        except requests.Timeout:
            logger.warning(
                "Ollama request timed out (attempt %d/%d).",
                attempt, MAX_RETRIES,
            )
        except Exception as exc:
            logger.error(
                "Unexpected error querying Ollama (attempt %d/%d): %s",
                attempt, MAX_RETRIES, exc,
            )

        if attempt < MAX_RETRIES:
            logger.info("Retrying in %.1f s…", backoff)
            time.sleep(backoff)
            backoff *= 2  # exponential backoff

    return None
