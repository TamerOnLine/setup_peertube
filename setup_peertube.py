#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_peertube.py
تثبيت PeerTube تلقائيًا على Ubuntu 22.04/24.04:
- تحديث الحزم وتثبيت Node 20 + Yarn، PostgreSQL + Redis + ffmpeg + Nginx
- إنشاء مستخدم/قاعدة بيانات
- جلب PeerTube من المستودع الرسمي (بدون افتراض اسم فرع)
- تثبيت اعتمادات Node
- توليد config/production.yaml من pt.env
- إعداد Nginx + خدمة systemd
- (اختياري) فتح منافذ UFW إن وُجد
"""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

# === إعدادات المستودع (لا تفترض فرعًا ثابتًا) ===
PEERTUBE_REPO = "https://github.com/Chocobozzz/PeerTube.git"
# مرجع اختياري: فرع أو وسم (tag). مثال: "main" أو "v7.2.3".
# إذا تُرك فارغًا → يستخدم الفرع الافتراضي للمستودع.
PEERTUBE_REF  = os.environ.get("PEERTUBE_REF", "").strip()

# === مسارات وخدمة ===
PT_USER_DEFAULT = "peertube"
PT_HOME = "/var/www"
NGINX_SITE = "/etc/nginx/sites-available/peertube"
NGINX_LINK = "/etc/nginx/sites-enabled/peertube"
SYSTEMD_UNIT = "/etc/systemd/system/peertube.service"

def log(m): print(f"[i] {m}")
def warn(m): print(f"[!] {m}", file=sys.stderr)

def run(cmd, *, check=True, shell=False, user=None, cwd=None, env=None):
    """
    تنفيذ أمر مع طباعة. استخدم shell=True عند تمرير متغيرات بيئة inline مثل:
    DEBIAN_FRONTEND=noninteractive apt-get ...
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

def get_env_bool(k, default=False):
    v = os.environ.get(k, str(default)).strip().lower()
    return v in {"1","true","yes","y","on"}

def to_yaml_bool(x):
    return "true" if (x if isinstance(x, bool) else str(x).strip().lower() in {"1","true","yes","y","on"}) else "false"

def detect_ipv4():
    try:
        out = subprocess.check_output(["bash","-lc","hostname -I | awk '{print $1}'"], text=True).strip()
        return out or "127.0.0.1"
    except Exception:
        return "127.0.0.1"

def is_ipv4(h):
    return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", str(h).strip()))

def load_pt_env_if_exists():
    p = Path("pt.env")
    if not p.exists():
        warn("pt.env not found; using defaults.")
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" in s:
            k, v = s.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

# === تثبيت الحزم ===
def ensure_packages():
    log("Update & base packages...")
    run("apt-get update -y", shell=True)
    run("DEBIAN_FRONTEND=noninteractive apt-get install -y curl wget gnupg lsb-release unzip git vim ca-certificates ufw", shell=True)

    log("Install Node.js 20 + Yarn...")
    if subprocess.run(["bash","-lc","node -v | grep -q '^v20'"]).returncode != 0:
        run("curl -fsSL https://deb.nodesource.com/setup_20.x | bash -", shell=True)
        run("apt-get install -y nodejs", shell=True)
    if subprocess.run(["bash","-lc","command -v yarn >/dev/null 2>&1"]).returncode != 0:
        run("npm install -g yarn", shell=True, check=False)

    log("Install Postgres/Redis/ffmpeg/Nginx...")
    run("DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql postgresql-contrib redis-server ffmpeg nginx", shell=True)
    run("systemctl enable --now redis-server postgresql nginx", check=False)

# === مستخدم وخدمة قاعدة البيانات ===
def ensure_pt_user(user, home):
    import pwd
    try:
        pwd.getpwnam(user)
        log(f"user {user} exists")
    except KeyError:
        run(["adduser", "--disabled-password", "--gecos", "", user])
    Path(home).mkdir(parents=True, exist_ok=True)

def ensure_db(db_user, db_pass, db_name):
    log("Configure PostgreSQL...")
    q1 = f"SELECT 1 FROM pg_roles WHERE rolname='{db_user}'"
    q2 = f"SELECT 1 FROM pg_database WHERE datname='{db_name}'"
    r = subprocess.run(f"sudo -u postgres psql -tAc \"{q1}\"", shell=True, text=True, capture_output=True)
    if "1" not in r.stdout:
        pw = db_pass.replace("'", "''")  # SQL escape
        run(f"sudo -u postgres psql -c \"CREATE USER {db_user} WITH PASSWORD '{pw}';\"", shell=True)
    r = subprocess.run(f"sudo -u postgres psql -tAc \"{q2}\"", shell=True, text=True, capture_output=True)
    if "1" not in r.stdout:
        run(f"sudo -u postgres psql -c \"CREATE DATABASE {db_name} OWNER {db_user};\"", shell=True)

