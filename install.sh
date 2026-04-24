#!/usr/bin/env bash
# ============================================================
# install.sh  —  Universal entry point (no chmod needed)
# Run this after cloning:
#   bash install.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[install] Setting executable permissions..."
chmod +x setup.sh start.sh

echo "[install] Running setup..."
bash setup.sh

echo ""
echo "======================================"
echo "  Setup complete! Start the server:"
echo "  ./start.sh"
echo "======================================"
