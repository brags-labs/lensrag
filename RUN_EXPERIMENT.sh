#!/usr/bin/env bash
set -euo pipefail
python -m lensrag.cli inspect
python -m lensrag.cli run --tiers S M L --top-k 10 --output results
python -m unittest discover -s tests -v