# === جلب/تحديث PeerTube من المستودع ===
def clone_or_update_peertube(pt_dir: Path, pt_user: str):
    if not pt_dir.exists():
        # كلون بدون افتراض فرع
        run(f"git clone {PEERTUBE_REPO} {shlex.quote(str(pt_dir))}", shell=True)
        if PEERTUBE_REF:
            run(f"git checkout {shlex.quote(PEERTUBE_REF)}", user=pt_user, cwd=str(pt_dir))
        run(f"chown -R {pt_user}:{pt_user} {shlex.quote(str(pt_dir))}", shell=True)
    else:
        run("git fetch --all --tags", user=pt_user, cwd=str(pt_dir))
        if PEERTUBE_REF:
            run(f"git checkout {shlex.quote(PEERTUBE_REF)}", user=pt_user, cwd=str(pt_dir))
        run("git pull --ff-only", user=pt_user, cwd=str(pt_dir), check=False)

    # تثبيت الاعتمادات
    run("yarn install --production --pure-lockfile", user=pt_user, cwd=str(pt_dir))

# === توليد production.yaml من pt.env ===
def build_production_yaml_from_env():
    domain = os.environ.get("PT_DOMAIN", "").strip()
    https  = get_env_bool("PT_HTTPS", False)
    web_port = int(os.environ.get("PT_WEB_PORT", "9000"))

    db_host = os.environ.get("PT_DB_HOST", "127.0.0.1")
    db_port = int(os.environ.get("PT_DB_PORT", "5432"))
    db_user = os.environ.get("PT_DB_USER", "peertube")
    db_pass = os.environ.get("PT_DB_PASS", "CHANGE_ME_DB_PASS")
    db_name = os.environ.get("PT_DB_NAME", "peertube")
    db_ssl  = get_env_bool("PT_DB_SSL", False)

    smtp_host = os.environ.get("PT_SMTP_HOST", "")
    smtp_port = int(os.environ.get("PT_SMTP_PORT", "587"))
    smtp_user = os.environ.get("PT_SMTP_USER", "")
    smtp_pass = os.environ.get("PT_SMTP_PASS", "")
    smtp_tls  = get_env_bool("PT_SMTP_TLS", True)
    smtp_disable_starttls = get_env_bool("PT_SMTP_DISABLE_STARTTLS", False)
    from_address = os.environ.get("PT_FROM_ADDRESS", "")

    instance_name = os.environ.get("PT_INSTANCE_NAME", "MyTube")
    instance_desc = os.environ.get("PT_INSTANCE_DESC", "Public PeerTube instance")
    languages = [s.strip() for s in os.environ.get("PT_LANGUAGES", "en,de,ar").split(",") if s.strip()]
    resolutions = [s.strip() for s in os.environ.get("PT_RESOLUTIONS", "720p,1080p").split(",") if s.strip()]

    if not domain:
        domain = detect_ipv4()
    if not from_address:
        from_address = f"PeerTube <no-reply@{domain}>"

    # خريطة الريزوليوشن
    res_keys = ["0p","144p","240p","360p","480p","720p","1080p","1440p","2160p"]
    res_map = {k: ("true" if k in resolutions else "false") for k in res_keys}

    secret_hex = os.urandom(32).hex()

    yml = f"""# Generated by setup_peertube.py
webserver:
  https: {to_yaml_bool(https)}
  hostname: '{domain}'
  port: {web_port}
secrets:
  peertube: '{secret_hex}'
database:
  hostname: '{db_host}'
  port: {db_port}
  ssl: {to_yaml_bool(db_ssl)}
  username: '{db_user}'
  password: '{db_pass}'
  name: '{db_name}'
redis:
  hostname: '127.0.0.1'
  port: 6379
  auth: null
  db: 0
smtp:
  transport: smtp
  hostname: {("null" if not smtp_host else "'"+smtp_host+"'")}
  port: {smtp_port}
  username: {("null" if not smtp_user else "'"+smtp_user+"'")}
  password: {("null" if not smtp_pass else "'"+smtp_pass+"'")}
  tls: {to_yaml_bool(smtp_tls)}
  disable_starttls: {to_yaml_bool(smtp_disable_starttls)}
  ca_file: null
  from_address: '{from_address}'
signup:
  enabled: false
  requires_approval: true
  requires_email_verification: false
instance:
  name: '{instance_name}'
  short_description: '{instance_name}'
  description: '{instance_desc}'
  languages:
{chr(10).join("    - "+l for l in languages)}
transcoding:
  enabled: true
  original_file:
    keep: false
  web_videos:
    enabled: false
  hls:
    enabled: true
  resolutions:
    0p: {res_map["0p"]}
    144p: {res_map["144p"]}
    240p: {res_map["240p"]}
    360p: {res_map["360p"]}
    480p: {res_map["480p"]}
    720p: {res_map["720p"]}
    1080p: {res_map["1080p"]}
    1440p: {res_map["1440p"]}
    2160p: {res_map["2160p"]}
"""
    return yml, domain, https, web_port

