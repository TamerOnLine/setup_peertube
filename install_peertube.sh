#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

systemctl stop unattended-upgrades.service apt-daily.service apt-daily-upgrade.service 2>/dev/null || true
systemctl kill --kill-who=all apt-daily.service apt-daily-upgrade.service 2>/dev/null || true

while pgrep -x apt > /dev/null || pgrep -x apt-get > /dev/null || pgrep -x dpkg > /dev/null; do
  echo "[i] بستنّى عمليات apt/dpkg تخلص ..."
  sleep 5
done

apt-get update -y
apt-get install -y curl wget gnupg lsb-release unzip git vim ca-certificates ufw python3 sudo

cd "$(dirname "$0")"
python3 setup_peertube.py
