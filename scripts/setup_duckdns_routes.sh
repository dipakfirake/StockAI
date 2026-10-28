#!/bin/bash
# ==============================================================================
# StockAI — DuckDNS Nginx Routing Setup Script for:
# 1. /health/live and /health/liv (FastAPI Liveness Probes)
# 2. /docs, /redoc, /openapi.json, /swagger (FastAPI Interactive Swagger Docs)
# 3. /flower/ (Celery Flower Monitoring Dashboard)
# 4. /metrics (Prometheus Observability Telemetry)
# ==============================================================================

set -e

echo "=== [1/4] Pulling Latest StockAI Updates ==="
cd /home/opc/StockAI || cd ~/StockAI
git pull origin main

echo "=== [2/4] Restarting Backend & Celery Flower Containers ==="
sudo docker compose up -d --build backend flower

echo "=== [3/4] Detecting Nginx Configuration File ==="
CONF_FILE=""
if [ -f "/etc/nginx/conf.d/stockai.conf" ]; then
    CONF_FILE="/etc/nginx/conf.d/stockai.conf"
elif [ -f "/etc/nginx/sites-available/stockai.conf" ]; then
    CONF_FILE="/etc/nginx/sites-available/stockai.conf"
elif [ -f "/etc/nginx/conf.d/default.conf" ]; then
    CONF_FILE="/etc/nginx/conf.d/default.conf"
else
    CONF_FILE="/etc/nginx/conf.d/stockai.conf"
fi

echo "Targeting Nginx configuration: $CONF_FILE"

# Backup existing configuration
if [ -f "$CONF_FILE" ]; then
    sudo cp "$CONF_FILE" "${CONF_FILE}.bak.$(date +%s)"
fi

# Detect domain name
DOMAIN=$(grep -m1 "server_name" "$CONF_FILE" 2>/dev/null | awk '{print $2}' | tr -d ';' || echo "stockai-live.duckdns.org")
if [ -z "$DOMAIN" ] || [ "$DOMAIN" = "_" ]; then
    DOMAIN="stockai-live.duckdns.org"
fi
echo "Using Domain: $DOMAIN"

# Inject or update location blocks in Nginx config
# We write an updated snippet that preserves existing SSL certificates
cat << 'EOF' | sudo tee /tmp/stockai_locations.conf > /dev/null
    # --- Health and Liveness Probes ---
    location ~ ^/health(/.*)?$ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # --- FastAPI Swagger, ReDoc & OpenAPI Documentation ---
    location ~ ^/(docs|redoc|openapi\.json|swagger) {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # --- Celery Flower Monitoring Dashboard ---
    location /flower/ {
        proxy_pass http://127.0.0.1:5555;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location = /flower {
        return 301 /flower/;
    }

    # --- Prometheus Telemetry ---
    location /metrics {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
EOF

# If the file already has SSL configured by certbot, insert locations before the closing brace
if grep -q "location /flower/" "$CONF_FILE" 2>/dev/null; then
    echo "Flower and Swagger locations already detected in $CONF_FILE. Updating..."
    # Remove existing custom blocks and re-insert
    sudo sed -i '/# --- Health and Liveness Probes ---/,/# --- End Custom Locations ---/d' "$CONF_FILE" 2>/dev/null || true
fi

# Insert into the server block before the last closing brace
python3 -c "
import re

with open('$CONF_FILE', 'r') as f:
    content = f.read()

with open('/tmp/stockai_locations.conf', 'r') as f:
    snippet = '\n' + f.read() + '\n'

if 'location ~ ^/(docs|redoc|openapi\.json|swagger)' not in content:
    # Find last closing brace of the main server block
    pos = content.rfind('}')
    if pos != -1:
        new_content = content[:pos] + snippet + content[pos:]
        with open('$CONF_FILE', 'w') as f:
            f.write(new_content)
        print('Successfully injected /health/live, /docs, and /flower/ into $CONF_FILE')
    else:
        print('Could not find closing brace in $CONF_FILE')
else:
    print('Locations already present in $CONF_FILE')
"

echo "=== [4/4] Validating & Reloading Nginx ==="
sudo nginx -t
sudo systemctl reload nginx

echo ""
echo "🎉 SUCCESS! All DuckDNS routes are now active:"
echo "👉 Health Liveness Probe: https://${DOMAIN}/health/live (also /health/liv)"
echo "👉 Swagger Documentation: https://${DOMAIN}/docs (also /swagger)"
echo "👉 Celery Flower:        https://${DOMAIN}/flower/"
echo ""
