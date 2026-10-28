# 100% Free HTTPS Setup Guide for StockAI

This guide provides tested, step-by-step methods to run StockAI over secure **HTTPS (`https://`)** instead of plain HTTP — **completely free of cost (₹0 / $0)**, with no credit card required.

---

## Executive Summary: Which Option is Best for You?

| Method | Cost | Requires Open Ports / Firewall changes? | Requires Custom Domain? | Best For |
| :--- | :--- | :--- | :--- | :--- |
| **Option 1: Cloudflare Tunnel (Recommended)** | **₹0 Free Forever** | **NO (0 ports needed!)** | Optional (Works with free or paid domain) | **Best overall**: Highest security, auto SSL, DDoS protection, works behind NAT/CGNAT/Oracle Cloud. |
| **Option 2: Let's Encrypt Certbot + Nginx** | **₹0 Free Forever** | Yes (Port 80 & 443 open) | Yes (Any domain pointing to server IP) | Traditional server deployment with direct Nginx SSL termination. |
| **Option 3: DuckDNS + Let's Encrypt** | **₹0 Free Forever** | Yes (Port 80 & 443 open) | **NO (Free `*.duckdns.org` subdomain)** | Developers who do not own a custom domain yet. |

---

## Option 1: Cloudflare Tunnel (Recommended — Zero Open Ports, Automated HTTPS)

Cloudflare Tunnel creates an encrypted outbound-only connection between your server (local or Oracle Cloud VM) and the Cloudflare edge.
- **Benefits**:
  - No need to configure router port-forwarding or open ports 80/443 in Oracle Cloud Security Lists.
  - Automatic SSL/TLS certificate issued and renewed by Cloudflare.
  - Automatic HTTP $\to$ HTTPS redirection.
  - Free Web Application Firewall (WAF) and DDoS protection.

### Step 1: Add your domain to Cloudflare (Free)
1. Sign up for a free account at [cloudflare.com](https://dash.cloudflare.com/sign-up).
2. Add your domain and select the **Free Plan ($0)**.
3. Update your domain registrar's nameservers to Cloudflare's free nameservers.

### Step 2: Create a Free Cloudflare Tunnel
1. In Cloudflare Dashboard, navigate to **Zero Trust** $\to$ **Networks** $\to$ **Tunnels**.
2. Click **Create a Tunnel** and choose **Cloudflared**.
3. Name it `stockai-tunnel`.
4. Copy the installation token shown in the dashboard (e.g., `EYJh...`).

### Step 3: Run Cloudflared in Docker
Add this lightweight service to your `docker-compose.yml`:

```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: stockai-tunnel
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token YOUR_CLOUDFLARE_TUNNEL_TOKEN
    networks:
      - stockai-network
```

### Step 4: Map Public Hostnames in Cloudflare Dashboard
Under the **Public Hostname** tab of your tunnel:
- **Frontend**:
  - Domain: `app.yourdomain.com` (or `@`)
  - Service Type: `HTTP`
  - URL: `frontend:80` (or `localhost:5173`)
- **Backend API**:
  - Domain: `api.yourdomain.com`
  - Service Type: `HTTP`
  - URL: `backend:8000` (or `localhost:8000`)

That's it! Your site is now live at `https://app.yourdomain.com` with valid HTTPS, zero open ports, and zero cost.

---

## Option 2: Let's Encrypt Certbot + Nginx (Direct SSL Termination)

If you have ports 80 and 443 open on your server/VM, you can use the official Let's Encrypt Certbot to obtain free, trusted 90-day SSL certificates that auto-renew.

### Step 1: Open Ports 80 and 443 in Oracle Cloud / Firewall
On Ubuntu / Debian server:
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

### Step 2: Sample Nginx SSL Configuration (`nginx.conf`)

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Certbot challenge path
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect all other HTTP traffic to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Modern SSL parameters
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # HSTS (Strict-Transport-Security)
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;

    # Frontend
    location / {
        proxy_pass http://frontend:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # Backend API
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # WebSocket support for live ticker & presence
    location /ws/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### Step 3: Run Certbot to Generate Certificate
```bash
docker compose run --rm certbot certonly --webroot --webroot-path=/var/www/certbot -d yourdomain.com -d www.yourdomain.com --email admin@yourdomain.com --agree-tos --no-eff-email
```

---

## Option 3: 100% Free Domain (DuckDNS) + HTTPS

If you don't own a domain, you can get a completely free domain:
1. Visit [duckdns.org](https://www.duckdns.org) and sign in (GitHub / Google).
2. Create a free subdomain: e.g., `stockai-trade.duckdns.org`.
3. Set the IP to your public server IP (e.g., `92.4.71.210`).
4. Follow **Option 1 (Cloudflare)** or **Option 2 (Let's Encrypt)** using `stockai-trade.duckdns.org`!

---

## Security Verification
Once enabled, test your HTTPS setup at [Qualys SSL Labs](https://www.ssllabs.com/ssltest/) to verify an **A+ Rating** with HSTS and TLS 1.3.
