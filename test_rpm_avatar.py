#!/usr/bin/env python3
"""
Test script to verify ReadyPlayerMe avatar integration
"""

import requests
import json
import time
import os

def test_backend_status():
    """Test if the backend is running"""
    try:
        response = requests.get('http://localhost:5000/api/session/new', method='POST')
        return response.status_code == 200
    except:
        return False

def test_avatar_files():
    """Test if avatar files exist"""
    files_to_check = [
        'static/js/rpm_avatar.js',
        'static/models/README.md',
        'templates/index.html'
    ]
    
    missing_files = []
    for file_path in files_to_check:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    return missing_files

def main():
    print("🧪 Testing ReadyPlayerMe Avatar Integration")
    print("=" * 50)
    
    # Test backend
    print("1. Testing backend connection...")
    if test_backend_status():
        print("   ✅ Backend is running")
    else:
        print("   ❌ Backend is not running")
        print("   💡 Start the backend with: python start.py")
    
    # Test files
    print("\n2. Checking avatar files...")
    missing = test_avatar_files()
    if not missing:
        print("   ✅ All avatar files are present")
    else:
        print("   ❌ Missing files:")
        for file in missing:
            print(f"      - {file}")
    
    # Test avatar model
    print("\n3. Checking avatar model...")
    if os.path.exists('static/models/avatar.glb'):
        print("   ✅ Avatar model found")
        size_mb = os.path.getsize('static/models/avatar.glb') / (1024*1024)
        print(f"   📊 File size: {size_mb:.2f} MB")
        if size_mb > 50:
            print("   ⚠️  Large file size may affect performance")
    else:
        print("   ❌ Avatar model not found")
        print("   💡 Download from ReadyPlayerMe and save as static/models/avatar.glb")
    
    print("\n📋 Next Steps:")
    print("   1. Get your ReadyPlayerMe avatar")
    print("   2. Save it as static/models/avatar.glb")
    print("   3. Start the backend: python start.py")
    print("   4. Open http://localhost:5000 in your browser")
    
    print("\n🎯 Your current setup:")
    print("   ✅ Backend: Ollama LLM (Mistral/Llama3)")
    print("   ✅ TTS: Rekam.ai cloud synthesis")
    print("   ✅ STT: OpenAI Whisper")
    print("   ✅ Emotion: VADER + HuggingFace")
    print("   🔄 Avatar: ReadyPlayerMe (pending model)")

if __name__ == "__main__":
    main()
