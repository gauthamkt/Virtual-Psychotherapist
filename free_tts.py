#!/usr/bin/env python3
"""
Free TTS using Google Translate TTS API
"""

import requests
import logging
import urllib.parse
import base64

logger = logging.getLogger(__name__)

def synthesize_google_tts(text: str, emotion: str = "neutral") -> bytes:
    """
    Generate speech using Google Translate TTS (free)
    """
    try:
        # Google Translate TTS endpoint
        # Note: This is a well-known unofficial endpoint
        text_encoded = urllib.parse.quote(text)
        
        # Language selection based on emotion (all use English for now)
        lang = "en"
        
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl={lang}&client=tw-ob"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://translate.google.com/"
        }
        
        logger.info(f"Requesting Google TTS for text: {text[:50]}...")
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        if response.status_code == 200:
            logger.info(f"✅ Google TTS successful - Size: {len(response.content)} bytes")
            return response.content
        else:
            logger.error(f"Google TTS failed with status: {response.status_code}")
            return b''
            
    except Exception as e:
        logger.error(f"Google TTS failed: {e}")
        return b''

def synthesize_fish_audio(text: str, emotion: str = "neutral") -> bytes:
    """
    Generate speech using Fish Audio API (free tier)
    """
    try:
        url = "https://api.fish.audio/v1/tts"
        
        payload = {
            "text": text,
            "voice": "en-US-Standard-A",  # Default voice
            "speed": 1.0
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "MindSpace-Therapist/1.0"
        }
        
        logger.info(f"Requesting Fish Audio TTS for text: {text[:50]}...")
        
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'audio' in content_type:
                logger.info(f"✅ Fish Audio TTS successful - Size: {len(response.content)} bytes")
                return response.content
            else:
                logger.error(f"Fish Audio returned non-audio: {content_type}")
                return b''
        else:
            logger.error(f"Fish Audio failed: {response.status_code}")
            return b''
            
    except Exception as e:
        logger.error(f"Fish Audio TTS failed: {e}")
        return b''
