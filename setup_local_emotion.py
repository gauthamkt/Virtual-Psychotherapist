#!/usr/bin/env python3
"""
Quick setup for local emotion detection
"""

import subprocess
import sys

def install_requirements():
    """Install required packages"""
    packages = [
        "transformers",
        "torch", 
        "sentencepiece",
        "protobuf"
    ]
    
    for package in packages:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"✅ Installed {package}")
        except subprocess.CalledProcessError:
            print(f"⚠️  {package} might already be installed")

def download_model():
    """Download emotion model"""
    try:
        from huggingface_hub import snapshot_download
        
        print("📥 Downloading emotion model...")
        model_path = snapshot_download(
            repo_id="j-hartmann/emotion-english-distilroberta-base",
            local_dir="models/emotion-model"
            # Remove local_files_only to allow download
        )
        print(f"✅ Model downloaded to: {model_path}")
        return True
        
    except ImportError:
        print("❌ huggingface_hub not installed. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
        return download_model()
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False

if __name__ == "__main__":
    print("🧠 Setting up local emotion detection...")
    print("=" * 50)
    
    # Install requirements
    install_requirements()
    
    # Download model
    if download_model():
        print("\n🎉 Setup complete!")
        print("📁 Model location: models/emotion-model")
        print("🚀 Restart your app to use local emotion detection")
    else:
        print("\n❌ Setup failed!")
        sys.exit(1)
