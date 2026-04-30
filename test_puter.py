#!/usr/bin/env python3
"""
Test Puter.com TTS API
"""

import requests
import json

def test_puter_tts():
    """Test Puter.com TTS API"""
    print("🧪 Testing Puter.com TTS API...")
    
    try:
        url = "https://api.puter.com/v1/ai/txt2speech"
        payload = {
            "text": "Hello! This is a test of the Puter TTS system.",
            "provider": "elevenlabs",
            "model": "eleven_multilingual_v2",
            "voice": "21m00Tcm4TlvDq8ikWAM",
            "output_format": "mp3_44100_128"
        }
        
        print(f"📤 Sending request to: {url}")
        print(f"📤 Payload: {json.dumps(payload, indent=2)}")
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "MindSpace-Therapist/1.0"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"📥 Response status: {response.status_code}")
        print(f"📥 Content-Type: {response.headers.get('content-type')}")
        print(f"📥 Content-Length: {len(response.content)} bytes")
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'audio' in content_type:
                print("✅ Puter TTS API working! Got audio data.")
                return True
            else:
                print("❌ Response is not audio:")
                try:
                    print(response.text[:500])
                except:
                    print("Could not decode response text")
                return False
        else:
            print(f"❌ API request failed: {response.status_code}")
            print(f"❌ Response: {response.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    test_puter_tts()
