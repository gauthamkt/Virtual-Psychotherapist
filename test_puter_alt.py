#!/usr/bin/env python3
"""
Test Puter.com TTS using the correct API endpoint
"""

import requests
import json

def test_puter_alternative():
    """Test alternative Puter.com endpoints"""
    print("🧪 Testing Puter.com alternative endpoints...")
    
    # Try different endpoints
    endpoints = [
        "https://api.puter.com/v1/ai/txt2speech",
        "https://puter.com/api/v1/ai/txt2speech", 
        "https://js.puter.com/v2/ai/txt2speech",
        "https://puter.ai/api/txt2speech"
    ]
    
    payload = {
        "text": "Hello! This is a test.",
        "provider": "elevenlabs",
        "model": "eleven_multilingual_v2",
        "voice": "21m00Tcm4TlvDq8ikWAM",
        "output_format": "mp3_44100_128"
    }
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "MindSpace-Therapist/1.0",
        "Origin": "https://puter.com",
        "Referer": "https://puter.com/"
    }
    
    for url in endpoints:
        print(f"\n📤 Trying: {url}")
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            print(f"📥 Status: {response.status_code}")
            print(f"📥 Content-Type: {response.headers.get('content-type')}")
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'audio' in content_type:
                    print(f"✅ SUCCESS! Got audio: {len(response.content)} bytes")
                    return url
                else:
                    print(f"❌ Not audio: {response.text[:200]}")
            else:
                print(f"❌ Failed: {response.text[:200]}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
    
    return None

if __name__ == "__main__":
    result = test_puter_alternative()
    if result:
        print(f"\n🎉 Working endpoint: {result}")
    else:
        print("\n❌ No working endpoint found")
