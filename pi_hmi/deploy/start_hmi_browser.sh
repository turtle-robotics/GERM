#!/bin/bash

# Wait for Flask to be ready
echo "Waiting for Flask..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:5000 > /dev/null 2>&1; then
        echo "Flask is up!"
        break
    fi
    sleep 1
done

# Launch Chromium in kiosk mode
chromium \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=Translate \
  --disable-background-networking \
  --disable-sync \
  --disable-gcm \
  --disable-push-messaging \
  --disable-gpu-vsync \
  --ignore-gpu-blocklist \
  --check-for-update-interval=31536000 \
  --ozone-platform=wayland \
  http://127.0.0.1:5000 &
