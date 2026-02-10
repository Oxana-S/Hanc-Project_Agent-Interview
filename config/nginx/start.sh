#!/bin/sh
set -e

# Process nginx template — substitute only $DOMAIN, leave nginx vars ($host etc.) intact
envsubst '$DOMAIN' < /etc/nginx/templates/nginx.conf.template > /etc/nginx/nginx.conf

# Auto-reload every 6 hours to pick up renewed SSL certificates
while :; do sleep 6h & wait $!; nginx -s reload; done &

# Start nginx in foreground
exec nginx -g "daemon off;"
