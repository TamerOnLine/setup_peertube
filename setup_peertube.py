import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List, Optional

# ==========================================
# Default configuration (can be overridden)
# ==========================================
DEFAULTS: Dict[str, Any] = {
    "domain": os.environ.get("PT_DOMAIN", "videos.example.com"),
    "https": os.environ.get("PT_HTTPS", "true"),  # "true" | "false"
    "web_port": int(os.environ.get("PT_WEB_PORT", "9000")),
    "pt_user": os.environ.get("PT_USER", "peertube"),
    "pt_home": os.environ.get("PT_HOME", "/var/www"),
    "db_host": os.environ.get("PT_DB_HOST", "127.0.0.1"),
    "db_port": int(os.environ.get("PT_DB_PORT", "5432")),
    "db_user": os.environ.get("PT_DB_USER", "peertube"),
    "db_pass": os.environ.get("PT_DB_PASS", "CHANGE_ME_DB_PASS"),
    "db_name": os.environ.get("PT_DB_NAME", "peertube"),
    "db_ssl": os.environ.get("PT_DB_SSL", "false"),
    "smtp_host": os.environ.get("PT_SMTP_HOST", ""),
    "smtp_port": int(os.environ.get("PT_SMTP_PORT", "587")),
    "smtp_user": os.environ.get("PT_SMTP_USER", ""),
    "smtp_pass": os.environ.get("PT_SMTP_PASS", ""),
    "smtp_tls": os.environ.get("PT_SMTP_TLS", "true"),
    "smtp_disable_starttls": os.environ.get(
        "PT_SMTP_DISABLE_STARTTLS", "false"
    ),
    "from_address": os.environ.get(
        "PT_FROM_ADDRESS", "PeerTube <no-reply@videos.example.com>"
    ),
    "instance_name": os.environ.get("PT_INSTANCE_NAME", "MyTube"),
    "instance_desc": os.environ.get(
        "PT_INSTANCE_DESC", "Public PeerTube instance"
    ),
    "languages": os.environ.get("PT_LANGUAGES", "en,de,ar"),
    "resolutions": os.environ.get("PT_RESOLUTIONS", "720p,1080p"),
    "enable_signup": os.environ.get("PT_ENABLE_SIGNUP", "false"),
    "requires_approval": os.environ.get("PT_REQUIRES_APPROVAL", "true"),
    "requires_email_verification": os.environ.get(
        "PT_REQUIRES_EMAIL_VERIFICATION", "false"
    ),
    "keep_original": os.environ.get("PT_KEEP_ORIGINAL", "false"),
    "hls_enabled": os.environ.get("PT_HLS_ENABLED", "true"),
    "web_videos_enabled": os.environ.get("PT_WEB_VIDEOS_ENABLED", "false"),
}

PEERTUBE_REPO = "https://github.com/Chocobozzz/PeerTube.git"
PEERTUBE_BRANCH = "production"

SITE_FILE = "/etc/nginx/sites-available/peertube"
SERVICE_FILE = "/etc/systemd/system/peertube.service"


def log(msg: str) -> None:
    """Print an informational message.

    Args:
        msg: The message to print.
    """

    print(f"[i] {msg}")



def warn(msg: str) -> None:
    """Print a warning message to stderr.

    Args:
        msg: The warning text to print.
    """

    print(f"[!] {msg}", file=sys.stderr)



