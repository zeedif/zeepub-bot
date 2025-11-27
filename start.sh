#!/bin/bash

# Start cloudflared in the background if token is present
if [ -n "$TUNNEL_TOKEN" ]; then
    echo "Starting Cloudflare Tunnel..."
    cloudflared tunnel run --token "$TUNNEL_TOKEN" &
else
    echo "WARNING: TUNNEL_TOKEN not set. Cloudflare Tunnel will not start."
fi

# Start the bot
echo "Starting ZeePub Bot..."
exec python run_with_api.py
