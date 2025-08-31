#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
setup_peertube.py
Automatically install PeerTube on Ubuntu 22.04/24.04:
- Update packages, install Node 20 + Yarn, PostgreSQL + Redis + ffmpeg + Nginx + Certbot
- Create user/database
- Clone PeerTube (production branch) + install dependencies
- Generate config/production.yaml dynamically from pt.env
- Set up Nginx + systemd service
"""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

PEERTUBE_REPO = "https://github.com/Chocobozzz/PeerTube.git"
PEERTUBE_BRANCH = "production"
PT_USER_DEFAULT = "peertube"
PT_HOME = "/var/www"
NGINX_SITE = "/etc/nginx/sites-available/peertube"
NGINX_LINK = "/etc/nginx/sites-enabled/peertube"
SYSTEMD_UNIT = "/etc/systemd/system/peertube.service"


# ========= Helper Functions =========

def log(msg: str):
    print(f"[i] {msg}")

def warn(msg: str):
    print(f"[!] {msg}", file=sys.stderr)

def run(cmd, *, check=True, shell=False, user=None, cwd=None, env=None):
    """
    Run a command with optional user and working directory context.
    Automatically handles shell commands and sudo as needed.
    """
    if isinstance(cmd, str):
        show = cmd
        cmd_list = cmd if shell else shlex.split(cmd)
    else:
        show = " ".join(shlex.quote(str(c)) for c in cmd)
        cmd_list = cmd

    if user and os.geteuid() == 0:
        inner = f"cd {shlex.quote(str(cwd))} && {show}" if cwd else show
        full = ["sudo", "-u", user, "bash", "-lc", inner]
        print("$ " + " ".join(shlex.quote(s) for s in full))
        return subprocess.run(full, check=check, text=True, env=env)
    else:
        if cwd:
            print(f"(cd {cwd})$ {show}")
        else:
            print(f"$ {show}")
        return subprocess.run(cmd_list, check=check, text=True, shell=shell, cwd=cwd, env=env)


def need_root():
    if os.geteuid() != 0:
        warn("Run as root.")
        sys.exit(1)


def get_env_bool(s, default=False):
    v = os.environ.get(s, str(default)).strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


def to_yaml_bool(x) -> str:
    return "true" if (x if isinstance(x, bool) else str(x).strip().lower() in {"1", "true", "yes", "y", "on"}) else "false"


def detect_ipv4():
    try:
        out = subprocess.check_output(["bash", "-lc", "hostname -I | awk '{print $1}'"], text=True).strip()
        return out or "127.0.0.1"
    except Exception:
        return "127.0.0.1"


def is_ipv4(host):
    return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", str(host).strip()))


def load_pt_env_if_exists():
    """
    Load environment variables from pt.env in the current directory.
    """
    p = Path("pt.env")
    if not p.exists():
        warn("pt.env not found in current directory; using defaults.")
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


# ========= Main =========

def main():
    need_root()
    load_pt_env_if_exists()
    log("Environment loaded. Ready for formatting or extension.")


if __name__ == "__main__":
    main()
