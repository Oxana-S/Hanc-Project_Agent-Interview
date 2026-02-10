#!/bin/bash
# init-letsencrypt.sh - First-time SSL certificate setup for Hanc.AI
#
# Usage: ./scripts/init-letsencrypt.sh
#
# This script:
# 1. Creates dummy certificates so nginx can start
# 2. Starts nginx
# 3. Requests real certificates from Let's Encrypt
# 4. Reloads nginx with real certificates
#
# Run this ONCE on first deployment. After that, certbot auto-renews.

set -euo pipefail

# Load .env (only KEY=VALUE lines, strip inline comments)
if [ -f .env ]; then
    set -a
    . .env
    set +a
fi

DOMAIN="${DOMAIN:?ERROR: Set DOMAIN in .env}"
EMAIL="${CERTBOT_EMAIL:?ERROR: Set CERTBOT_EMAIL in .env}"
STAGING="${CERTBOT_STAGING:-0}"

DATA_PATH="./data/certbot"

echo "============================================================"
echo "  Hanc.AI — SSL Certificate Setup"
echo "============================================================"
echo ""
echo "  Domain:  $DOMAIN"
echo "  Email:   $EMAIL"
echo "  Staging: $STAGING"
echo ""
echo "============================================================"

# Step 1: Create directories
echo ""
echo ">>> [1/6] Creating directories..."
mkdir -p "$DATA_PATH/conf/live/$DOMAIN"
mkdir -p "$DATA_PATH/www"

# Step 2: Create dummy certificate for nginx to start
echo ">>> [2/6] Creating dummy certificate..."
docker compose run --rm --entrypoint "\
    openssl req -x509 -nodes -newkey rsa:4096 -days 1 \
    -keyout '/etc/letsencrypt/live/$DOMAIN/privkey.pem' \
    -out '/etc/letsencrypt/live/$DOMAIN/fullchain.pem' \
    -subj '/CN=localhost'" certbot

# Step 3: Start nginx with dummy certificate
echo ">>> [3/6] Starting nginx..."
docker compose up -d nginx

echo ">>> Waiting 5 seconds for nginx to start..."
sleep 5

# Step 4: Delete dummy certificate
echo ">>> [4/6] Deleting dummy certificate..."
docker compose run --rm --entrypoint "\
    rm -rf /etc/letsencrypt/live/$DOMAIN && \
    rm -rf /etc/letsencrypt/archive/$DOMAIN && \
    rm -rf /etc/letsencrypt/renewal/$DOMAIN.conf" certbot

# Step 5: Request real certificate
echo ">>> [5/6] Requesting Let's Encrypt certificate..."

STAGING_ARG=""
if [ "$STAGING" = "1" ]; then
    STAGING_ARG="--staging"
    echo "    (Using Let's Encrypt STAGING server — certificate will NOT be trusted)"
fi

docker compose run --rm --entrypoint "\
    certbot certonly --webroot -w /var/www/certbot \
    $STAGING_ARG \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    --force-renewal \
    -d $DOMAIN" certbot

# Step 6: Reload nginx with real certificate
echo ">>> [6/6] Reloading nginx with real certificate..."
docker compose exec nginx nginx -s reload

echo ""
echo "============================================================"
echo "  SUCCESS"
echo "============================================================"
echo ""
echo "  SSL certificate obtained for $DOMAIN"
echo "  Nginx is running with HTTPS on ports 80/443"
echo ""
echo "  Next steps:"
echo "    docker compose up -d     # start all services"
echo "    curl -I https://$DOMAIN  # verify HTTPS"
echo ""
echo "============================================================"
