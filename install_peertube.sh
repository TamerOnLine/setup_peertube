#!/usr/bin/env bash
set -euo pipefail

# 🔧 PeerTube Environment Setup from GitHub

# 1) Update & upgrade system packages
apt-get update -y && apt-get upgrade -y
apt-get install -y curl git python3 sudo

# 2) Move into the script directory (the folder where this script is located)
cd "$(dirname "$0")"

# 3) Load environment variables from pt.env
set -a   # automatically export all variables
source pt.env
set +a

# 4) Run the Python setup script
python3 setup_peertube.py