def write_production_yaml(pt_dir: Path, content: str, owner: str):
    cfg = pt_dir / "config" / "production.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(content, encoding="utf-8")
    try:
        import pwd, grp
        os.chown(str(cfg), pwd.getpwnam(owner).pw_uid, grp.getgrnam(owner).gr_gid)
        os.chmod(str(cfg), 0o600)
    except Exception:
        pass
    log(f"Wrote {cfg}")

# === Nginx (reverse proxy بسيط) ===
def configure_nginx(server_name: str, web_port: int):
    if not server_name:
        server_name = "_"
    conf = dedent(f"""
    server {{
      server_name {server_name};
      listen 80;
      listen [::]:80;
      location / {{
        proxy_pass http://127.0.0.1:{web_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 600s;
        proxy_send_timeout    600s;
        proxy_read_timeout    600s;
        send_timeout          600s;
      }}
    }}
    """).strip() + "\n"
    Path(NGINX_SITE).write_text(conf, encoding="utf-8")
    if not Path(NGINX_LINK).exists():
        try:
            os.symlink(NGINX_SITE, NGINX_LINK)
        except FileExistsError:
            pass
    run("nginx -t", shell=True)
    run("systemctl reload nginx", shell=True)

def write_systemd_unit(pt_dir: Path, pt_user: str):
    unit = dedent(f"""
    [Unit]
    Description=PeerTube
    After=postgresql.service redis-server.service

    [Service]
    User={pt_user}
    WorkingDirectory={pt_dir}
    Environment=NODE_ENV=production
    ExecStart=/usr/bin/node dist/server
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
    """).strip() + "\n"
    Path(SYSTEMD_UNIT).write_text(unit, encoding="utf-8")
    run("systemctl daemon-reload", shell=True)
    run("systemctl enable peertube", shell=True, check=False)
    run("systemctl restart peertube", shell=True, check=False)
    run("sleep 2", shell=True)
    run("systemctl status peertube --no-pager -n 50", shell=True, check=False)

def ufw_open_http_https():
    if subprocess.run(["bash","-lc","command -v ufw >/dev/null 2>&1"]).returncode == 0:
        run("ufw allow 80/tcp", shell=True, check=False)
        run("ufw allow 443/tcp", shell=True, check=False)

# === main ===
def main():
    need_root()
    load_pt_env_if_exists()

    pt_user = os.environ.get("PT_USER", PT_USER_DEFAULT)
    pt_home = PT_HOME
    pt_dir  = Path(pt_home) / "peertube"

    ensure_packages()
    ensure_pt_user(pt_user, pt_home)
    ensure_db(
        os.environ.get("PT_DB_USER", "peertube"),
        os.environ.get("PT_DB_PASS", "CHANGE_ME_DB_PASS"),
        os.environ.get("PT_DB_NAME", "peertube"),
    )

    clone_or_update_peertube(pt_dir, pt_user)

    yml, domain, https, web_port = build_production_yaml_from_env()
    write_production_yaml(pt_dir, yml, pt_user)

    configure_nginx(domain, web_port)
    write_systemd_unit(pt_dir, pt_user)
    ufw_open_http_https()

    proto = "https" if https else "http"
    print("\n==== DONE ====")
    print(f"URL: {proto}://{domain}")
    print("systemctl status peertube")
    print("journalctl -u peertube -n 100 --no-pager")

if __name__ == "__main__":
    main()
