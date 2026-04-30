#!/usr/bin/env python3
"""
Puter.com TTS using ElevenLabs API
"""

import requests
import logging
import json
import time

logger = logging.getLogger(__name__)

def synthesize_puter(text: str, emotion: str = "neutral") -> bytes:
    """
    Generate speech using Puter.com's ElevenLabs API
    """
    try:
        # Puter.com API endpoint
        url = "https://api.puter.com/v1/ai/txt2speech"
        
        # Voice selection based on emotion
        voice_map = {
            "neutral": "21m00Tcm4TlvDq8ikWAM",  # Adam
            "joy": "21m00Tcm4TlvDq8ikWAM",      # Adam (friendly)
            "sadness": "AZnzlk1XvdvUeBnXmlld",  # Sam (calm)
            "anger": "29vD33N1CtxCeqQR0WJfx",   # Rachel (assertive)
            "anxiety": "21m00Tcm4TlvDq8ikWAM",  # Adam (gentle)
            "fear": "AZnzlk1XvdvUeBnXmlld"      # Sam (soothing)
        }
        
        voice_id = voice_map.get(emotion.lower(), "21m00Tcm4TlvDq8ikWAM")
        
        payload = {
            "text": text,
            "provider": "elevenlabs",
            "model": "eleven_multilingual_v2",
            "voice": voice_id,
            "output_format": "mp3_44100_128"
        }
        
        logger.info(f"Requesting Puter/ElevenLabs TTS for text: {text[:50]}...")
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "MindSpace-Therapist/1.0"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Check if response is audio data
        content_type = response.headers.get('content-type', '')
        if 'audio' in content_type:
            logger.info(f"✅ Puter TTS successful - Size: {len(response.content)} bytes")
            return response.content
        else:
            # Try to parse as JSON in case of error
            try:
                error_data = response.json()
                logger.error(f"Puter TTS API error: {error_data}")
            except:
                logger.error(f"Puter TTS returned non-audio content: {content_type}")
            return b''
            
    except Exception as e:
        logger.error(f"Puter TTS failed: {e}")
        return b''
