#!/usr/bin/env bash
# Sets up a dedicated venv for catalitmine.
#
#   bash setup_env.sh               # core pipeline (docling, anthropic, analysis)
#   bash setup_env.sh --with-cde2   # + legacy CDE2 evidence-track stack
#
# Activate afterwards:  source venv/bin/activate

set -e
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "Python >= 3.10 required (found: $($PYTHON --version))" >&2
    exit 1
fi

echo "=== Creating venv ==="
"$PYTHON" -m venv venv
venv/bin/pip install --upgrade pip

echo "=== Installing core pipeline dependencies ==="
venv/bin/pip install -r requirements.txt

if [ "${1:-}" = "--with-cde2" ]; then
    echo ""
    echo "=== Installing legacy CDE2 evidence-track stack ==="
    venv/bin/pip install -r requirements-cde2.txt

    # dawg compatibility shim (CDE2 imports `dawg`, the package is dawg-python)
    SITE=$(venv/bin/python -c "import site; print(site.getsitepackages()[0])")
    cat > "$SITE/dawg.py" << 'SHIM'
from dawg_python import *
from dawg_python import DAWG, BytesDAWG, RecordDAWG, IntDAWG, CompletionDAWG
SHIM

    echo "=== Downloading CDE2 models (NER + tokenizer) ==="
    venv/bin/cde data download

    echo "=== Verifying CDE2 ==="
    venv/bin/python -c "
import chemdataextractor as cde
from chemdataextractor import Document
from chemdataextractor.doc import Paragraph
print('CDE2 version:', cde.__version__)
doc = Document(Paragraph('Cu/ZnO showed 42% CO2 conversion at 260 °C and 3 MPa.'))
print('CEMs:', [c.text for c in doc.cems])
"
fi

echo ""
echo "=== Verifying core imports ==="
venv/bin/python -c "
import docling, anthropic, pandas, numpy, matplotlib, PIL, pdfplumber, requests
print('docling   ', getattr(docling, '__version__', '?'))
print('anthropic ', anthropic.__version__)
print('pandas    ', pandas.__version__)
print('OK')
"

echo ""
echo "Done. Next steps:"
echo "  source venv/bin/activate"
echo "  cp .env.example .env      # then set ANTHROPIC_API_KEY (LLM steps only)"
