#!/usr/bin/env bash
# Sets up a dedicated venv for the Science text mining project.
# Run once:  bash setup_env.sh
# Activate:  source venv/bin/activate

set -e
cd "$(dirname "$0")"

echo "=== Creating venv ==="
python3 -m venv venv

echo "=== Installing packages ==="
venv/bin/pip install --upgrade pip

# Core pipeline deps
venv/bin/pip install pdfplumber

# stanza<1.9 to avoid SyntaxError bug in convert_hebrew_mixed.py on Python 3.9
venv/bin/pip install "stanza<1.9"

# ChemDataExtractor2 with all required deps (no dep resolver loop)
venv/bin/pip install \
    chemdataextractor2 \
    deprecation \
    lxml \
    pyyaml \
    python-dateutil \
    beautifulsoup4 \
    appdirs \
    nltk \
    tokenizers \
    dawg-python \
    python-crfsuite \
    yaspin

# PyTorch for macOS arm64 (MPS acceleration on Apple Silicon)
# Pinned to <2.6: PyTorch 2.6 changed torch.load default to weights_only=True,
# which breaks stanza's old model format used by CDE2.
venv/bin/pip install "torch<2.6"

# transformers (CDE2 requires >=4.30.1)
venv/bin/pip install "transformers>=4.30.1"

# Create dawg compatibility shim inside the venv
SITE=$(venv/bin/python -c "import site; print(site.getsitepackages()[0])")
cat > "$SITE/dawg.py" << 'SHIM'
from dawg_python import *
from dawg_python import DAWG, BytesDAWG, RecordDAWG, IntDAWG, CompletionDAWG
SHIM

echo ""
echo "=== Clearing stale stanza cache ==="
rm -rf ~/stanza_resources

echo ""
echo "=== Downloading CDE2 models (NER + tokenizer) ==="
venv/bin/cde data download

echo ""
echo "=== Verifying ==="
venv/bin/python -c "
import chemdataextractor as cde
from chemdataextractor import Document
from chemdataextractor.doc import Paragraph
print('CDE2 version:', cde.__version__)

# Quick smoke test
doc = Document(Paragraph('Cu/ZnO showed 42% CO2 conversion at 260 °C and 3 MPa.'))
print('CEMs:', [c.text for c in doc.cems])
print('OK')
"

echo ""
echo "Done. Activate with:  source venv/bin/activate"
