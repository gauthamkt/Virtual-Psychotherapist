#!/usr/bin/env python3
"""
Download and setup emotion detection model locally
"""

import os
from pathlib import Path
from huggingface_hub import snapshot_download

def download_emotion_model():
    """Download j-hartmann/emotion-english-distilroberta-base model"""
    print("📥 Downloading emotion detection model...")
    
    try:
        # Create models directory
        models_dir = Path("models")
        models_dir.mkdir(exist_ok=True)
        
        # Download model files
        model_path = snapshot_download(
            repo_id="j-hartmann/emotion-english-distilroberta-base",
            local_dir="models/emotion-model",
            local_files_only=True
        )
        
        print(f"✅ Model downloaded to: {model_path}")
        print("📁 Model files:")
        
        # List downloaded files
        for file in Path(model_path).rglob("*"):
            print(f"   📄 {file.name}")
            
        return True
        
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False

if __name__ == "__main__":
    download_emotion_model()
