#!/usr/bin/env python3
"""
Test Rekam.ai API directly to debug TTS issues
"""

import requests
import json

def test_rekam_api():
    """Test Rekam.ai API endpoints"""
    print("🧪 Testing Rekam.ai API...")
    
    # Test 1: Check if main site is accessible
    try:
        session = requests.Session()
        response = session.get("https://www.rekam.ai/free-text-to-speech", timeout=10)
        print(f"✅ Main site accessible: {response.status_code}")
        
        # Set cookies
        session.cookies.set("cookie_consent", "accepted", domain=".rekam.ai")
        
    except Exception as e:
        print(f"❌ Main site failed: {e}")
        return False
    
    # Test 2: Try TTS API
    try:
        url = "https://www.rekam.ai/api/tts/generate"
        payload = {
            "text": "Hello world",
            "voice": "af_heart",  # Common voice ID
            "speed": 1.0
        }
        
        print(f"📤 Sending request to: {url}")
        print(f"📤 Payload: {json.dumps(payload, indent=2)}")
        
        response = session.post(url, json=payload, timeout=20)
        print(f"📥 Response status: {response.status_code}")
        print(f"📥 Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"📥 Response data: {json.dumps(data, indent=2)}")
            
            if "data" in data and "audio_url" in data["data"]:
                audio_url = data["data"]["audio_url"]
                print(f"✅ Audio URL: {audio_url}")
                
                # Test 3: Try downloading the audio
                audio_response = session.get(audio_url, timeout=10)
                print(f"📥 Audio download status: {audio_response.status_code}")
                print(f"📥 Audio size: {len(audio_response.content)} bytes")
                
                if len(audio_response.content) > 100:
                    print("✅ Rekam.ai API is working!")
                    return True
                else:
                    print("❌ Audio file is empty or too small")
                    return False
            else:
                print(f"❌ Unexpected response format: {data}")
                return False
        else:
            print(f"❌ API request failed: {response.status_code}")
            print(f"❌ Response text: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ TTS API test failed: {e}")
        return False

if __name__ == "__main__":
    test_rekam_api()