def run(
    cmd: Any,
    check: bool = True,
    shell: bool = False,
    env: Optional[Dict[str, str]] = None,
    user: Optional[str] = None,
    cwd: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Run a command and print it before execution.

    This utility supports running as another user via sudo. When a list is
    provided, it is joined to a printable representation. If a string is
    provided and ``shell`` is False, the command is split using ``shlex``.

    Args:
        cmd: Command to execute (string or list).
        check: Whether to raise if the command exits with a non-zero status.
        shell: Whether to run through the shell.
        env: Optional environment variables to pass to the process.
        user: If set and current user is root, wrap with ``sudo -u``.
        cwd: Optional working directory.

    Returns:
        The ``subprocess.CompletedProcess`` instance.
    """

    if isinstance(cmd, str) and not shell:
        cmd_show = cmd
        cmd_list: List[str] = shlex.split(cmd)
    elif isinstance(cmd, list):
        cmd_list = cmd
        cmd_show = " ".join(shlex.quote(c) for c in cmd)
    else:
        cmd_list = cmd
        cmd_show = cmd if isinstance(cmd, str) else " ".join(cmd)

    if user and os.geteuid() == 0:
        # Wrap with sudo -u <user> bash -lc "cd ... && <cmd>"
        if cwd:
            inner = f"cd {shlex.quote(str(cwd))} && {cmd_show}"
        else:
            inner = cmd_show
        full = ["sudo", "-u", user, "bash", "-lc", inner]
        print(f"$ {' '.join(shlex.quote(s) for s in full)}")
        return subprocess.run(full, check=check, text=True, env=env)

    if cwd:
        print(f"(cd {cwd})$ {cmd_show}")
    else:
        print(f"$ {cmd_show}")
    return subprocess.run(
        cmd_list if not shell else cmd,
        check=check,
        shell=shell,
        text=True,
        env=env,
        cwd=cwd,
    )



def require_root() -> None:
    """Exit the program if it is not executed as root.

    Raises:
        SystemExit: If the effective UID is not 0.
    """

    if os.geteuid() != 0:
        warn("Please run this script as root (e.g., sudo python3 setup_peertube.py)")
        sys.exit(1)



def is_ip(host: str) -> bool:
    """Return True if the given host string looks like an IPv4 address.

    Args:
        host: Hostname or IP string.

    Returns:
        True if ``host`` matches a simple IPv4 dotted-quad pattern; otherwise
        False.
    """

    return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host))



def ensure_packages() -> None:
    """Install required system packages and enable core services.

    Notes:
        - Updates apt cache, installs Node.js 20, Yarn (via Corepack or npm),
          PostgreSQL, Redis, FFmpeg, Nginx, and Certbot.
        - Enables and starts Redis, PostgreSQL, and Nginx services.
    """

    log("Updating system and installing base packages...")
    run("apt-get update -y")
    run(
        "DEBIAN_FRONTEND=noninteractive apt-get install -y "
        "curl wget gnupg lsb-release unzip git vim ca-certificates ufw"
    )

    log("Installing Node.js 20 and Corepack/Yarn...")
    run("curl -fsSL https://deb.nodesource.com/setup_20.x | bash -", shell=True)
    run("apt-get install -y nodejs")
    try:
        run("corepack enable", check=False)
        run("yarn --version", check=False)
    except Exception:
        pass

    if subprocess.run(["bash", "-lc", "command -v yarn >/dev/null 2>&1"]).returncode != 0:
        warn("Corepack did not enable yarn; installing yarn globally via npm...")
        run("npm install -g yarn")

    log("Installing PostgreSQL, Redis, FFmpeg, Nginx, and Certbot...")
    run(
        "apt-get install -y postgresql postgresql-contrib redis-server ffmpeg "
        "nginx certbot python3-certbot-nginx"
    )

    log("Enabling and starting required services...")
    run("systemctl enable --now redis-server postgresql nginx")



def ensure_user(user: str, home: str) -> None:
    """Ensure the PeerTube system user exists and its home directory is created.

    Args:
        user: Username to ensure.
        home: Home directory path.
    """

    import pwd

    try:
        pwd.getpwnam(user)
        log(f"User {user} already exists.")
    except KeyError:
        log(f"Creating user {user} ...")
        run(["adduser", "--disabled-password", "--gecos", "", user])

    Path(home).mkdir(parents=True, exist_ok=True)



def ensure_db(user: str, password: str, dbname: str) -> None:
    """Ensure PostgreSQL role and database exist for PeerTube.

    Args:
        user: Database username.
        password: Database user password.
        dbname: Database name.
    """

    log("Configuring PostgreSQL (role and database)...")
    cmd_exists_user = (
        f"sudo -u postgres psql -tAc \"SELECT 1 FROM pg_roles "
        f"WHERE rolname='{user}'\""
    )
    ret = subprocess.run(cmd_exists_user, shell=True, text=True, capture_output=True)
    if "1" not in ret.stdout:
        run(
            f"sudo -u postgres psql -c \"CREATE USER {user} WITH PASSWORD "
            f"'{password}';\"",
            shell=True,
        )

    cmd_exists_db = (
        f"sudo -u postgres psql -tAc \"SELECT 1 FROM pg_database "
        f"WHERE datname='{dbname}'\""
    )
    ret = subprocess.run(cmd_exists_db, shell=True, text=True, capture_output=True)
    if "1" not in ret.stdout:
        run(
            f"sudo -u postgres psql -c \"CREATE DATABASE {dbname} OWNER {user};\"",
            shell=True,
        )



def clone_or_update_repo(
    repo_url: str, dest: str, user: str, branch: Optional[str] = None
) -> None:
    """Clone the repository if missing, otherwise fetch and reset/pull.

    Args:
        repo_url: Git repository URL.
        dest: Destination directory path.
        user: System user to run git as.
        branch: Optional branch name to checkout/reset to.
    """

    dest_path = Path(dest)
    if not dest_path.exists():
        log(f"Cloning {repo_url} → {dest}")
        run(f"git clone {shlex.quote(repo_url)} {shlex.quote(dest)}", user=user)
        if branch:
            run(f"git checkout {shlex.quote(branch)}", user=user, cwd=dest)
    else:
        log(f"Updating repository at {dest} ...")
        run("git fetch --all", user=user, cwd=dest)
        if branch:
            run(
                f"git reset --hard origin/{shlex.quote(branch)}",
                user=user,
                cwd=dest,
            )
        else:
            run("git pull --rebase", user=user, cwd=dest)



def ensure_yarn_install(pt_dir: str, user: str) -> None:
    """Run ``yarn install`` for production dependencies in the PeerTube repo.

    Args:
        pt_dir: Path to the PeerTube repository.
        user: System user to run yarn as.
    """

    log("Running yarn install for dependencies...")
    run("yarn install --production --pure-lockfile", user=user, cwd=pt_dir)



def gen_secret_hex(nbytes: int = 32) -> str:
    """Generate a random hexadecimal secret.

    Args:
        nbytes: Number of random bytes to generate.

    Returns:
        A hex string of length ``2 * nbytes``.
    """

    return os.urandom(nbytes).hex()



def bool_str(x: Any) -> str:
    """Return a canonical lowercase boolean string ("true" or "false").

    Args:
        x: A truthy/falsey value; strings like "1", "true", "yes", "on" are
           considered true.

    Returns:
        "true" or "false".
    """

    if isinstance(x, bool):
        return "true" if x else "false"
    s = str(x).strip().lower()
    return "true" if s in {"1", "true", "yes", "y", "on"} else "false"



def build_production_yaml(
    https: Any,
    domain: str,
    web_port: int,
    secret_value: str,
    db_host: str,
    db_port: int,
    db_user: str,
    db_pass: str,
    db_name: Optional[str] = None,
    db_ssl: Any = False,
    smtp_host: Optional[str] = None,
    smtp_port: int = 587,
    smtp_user: Optional[str] = None,
    smtp_pass: Optional[str] = None,
    smtp_tls: Any = False,
    smtp_starttls_disable: Any = False,
    from_address: str = "PeerTube <no-reply@example.com>",
    instance_name: str = "PeerTube",
    instance_desc: str = "Welcome to this PeerTube instance!",
    languages: Optional[List[str]] = None,
    enable_signup: Any = False,
    requires_approval: Any = True,
    requires_email_verification: Any = False,
    video_quota: str = "-1",
    video_quota_daily: str = "-1",
    hls_enabled: Any = True,
    web_videos_enabled: Any = False,
    transcoding_keep_original: Any = False,
    resolutions: Optional[List[str]] = None,
) -> str:
    """Build a PeerTube ``production.yaml`` file as a string.

    The output is intended to be written to ``config/production.yaml``.

    Args:
        https: Whether HTTPS is enabled.
        domain: The public hostname for the instance.
        web_port: Internal HTTP port to proxy to.
        secret_value: Random secret used by PeerTube.
        db_host: Database host.
        db_port: Database port.
        db_user: Database user.
        db_pass: Database password.
        db_name: Database name.
        db_ssl: Whether to enable SSL for DB connection.
        smtp_host: SMTP hostname or None to disable.
        smtp_port: SMTP port.
        smtp_user: SMTP username or None.
        smtp_pass: SMTP password or None.
        smtp_tls: Whether to use TLS for SMTP.
        smtp_starttls_disable: Whether to disable STARTTLS.
        from_address: Default from address used by emails.
        instance_name: Instance display name.
        instance_desc: Instance description.
        languages: Preferred languages list.
        enable_signup: Whether user signup is enabled.
        requires_approval: Whether signup requires manual approval.
        requires_email_verification: Whether email verification is required.
        video_quota: Global upload quota per user ("-1" for unlimited).
        video_quota_daily: Daily upload quota per user ("-1" for unlimited).
        hls_enabled: Whether HLS is enabled.
        web_videos_enabled: Whether web videos are enabled.
        transcoding_keep_original: Whether to keep original uploaded files.
        resolutions: List of target resolutions (e.g., ["720p", "1080p"]).

    Returns:
        The YAML contents as a single string.
    """

    if languages is None:
        languages = []
    if resolutions is None:
        resolutions = ["720p", "1080p"]

    res_keys = [
        "0p",
        "144p",
        "240p",
        "360p",
        "480p",
        "720p",
        "1080p",
        "1440p",
        "2160p",
    ]
    res_map = {k: ("true" if k in resolutions else "false") for k in res_keys}

    langs_yaml = (
        "\n".join([f"    - {lang}" for lang in languages])
        if languages
        else "    # - en\n    # - de\n    # - ar"
    )

    yaml_text = f"""# Generated by setup_peertube.py
# Do NOT commit this file to Git. It contains secrets.

webserver:
  https: {bool_str(https)}
  hostname: '{domain}'
  port: {int(web_port)}

secrets:
  peertube: '{secret_value}'

database:
  hostname: '{db_host}'
  port: {int(db_port)}
  ssl: {bool_str(db_ssl)}
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
  hostname: {('null' if not smtp_host else "'" + smtp_host + "'")}
  port: {int(smtp_port)}
  username: {('null' if not smtp_user else "'" + smtp_user + "'")}
  password: {('null' if not smtp_pass else "'" + smtp_pass + "'")}
  tls: {bool_str(smtp_tls)}
  disable_starttls: {bool_str(smtp_starttls_disable)}
  ca_file: null
  from_address: '{from_address}'

signup:
  enabled: {bool_str(enable_signup)}
  limit: 10
  minimum_age: 16
  requires_approval: {bool_str(requires_approval)}
  requires_email_verification: {bool_str(requires_email_verification)}
  filters:
    cidr:
      whitelist: []
      blacklist: []

instance:
  name: '{instance_name}'
  short_description: '{instance_name}'
  description: '{instance_desc}'
  default_client_route: '/videos/trending'
  is_nsfw: false
  default_nsfw_policy: 'do_not_list'
  languages:
{langs_yaml}

user:
  history:
    videos:
      enabled: true
  video_quota: {video_quota}
  video_quota_daily: {video_quota_daily}
  default_channel_name: 'Main $1 channel'

transcoding:
  enabled: true
  original_file:
    keep: {bool_str(transcoding_keep_original)}
  allow_additional_extensions: true
  allow_audio_files: true
  remote_runners:
    enabled: false
  threads: 1
  concurrency: 1
  profile: 'default'
  resolutions:
    0p: {res_map['0p']}
    144p: {res_map['144p']}
    240p: {res_map['240p']}
    360p: {res_map['360p']}
    480p: {res_map['480p']}
    720p: {res_map['720p']}
    1080p: {res_map['1080p']}
    1440p: {res_map['1440p']}
    2160p: {res_map['2160p']}
  always_transcode_original_resolution: true
  web_videos:
    enabled: {bool_str(web_videos_enabled)}
  hls:
    enabled: {bool_str(hls_enabled)}

live:
  enabled: false

log:
  level: 'info'
  rotation:
    enabled: true
    max_file_size: 12MB
    max_files: 20
  log_http_requests: true

contact_form:
  enabled: true
"""
    return yaml_text



def write_file(
    path: Path,
    content: str,
    mode: int = 0o600,
    owner_user: Optional[str] = None,
    owner_group: Optional[str] = None,
) -> None:
    """Write text to a file with permissions and optional ownership.

    Args:
        path: Path to write.
        content: Text content to write.
        mode: File mode to set after writing.
        owner_user: Optional owner username to chown to.
        owner_group: Optional owner group name to chown to.

    Notes:
        If ownership change fails, a warning is printed but execution continues.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    os.chmod(path, mode)
    if owner_user and owner_group:
        try:
            import grp
            import pwd

            uid = pwd.getpwnam(owner_user).pw_uid
            gid = grp.getgrnam(owner_group).gr_gid
            os.chown(path, uid, gid)
        except Exception as exc:  # noqa: BLE001 - broad by design for logging only
            warn(f"Could not change ownership: {exc}")



def configure_nginx(domain: str, web_port: int) -> None:
    """Write an Nginx reverse proxy config and reload Nginx.

    Args:
        domain: Public domain name.
        web_port: Internal port to proxy to.
    """

    log("Configuring Nginx as a reverse proxy for the internal port...")
    site_conf = (
        dedent(
            f"""
            server {{
              server_name {domain};
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
            """
        ).strip()
        + "\n"
    )
    Path(SITE_FILE).write_text(site_conf, encoding="utf-8")
    run(f"ln -sf {SITE_FILE} /etc/nginx/sites-enabled/peertube")
    run("nginx -t")
    run("systemctl reload nginx")



def enable_https_if_needed(domain: str, https: Any) -> None:
    """Run Certbot for HTTPS if enabled and the domain is not an IP.

    Args:
        domain: The public domain.
        https: Truthy/falsey to decide whether to enable HTTPS.
    """

    if bool_str(https) != "true":
        log("HTTPS=false → skipping certificate issuance.")
        return
    if is_ip(domain):
        warn(
            "The domain looks like an IP. Skipping Certbot (a real domain is "
            "required for HTTPS certificates)."
        )
        return
    email = f"admin@{domain}"
    log("Running Certbot to issue HTTPS certificate...")
    run(
        f"certbot --nginx -d {shlex.quote(domain)} --non-interactive --agree-tos "
        f"-m {shlex.quote(email)}",
        check=False,
    )



def write_systemd_service(pt_dir: str, pt_user: str) -> None:
    """Create and manage a systemd service unit for PeerTube.

    Args:
        pt_dir: Path to the PeerTube repository working directory.
        pt_user: System user to run the service as.
    """

    if not Path(SERVICE_FILE).exists():
        log("Creating systemd unit for PeerTube...")
        unit = (
            dedent(
                f"""
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
                """
            ).strip()
            + "\n"
        )
        Path(SERVICE_FILE).write_text(unit, encoding="utf-8")
    run("systemctl daemon-reload")
    run("systemctl enable peertube", check=False)
    run("systemctl restart peertube", check=False)
    run("sleep 3", shell=True)
    run("systemctl status peertube --no-pager -n 50", check=False)



def ufw_allow_http_https() -> None:
    """Allow inbound HTTP and HTTPS through UFW if it is installed."""

    if (
        subprocess.run(["bash", "-lc", "command -v ufw >/dev/null 2>&1"]).returncode
        == 0
    ):
        run("ufw allow 80/tcp", check=False)
        run("ufw allow 443/tcp", check=False)



def parse_args(argv: List[str]) -> Dict[str, Any]:
    """Parse ``--key=value`` pairs from the CLI and overlay onto DEFAULTS.

    Args:
        argv: ``sys.argv``-style list of command-line arguments.

    Returns:
        A configuration dictionary derived from DEFAULTS with any keys
        overridden by parsed command-line options.

    Notes:
        Numeric keys (``web_port``, ``db_port``, ``smtp_port``) are coerced to
        integers when possible. If the default ``from_address`` is unchanged,
        it is updated to use the provided domain.
    """

    cfg: Dict[str, Any] = DEFAULTS.copy()
    for arg in argv[1:]:
        if arg.startswith("--") and "=" in arg:
            key, value = arg[2:].split("=", 1)
            key = key.strip().replace("-", "_")
            if key in cfg:
                if key in {"web_port", "db_port", "smtp_port"}:
                    try:
                        cfg[key] = int(value)
                    except Exception:
                        cfg[key] = int(cfg[key])
                else:
                    cfg[key] = value

    if cfg["from_address"] == "PeerTube <no-reply@videos.example.com>":
        cfg["from_address"] = f"PeerTube <no-reply@{cfg['domain']}>"
    return cfg



def main() -> None:
    """Run the end-to-end setup routine for a PeerTube instance.

    Steps:
        1. Ensure root privileges.
        2. Parse configuration from environment and CLI.
        3. Install required packages and services.
        4. Ensure system user and PostgreSQL database.
        5. Clone or update the PeerTube repository.
        6. Install Node dependencies via Yarn.
        7. Generate and write ``config/production.yaml``.
        8. Configure Nginx and HTTPS (Certbot) if applicable.
        9. Create/manage the systemd service.
        10. Allow HTTP/HTTPS in UFW if available.

    Notes:
        The script avoids changing core logic and focuses on orchestration and
        configuration generation.
    """

    require_root()
    cfg = parse_args(sys.argv)

    pt_user = cfg["pt_user"]
    pt_home = Path(cfg["pt_home"])
    pt_dir = pt_home / "peertube"

    ensure_packages()
    ensure_user(pt_user, str(pt_home))
    ensure_db(cfg["db_user"], cfg["db_pass"], cfg["db_name"])

    if not pt_dir.exists():
        run(
            f"git clone -b {PEERTUBE_BRANCH} {PEERTUBE_REPO} {shlex.quote(str(pt_dir))}",
            user=pt_user,
        )
    else:
        run("git fetch --all", user=pt_user, cwd=str(pt_dir))
        run(
            f"git reset --hard origin/{PEERTUBE_BRANCH}",
            user=pt_user,
            cwd=str(pt_dir),
        )

    ensure_yarn_install(str(pt_dir), pt_user)

    secret = gen_secret_hex()
    langs = [s.strip() for s in str(cfg["languages"]).split(",") if s.strip()]
    ress = [s.strip() for s in str(cfg["resolutions"]).split(",") if s.strip()]
    yaml_text = build_production_yaml(
        https=cfg["https"],
        domain=cfg["domain"],
        web_port=cfg["web_port"],
        secret_value=secret,
        db_host=cfg["db_host"],
        db_port=cfg["db_port"],
        db_user=cfg["db_user"],
        db_pass=cfg["db_pass"],
        db_name=cfg["db_name"],
        db_ssl=cfg["db_ssl"],
        smtp_host=cfg["smtp_host"] or None,
        smtp_port=cfg["smtp_port"],
        smtp_user=cfg["smtp_user"] or None,
        smtp_pass=cfg["smtp_pass"] or None,
        smtp_tls=cfg["smtp_tls"],
        smtp_starttls_disable=cfg["smtp_disable_starttls"],
        from_address=cfg["from_address"],
        instance_name=cfg["instance_name"],
        instance_desc=cfg["instance_desc"],
        languages=langs,
        enable_signup=cfg["enable_signup"],
        requires_approval=cfg["requires_approval"],
        requires_email_verification=cfg["requires_email_verification"],
        video_quota="-1",
        video_quota_daily="-1",
        hls_enabled=cfg["hls_enabled"],
        web_videos_enabled=cfg["web_videos_enabled"],
        transcoding_keep_original=cfg["keep_original"],
        resolutions=ress,
    )

    config_path = pt_dir / "config" / "production.yaml"
    write_file(
        config_path,
        yaml_text,
        mode=0o600,
        owner_user=pt_user,
        owner_group=pt_user,
    )
    log(f"Created {config_path}")

    configure_nginx(cfg["domain"], cfg["web_port"])
    enable_https_if_needed(cfg["domain"], cfg["https"])

    write_systemd_service(str(pt_dir), pt_user)

    ufw_allow_http_https()

    proto = "https" if bool_str(cfg["https"]) == "true" else "http"
    print("\n================= ✅ Completed =================")
    print(f"URL: {proto}://{cfg['domain']}")
    print("Status: systemctl status peertube")
    print("Logs: journalctl -u peertube -n 100 --no-pager")
    print("Path: ", pt_dir)


if __name__ == "__main__":
    main()
