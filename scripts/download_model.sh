#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

URL="${AOE_MODEL_URL:-https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf}"
DEST="models/qwen2.5-1.5b-instruct-q4_k_m.gguf"

mkdir -p models
echo "Downloading $URL"
curl -fL --retry 3 --progress-bar -o "$DEST.tmp" "$URL"
mv "$DEST.tmp" "$DEST"
echo "Saved: $DEST ($(du -h "$DEST" | cut -f1))"
