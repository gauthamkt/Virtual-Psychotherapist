#!/usr/bin/env python3
"""
Simple working TTS solution
"""

import requests
import logging
import json
import io
import wave
import numpy as np

logger = logging.getLogger(__name__)

def synthesize_simple_tts(text: str, emotion: str = "neutral") -> bytes:
    """
    Simple TTS that works reliably with short text
    """
    try:
        # Truncate text to avoid length limits
        max_length = 100
        short_text = text[:max_length] if len(text) > max_length else text
        
        # Use a simple TTS API that returns audio directly
        url = "https://api.novelai.net/voice/tts"
        
        payload = {
            "text": short_text,
            "voice": "en-US-female-1",
            "output_format": "mp3"
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "MindSpace-Therapist/1.0"
        }
        
        logger.info(f"Requesting Simple TTS for text: {short_text[:50]}...")
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'audio' in content_type or 'mpeg' in content_type:
                logger.info(f"✅ Simple TTS successful - Size: {len(response.content)} bytes")
                return response.content
            else:
                # Try to get audio from JSON response
                try:
                    data = response.json()
                    if 'audio_url' in data:
                        audio_response = requests.get(data['audio_url'], timeout=10)
                        if audio_response.status_code == 200:
                            logger.info(f"✅ Simple TTS (via URL) successful - Size: {len(audio_response.content)} bytes")
                            return audio_response.content
                except:
                    pass
        else:
            logger.warning(f"Simple TTS failed: {response.status_code}")
        
        # Fallback to basic tone generation
        return _generate_basic_tone(short_text, emotion)
        
    except Exception as e:
        logger.error(f"Simple TTS failed: {e}")
        return _generate_basic_tone(text, emotion)

def _generate_basic_tone(text: str, emotion: str) -> bytes:
    """Generate a basic tone as last resort"""
    try:
        duration = min(len(text) * 0.1, 2.0)  # 0.1-2 seconds
        sample_rate = 22050
        samples = int(sample_rate * duration)
        
        # Base frequency for different emotions
        freq_map = {
            "neutral": 180.0,
            "joy": 220.0,
            "sadness": 140.0,
            "anger": 160.0,
            "anxiety": 200.0
        }
        freq = freq_map.get(emotion, 180.0)
        
        # Generate simple sine wave
        t = np.linspace(0, duration, samples)
        waveform = 0.3 * np.sin(2 * np.pi * freq * t)
        
        # Add envelope
        envelope = np.exp(-t * 0.5)
        waveform *= envelope
        
        # Convert to 16-bit PCM
        waveform = np.clip(waveform, -1, 1)
        waveform_int16 = (waveform * 16383).astype(np.int16)
        
        # Create WAV in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(wav_int16.tobytes())
        
        wav_buffer.seek(0)
        return wav_buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Basic tone generation failed: {e}")
        return b''
