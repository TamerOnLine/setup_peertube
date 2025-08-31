# PeerTube Auto Installer 🚀

This repository provides a **one-click installer** for [PeerTube](https://joinpeertube.org/) on **Ubuntu 22.04 / 24.04** servers.  
It automates the full setup:

- Install required packages (Node.js 20, Yarn, PostgreSQL, Redis, ffmpeg, Nginx)
- Create `peertube` system user and PostgreSQL database
- Clone the official [PeerTube repo](https://github.com/Chocobozzz/PeerTube)
- Build frontend/backend using Yarn
- Auto-generate `config/production.yaml` from environment file (`pt.env`)
- Configure Nginx reverse proxy (with WebSocket & optional HTTPS via certbot)
- Create & enable `systemd` service
- Open firewall (80/443)

---

## 📂 Repository Structure

- **`install_peertube.sh`** → Bootstrap script (stops apt locks, installs Python, runs `setup_peertube.py`).  
- **`setup_peertube.py`** → Main Python installer. Handles packages, DB, Git, Yarn build, config, Nginx, systemd.  
- **`pt.env`** → Environment configuration file for PeerTube (domain, DB, SMTP, etc.).  
- **`setup_peertube.yaml`** → Optional cloud-init file (for Hetzner / cloud providers).  

---

## ⚙️ Requirements

- Fresh **Ubuntu 22.04 or 24.04** server
- Root access (`ssh root@your-server-ip`)
- Minimum **2 GB RAM** (+swap will be added automatically if needed)
- Optional: Domain name (recommended for federation & OAuth)

---

## 🛠️ Installation

### Option 1: Cloud-init (auto at first boot)
Copy the contents of `setup_peertube.yaml` into your cloud provider's **user-data**.  
On first boot, PeerTube will be installed and started automatically.

### Option 2: Manual Installation
1. Clone the repo:
   ```bash
   git clone https://github.com/<your-org>/setup_peertube.git
   cd setup_peertube
   ```

2. Edit `pt.env`:
   ```ini
   PT_DOMAIN="videos.example.com"   # or leave empty → will fallback to server IP
   PT_HTTPS=true                    # enable HTTPS if domain is used
   PT_DB_PASS="your-strong-password"
   PT_INSTANCE_NAME="MyTube"
   PT_INSTANCE_DESC="Public PeerTube instance"
   PT_LANGUAGES="en,de,ar"
   PT_RESOLUTIONS="720p,1080p"
   PEERTUBE_REF="v7.2.3"
   ```

3. Run installer:
   ```bash
   bash install_peertube.sh
   ```

---

## 🔑 Post-Install

- Check status:
  ```bash
  systemctl status peertube
  journalctl -u peertube -n 100 --no-pager
  ```

- Default URL:
  ```
  http://<your-domain-or-ip>
  ```

- If you set `PT_HTTPS=true` and domain → installer tries automatic **Let's Encrypt** via `certbot`.  
- If no domain → PeerTube will run on your **IP**, but federation & OAuth features may be limited.

---

## 📌 Notes

- **Swap**: If build fails with exit code 137 (out-of-memory), installer creates a **4G swapfile** automatically.  
- **Nginx**: Adds `websocket_map.conf` to support WebSockets. If your `/etc/nginx/nginx.conf` doesn’t include `conf.d/*.conf`, add manually:
  ```nginx
  http {
    include /etc/nginx/conf.d/*.conf;
  }
  ```
- **SMTP**: Configure `pt.env` for email notifications (optional). Without SMTP, PeerTube runs but cannot send mails.

---

## 🧹 Management

- Restart PeerTube:
  ```bash
  systemctl restart peertube
  ```
- Logs:
  ```bash
  journalctl -u peertube -f
  ```
- Nginx reload:
  ```bash
  systemctl reload nginx
  ```

---

## 🤝 Credits

- [PeerTube](https://github.com/Chocobozzz/PeerTube) (original software)  
- This installer is maintained by **TamerOnLine**
