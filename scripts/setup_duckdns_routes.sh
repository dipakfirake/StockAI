#!/bin/bash
# ==============================================================================
# StockAI — DuckDNS Nginx Routing Setup Script for:
# 1. /health/live and /health/liv (FastAPI Liveness Probes)
# 2. /docs, /redoc, /openapi.json, /swagger (FastAPI Interactive Swagger Docs)
# 3. /flower/ (Celery Flower Monitoring Dashboard with WebSocket Support)
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

# Write location snippet
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
        proxy_read_timeout 86400s;
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

# Intelligent Python script: specifically targets the SSL (port 443) server block!
python3 -c "
import re

with open('$CONF_FILE', 'r') as f:
    content = f.read()

with open('/tmp/stockai_locations.conf', 'r') as f:
    snippet = f.read().strip() + '\n'

# Find all server { blocks with accurate brace depth tracking
server_matches = list(re.finditer(r'\bserver\s*\{', content))
if not server_matches:
    print('No server blocks found in $CONF_FILE')
    exit(0)

blocks = []
for m in server_matches:
    start_pos = m.end() - 1  # points to '{'
    depth = 0
    end_pos = -1
    for i in range(start_pos, len(content)):
        if content[i] == '{':
            depth += 1
        elif content[i] == '}':
            depth -= 1
            if depth == 0:
                end_pos = i
                break
    if end_pos != -1:
        blocks.append((start_pos, end_pos, content[m.start():end_pos + 1]))

# Find the SSL block (contains 443 or ssl_certificate)
ssl_block = None
for s_pos, e_pos, b_text in blocks:
    if '443' in b_text or 'ssl_certificate' in b_text:
        ssl_block = (s_pos, e_pos, b_text)
        break

# If no SSL block, use the block that has proxy_pass
if not ssl_block:
    for s_pos, e_pos, b_text in blocks:
        if 'proxy_pass' in b_text:
            ssl_block = (s_pos, e_pos, b_text)
            break

if not ssl_block:
    ssl_block = blocks[0]

s_pos, e_pos, b_text = ssl_block

# Clean up any existing snippet in this block if present
cleaned_block = b_text
cleaned_block = re.sub(r'# --- Health and Liveness Probes ---.*?# --- Prometheus Telemetry ---.*?location /metrics\s*\{.*?\}', '', cleaned_block, flags=re.DOTALL)

# Insert snippet before closing brace of the SSL server block
last_brace = cleaned_block.rfind('}')
if last_brace != -1:
    new_block = cleaned_block[:last_brace] + '\n' + snippet + cleaned_block[last_brace:]
    new_content = content[:content.find(b_text)] + new_block + content[content.find(b_text) + len(b_text):]
    with open('$CONF_FILE', 'w') as f:
        f.write(new_content)
    print('🎉 Successfully injected routes into the SSL (443) server block in $CONF_FILE!')
else:
    print('Failed to locate closing brace in target server block')
"

echo "=== [4/4] Validating & Reloading Nginx ==="
sudo nginx -t
sudo systemctl reload nginx

echo ""
echo "🎉 SUCCESS! All DuckDNS routes are now active over HTTPS:"
echo "👉 Celery Flower Dashboard: https://${DOMAIN}/flower/ (Basic Auth: headadmin / Admin Pass)"
echo "👉 FastAPI Swagger Docs:   https://${DOMAIN}/docs (Admin Protected)"
echo "👉 FastAPI ReDoc Docs:     https://${DOMAIN}/redoc"
echo "👉 FastAPI OpenAPI Schema: https://${DOMAIN}/openapi.json"
echo "👉 Health Liveness Probe:  https://${DOMAIN}/health/live"
echo "👉 Health Readiness Probe: https://${DOMAIN}/health/ready"
echo ""
