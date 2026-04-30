#!/usr/bin/env python3
"""
FreeTTS.com TTS integration
"""

import requests
import logging
import json

logger = logging.getLogger(__name__)

def synthesize_freetts(text: str, emotion: str = "neutral") -> bytes:
    """
    Generate speech using FreeTTS.com API
    """
    try:
        url = "https://freetts.com/text-to-speech"
        
        # Voice selection based on emotion
        voice_map = {
            "neutral": "default",
            "joy": "female_happy",
            "sadness": "female_sad", 
            "anger": "male_angry",
            "anxiety": "female_anxious",
            "fear": "male_scared"
        }
        
        voice_id = voice_map.get(emotion.lower(), "default")
        
        payload = {
            "text": text,
            "voice": voice_id
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "MindSpace-Therapist/1.0"
        }
        
        logger.info(f"Requesting FreeTTS.com for text: {text[:50]}...")
        
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'audio' in content_type:
                logger.info(f"✅ FreeTTS.com successful - Size: {len(response.content)} bytes")
                return response.content
            else:
                logger.error(f"FreeTTS.com returned non-audio content: {content_type}")
                return b''
        else:
            logger.error(f"FreeTTS.com API failed with status: {response.status_code}")
            return b''
            
    except Exception as e:
        logger.error(f"FreeTTS.com failed: {e}")
        return b''
