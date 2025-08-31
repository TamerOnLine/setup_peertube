# setup_peertube

🚀 Quick installer for [PeerTube](https://joinpeertube.org/) on Ubuntu servers using GitHub.

---

## 1. Manual Installation

```bash
# Clone this repository
git clone https://github.com/TamerOnLine/setup_peertube.git
cd setup_peertube

# Edit environment variables (⚠️ set PT_DB_PASS and PT_DOMAIN!)
nano pt.env

# Run installer
sudo bash install_peertube.sh
```

---

## 2. Cloud-Init (automatic on new server)

When creating a new Ubuntu server (22.04/24.04), paste this into the **User-Data / cloud-init** field:

```yaml
#cloud-config
runcmd:
  - git clone https://github.com/TamerOnLine/setup_peertube.git /root/setup_peertube
  - cd /root/setup_peertube && bash install_peertube.sh
```

This will automatically pull the repo and run the installer on first boot.

---

## 3. Environment Variables (`pt.env`)

Before running the installer, edit `pt.env`:

- `PT_DB_PASS` → Database password (**required**).  
- `PT_DOMAIN` → Domain name or server IP (**required**).  
- `PT_HTTPS` → `true` if you have a valid domain + SSL, otherwise `false`.  
- `PT_WEB_PORT` → Web port (default `9000`).  
- **SMTP settings** → Configure if you want emails (optional).  
- `PT_INSTANCE_NAME` / `PT_INSTANCE_DESC` → Name & description of your instance.  
- `PT_LANGUAGES` → Default languages (`en,de,ar`).  
- `PT_RESOLUTIONS` → Video resolutions (`720p,1080p`).  

---

## 4. Service Management

After installation, PeerTube runs as a systemd service:

```bash
# Check status
sudo systemctl status peertube

# Restart service
sudo systemctl restart peertube

# View logs
sudo journalctl -u peertube -n 50 --no-pager
```

---

## 5. Access Your Instance

- If `PT_HTTPS=false` → **http://YOUR_DOMAIN_OR_IP**  
- If `PT_HTTPS=true`  → **https://YOUR_DOMAIN**

---

## 6. Notes

- Default database user: `peertube`  
- Default database name: `peertube`  
- Make sure ports 80/443 are open in firewall.  
- If you use HTTPS, Certbot will auto-request a Let’s Encrypt certificate.  

---

✅ That’s it — simple PeerTube setup directly from GitHub!
