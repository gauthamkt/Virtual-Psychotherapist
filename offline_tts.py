#!/usr/bin/env python3
"""
Offline TTS using pyttsx3
"""

import pyttsx3
import logging
import io
import tempfile
import os

logger = logging.getLogger(__name__)

def synthesize_offline_tts(text: str, emotion: str = "neutral") -> bytes:
    """
    Generate speech using pyttsx3 offline TTS
    """
    try:
        # Initialize the TTS engine
        engine = pyttsx3.init()
        
        # Get available voices
        voices = engine.getProperty('voices')
        
        # Always use Zira voice for all emotions
        selected_voice = None
        for voice in voices:
            if "zira" in voice.name.lower():
                selected_voice = voice
                break
        
        if selected_voice:
            engine.setProperty('voice', selected_voice.id)
        elif voices:
            # Fallback to first available voice if Zira not found
            engine.setProperty('voice', voices[0].id)
        
        # Set speech rate based on emotion
        rate = engine.getProperty('rate')
        if emotion == "joy" or emotion == "happy":
            engine.setProperty('rate', rate + 20)  # Faster for happy
        elif emotion == "sadness":
            engine.setProperty('rate', rate - 30)  # Slower for sad
        elif emotion == "anger":
            engine.setProperty('rate', rate + 10)  # Slightly faster for angry
        else:
            engine.setProperty('rate', rate)  # Normal rate
        
        # Set volume
        engine.setProperty('volume', 0.9)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Save speech to file
            engine.save_to_file(text, temp_path)
            engine.runAndWait()
            
            # Read the generated audio file
            with open(temp_path, 'rb') as f:
                audio_data = f.read()
            
            logger.info(f"✅ Offline TTS generated - Size: {len(audio_data)} bytes")
            return audio_data
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        
    except Exception as e:
        logger.error(f"Offline TTS failed: {e}")
        return b''

def get_available_voices():
    """Get list of available voices"""
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        voice_list = []
        for voice in voices:
            voice_list.append({
                'id': voice.id,
                'name': voice.name,
                'gender': voice.gender,
                'languages': voice.languages
            })
        
        print("Available voices:")
        for voice in voice_list:
            print(f"  - {voice['name']} (ID: {voice['id']})")
        
        return voice_list
    except Exception as e:
        logger.error(f"Failed to get voices: {e}")
        return []
