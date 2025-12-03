#!/bin/bash
# Update librarian-bot on Unraid server

set -e

echo "🔄 Pulling latest code..."
cd /mnt/user/appdata/librarian-bot
git pull origin WIP

echo "📝 Updating .env with SERVER_MODE=local..."
# Add SERVER_MODE if it doesn't exist, update if it does
if grep -q "^SERVER_MODE=" config/.env; then
    sed -i 's/^SERVER_MODE=.*/SERVER_MODE=local/' config/.env
else
    echo "" >> config/.env
    echo "# Server Mode: local (run organizer in container) or seedbox (run via SSH)" >> config/.env
    echo "SERVER_MODE=local" >> config/.env
fi

echo "✅ Updated configuration:"
grep -E "SERVER_MODE|LIBRARY_PATH|QBIT_DOWNLOAD_PATH" config/.env

echo ""
echo "🛑 Stopping container..."
docker stop librarian-bot
docker rm librarian-bot

echo "🔨 Rebuilding Docker image..."
docker build -t librarian-bot .

echo "🚀 Starting container..."
docker run -d --name librarian-bot --restart unless-stopped \
  -v /mnt/user/appdata/librarian-bot/config/.env:/app/config/.env:ro \
  -v /mnt/user/appdata/librarian-bot/data:/app/data \
  -v /mnt/user/upload/Other/Library/BLOOM-Library:/library \
  -v /mnt/user/upload/Other/Library/Downloads:/downloads \
  -e TZ=America/New_York \
  -e PYTHONUNBUFFERED=1 \
  librarian-bot

echo ""
echo "✅ Update complete! Checking logs..."
sleep 3
docker logs librarian-bot --tail 20
