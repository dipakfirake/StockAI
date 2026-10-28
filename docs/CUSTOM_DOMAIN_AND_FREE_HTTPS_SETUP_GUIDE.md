# Production Guide: Custom Domain & 100% Free HTTPS (Let's Encrypt + Nginx)

This guide walks you through connecting your **own domain name** (e.g., `yourdomain.com`) to your StockAI server (`92.4.71.210`) with **100% Free HTTPS (`https://`)**, zero Cloudflare tunneling, and an **A+ Security Rating**.

---

## Architecture Overview

```
[ User Browser ]
       │
       ▼ (Encrypted HTTPS on Port 443)
┌────────────────────────────────────────────────────────┐
│  UBUNTU HOST NGINX REVERSE PROXY                       │
│  - SSL/TLS 1.3 Termination (Let's Encrypt)             │
│  - HTTP -> HTTPS Automatic 301 Redirect                │
│  - HSTS & Anti-Clickjacking Defense Headers            │
└─────────────┬──────────────────────────┬───────────────┘
              │ (Internal Proxy)         │ (Internal Proxy)
              ▼                          ▼
     [ StockFrontend :5173 ]    [ StockBackend :8000 ]
                                         │
                                         ▼
                               [ PostgreSQL & Redis ]
                               (Strictly Isolated!)
```

---

## Step 1: Point Your Domain DNS to Your Server IP

1. Log in to your domain registrar (GoDaddy, Namecheap, Hostinger, BigRock, Google Domains, etc.).
2. Go to **DNS Management** for your domain.
3. Add these two **A Records**:

| Type | Name / Host | Points to / Value | TTL |
| :--- | :--- | :--- | :--- |
| **A** | `@` *(root domain)* | `92.4.71.210` | 300 / 1/2 hour (or Auto) |
| **A** | `www` | `92.4.71.210` | 300 / 1/2 hour (or Auto) |

> ⏱ **Verification:** Wait 2 to 5 minutes, then open your local terminal/command prompt and run:
> ```bash
> ping yourdomain.com
> ```
> If it replies with `92.4.71.210`, your DNS is live!

---

## Step 2: Open Ports 80 and 443 in Firewalls

Let's Encrypt requires **Port 80** to verify domain ownership and **Port 443** to serve secure HTTPS.

### 2.1 Oracle Cloud Security List
1. Open [cloud.oracle.com](https://cloud.oracle.com) and log in.
2. Navigate to **Networking** $\to$ **Virtual Cloud Networks** $\to$ Click your VCN.
3. Click **Security Lists** in the left sidebar $\to$ Click **Default Security List**.
4. Click **Add Ingress Rules**:
   - **Source Type**: `CIDR`
   - **Source CIDR**: `0.0.0.0/0`
   - **IP Protocol**: `TCP`
   - **Destination Port Range**: `80,443`
   - **Description**: `Allow HTTP and HTTPS`
5. Click **Add Ingress Rules**.

### 2.2 Server Operating System Firewall
SSH into your Oracle Cloud VM and run:

**For Oracle Linux / RHEL (default on Oracle Cloud):**
```bash
sudo firewall-cmd --permanent --add-service=http --add-service=https 2>/dev/null || true
sudo firewall-cmd --reload 2>/dev/null || true
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
```

**For Ubuntu / Debian:**
```bash
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true
```

---

## Step 3: Install Nginx & Certbot on the Server

**For Oracle Linux (default on Oracle Cloud):**
```bash
# Enable EPEL (Extra Packages for Enterprise Linux)
sudo dnf install -y oracle-epel-release-el8 2>/dev/null || sudo dnf install -y oracle-epel-release-el9 2>/dev/null || sudo dnf install -y epel-release

# Install Nginx and Certbot
sudo dnf install -y nginx certbot python3-certbot-nginx
sudo systemctl enable --now nginx
```

**For Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
sudo systemctl enable --now nginx
```

---

## Step 4: Configure Hardened Nginx Reverse Proxy

Create an Nginx configuration file in `/etc/nginx/conf.d/stockai.conf` (or `/etc/nginx/sites-available/stockai.conf` on Ubuntu):


Paste the following configuration into the file (**Replace `yourdomain.com` with your actual domain**):

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Maximum payload limit (matches StockAI 1MB body limit guard)
    client_max_body_size 10M;

    # Frontend React App (Vite Dev / Prod)
    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend FastAPI REST Endpoints
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 60s;
    }

    # Real-Time WebSocket Connections (Live Ticker & Presence)
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

Enable the configuration and restart Nginx:
```bash
# Link to enabled sites
sudo ln -sf /etc/nginx/sites-available/stockai.conf /etc/nginx/sites-enabled/

# Remove default nginx welcome page
sudo rm -f /etc/nginx/sites-enabled/default

# Test configuration syntax
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

---

## Step 5: Generate Free Let's Encrypt SSL Certificate

Run this single command (**Replace `yourdomain.com` with your actual domain**):

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### What Certbot will prompt:
1. **Email Address**: Enter your Gmail address (used strictly for urgent security and renewal alerts).
2. **Terms of Service**: Press `Y` and Enter.
3. **Share Email with EFF?**: Press `N` and Enter.

Certbot will automatically:
- Verify domain ownership.
- Fetch trusted cryptographic certificates from the official Certificate Authority.
- Inject hardened SSL configurations into your Nginx setup.
- Enable automatic **HTTP $\to$ HTTPS permanent redirect** (anyone typing `http://` is automatically sent to `https://`).

---

## Step 6: Add A+ Grade Security Headers

To ensure your platform achieves an **A+ Security Rating** on Qualys SSL Labs, open your Nginx config:
```bash
sudo nano /etc/nginx/sites-available/stockai.conf
```

Look for the `server { listen 443 ssl ...` block that Certbot just created, and add these lines right under `server_name`:

```nginx
    # Institutional Cybersecurity Hardening Headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

Save and reload:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## Step 7: Verify Automatic SSL Renewal (Free Forever)

Let's Encrypt certificates are valid for 90 days. Certbot installs a systemd timer that automatically checks and renews your certificate before it expires:

```bash
sudo certbot renew --dry-run
```

When you see:
`Congratulations, all simulated renewals succeeded`
Your SSL is completely autonomous and 100% maintenance-free!

---

## Step 8: Update Google OAuth Authorized Origins

Now that your site runs on your custom domain with HTTPS:
1. Go back to [Google Cloud Console](https://console.cloud.google.com/) $\to$ **APIs & Services** $\to$ **Credentials**.
2. Click on your **StockAI Web Client**.
3. Under **Authorized JavaScript origins**, click **+ ADD URI** and add:
   - `https://yourdomain.com`
   - `https://www.yourdomain.com`
4. Click **SAVE**.

---

## Final Result

Open your browser and navigate to:
`https://yourdomain.com`

* **Secure Green Padlock**: Validated by Let's Encrypt Authority.
* **100% Free Forever**: Zero ongoing fees, zero credit cards.
* **Zero Middlemen**: Direct encrypted connection to your Oracle Cloud VM.
* **Protected Core**: PostgreSQL, Redis, and internal containers are completely inaccessible to external port scanners.
