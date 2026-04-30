#!/usr/bin/env bash
# ============================================================================
# setup.sh — One-time setup for the MindSpace Virtual Psychotherapist
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'  # No Color

print_step()  { echo -e "\n${CYAN}${BOLD}[$1/${TOTAL_STEPS}]${NC} $2"; }
print_ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
print_warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }
print_err()   { echo -e "  ${RED}✗${NC} $1"; }

TOTAL_STEPS=8
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║    MindSpace — Virtual Psychotherapist       ║"
echo "  ║           Environment Setup                  ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# ---------------------------------------------------------------
# 1. Check Python version
# ---------------------------------------------------------------
print_step 1 "Checking Python version..."

PYTHON_CMD=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    PY_VERSION=$("$cmd" --version 2>&1 | awk '{print $2}')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
      PYTHON_CMD="$cmd"
      break
    fi
  fi
done

if [ -z "$PYTHON_CMD" ]; then
  print_err "Python 3.10+ is required but not found."
  echo "    Install Python 3.10+ from https://www.python.org/downloads/"
  exit 1
fi
print_ok "Found $PYTHON_CMD ($PY_VERSION)"

# ---------------------------------------------------------------
# 2. Create virtual environment
# ---------------------------------------------------------------
print_step 2 "Creating virtual environment..."

if [ -d "venv" ]; then
  print_ok "Virtual environment already exists."
else
  "$PYTHON_CMD" -m venv venv
  print_ok "Created venv/"
fi

# Activate
if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
  source venv/Scripts/activate
else
  print_err "Cannot find venv activation script."
  exit 1
fi
print_ok "Virtual environment activated."

# ---------------------------------------------------------------
# 3. Install Python dependencies
# ---------------------------------------------------------------
print_step 3 "Installing Python dependencies..."

pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
print_ok "All Python packages installed."

# ---------------------------------------------------------------
# 4. Check Ollama
# ---------------------------------------------------------------
print_step 4 "Checking Ollama installation..."

if command -v ollama &>/dev/null; then
  OLLAMA_VER=$(ollama --version 2>&1 | head -1)
  print_ok "Ollama found: $OLLAMA_VER"
else
  print_warn "Ollama is not installed."
  echo ""
  echo "    Ollama is required for the LLM backend."
  echo "    Install from: https://ollama.com/download"
  echo ""
  read -rp "    Press Enter after installing Ollama, or Ctrl+C to exit..."

  if ! command -v ollama &>/dev/null; then
    print_err "Ollama still not found. Please install and re-run setup."
    exit 1
  fi
  print_ok "Ollama detected."
fi

# ---------------------------------------------------------------
# 5. Pull Ollama model
# ---------------------------------------------------------------
print_step 5 "Pulling Ollama model (mistral)..."

if ollama list 2>/dev/null | grep -q "mistral"; then
  print_ok "Model 'mistral' is already available."
else
  echo "    Downloading mistral model (this may take a few minutes)..."
  ollama pull mistral
  print_ok "Model 'mistral' pulled successfully."
fi

# ---------------------------------------------------------------
# 6. Download Whisper model
# ---------------------------------------------------------------
print_step 6 "Downloading Whisper base model..."

"$PYTHON_CMD" -c "
import whisper
print('  Loading Whisper base model...')
model = whisper.load_model('base')
print('  Whisper base model ready.')
" 2>/dev/null && print_ok "Whisper base model cached." || print_warn "Whisper download skipped (will download on first use)."

# ---------------------------------------------------------------
# 7. Download Coqui TTS model
# ---------------------------------------------------------------
print_step 7 "Downloading Coqui TTS model..."

"$PYTHON_CMD" -c "
from TTS.api import TTS
print('  Loading TTS model...')
tts = TTS(model_name='tts_models/en/ljspeech/tacotron2-DDC', progress_bar=True)
print('  Coqui TTS model ready.')
" 2>/dev/null && print_ok "Coqui TTS model cached." || print_warn "Coqui TTS download skipped (will download on first use)."

# ---------------------------------------------------------------
# 8. Initialize database
# ---------------------------------------------------------------
print_step 8 "Initializing SQLite database..."

"$PYTHON_CMD" -c "
from database import init_db
init_db()
print('  Database ready.')
"
print_ok "Database initialized and resources seeded."

# ---------------------------------------------------------------
# Done!
# ---------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅ Setup complete!${NC}"
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  To start the application:"
echo -e "    ${CYAN}1.${NC} Make sure Ollama is running:  ${BOLD}ollama serve${NC}"
echo -e "    ${CYAN}2.${NC} Run the app:                  ${BOLD}python start.py${NC}"
echo -e "    ${CYAN}3.${NC} Open browser:                 ${BOLD}http://localhost:5000${NC}"
echo ""
