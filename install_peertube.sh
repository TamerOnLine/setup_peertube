#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive


apt-get update -y
apt-get install -y curl wget gnupg lsb-release unzip git vim ca-certificates ufw python3 sudo


cd "$(dirname "$0")"
python3 setup_peertube.py
