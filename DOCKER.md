# Librarian Bot - Docker Deployment Guide

## Quick Start (Unraid)

### Option 1: Docker Compose (Recommended)

1. **Copy the bot to your Unraid server:**
   ```bash
   # SSH into Unraid and create directory
   mkdir -p /mnt/user/appdata/librarian-bot
   cd /mnt/user/appdata/librarian-bot
   
   # Copy all files to this directory
   # (Use WinSCP, FileZilla, or rsync)
   ```

2. **Configure environment variables:**
   ```bash
   # Copy example config
   cp config/.env.example config/.env
   
   # Edit with your settings
   nano config/.env
   ```

3. **Update volume paths in docker-compose.yml:**
   ```yaml
   volumes:
     - ./config/.env:/app/config/.env:ro
     - ./data:/app/data
     # Adjust these paths to match your Unraid shares
     - /mnt/user/BLOOM-LIBRARY:/library
     - /mnt/user/downloads/completed/MAM:/downloads
   ```

4. **Start the bot:**
   ```bash
   docker-compose up -d
   ```

5. **View logs:**
   ```bash
   docker-compose logs -f librarian-bot
   ```

### Option 2: Unraid Docker Template

Add this template to Unraid's Docker page:

**Container Settings:**
- **Name:** librarian-bot
- **Repository:** (build locally first with `docker build -t librarian-bot .`)
- **Network Type:** Bridge
- **Port Mappings:** None required (Discord bot only)

**Volume Mappings:**
1. **Config:**
   - Container Path: `/app/config/.env`
   - Host Path: `/mnt/user/appdata/librarian-bot/config/.env`
   - Access Mode: Read-only

2. **Data:**
   - Container Path: `/app/data`
   - Host Path: `/mnt/user/appdata/librarian-bot/data`
   - Access Mode: Read/Write

3. **Library:**
   - Container Path: `/library`
   - Host Path: `/mnt/user/BLOOM-LIBRARY`
   - Access Mode: Read/Write

4. **Downloads:**
   - Container Path: `/downloads`
   - Host Path: `/mnt/user/downloads/completed/MAM`
   - Access Mode: Read/Write

**Environment Variables:**
- `TZ`: `America/New_York` (adjust to your timezone)
- `PYTHONUNBUFFERED`: `1`

### Option 3: Docker CLI

```bash
# Build image
docker build -t librarian-bot .

# Run container
docker run -d \
  --name librarian-bot \
  --restart unless-stopped \
  -v /mnt/user/appdata/librarian-bot/config/.env:/app/config/.env:ro \
  -v /mnt/user/appdata/librarian-bot/data:/app/data \
  -v /mnt/user/BLOOM-LIBRARY:/library \
  -v /mnt/user/downloads/completed/MAM:/downloads \
  -e TZ=America/New_York \
  -e PYTHONUNBUFFERED=1 \
  librarian-bot
```

## Configuration Notes

### Environment File
The `.env` file in `config/` directory must contain all required variables:
- Discord bot token
- qBittorrent credentials and URL
- Prowlarr URL and API key
- Audiobookshelf URL and token
- Library paths

**Important:** Update paths in `.env` to match container paths:
```bash
# Inside container, paths should be:
LIBRARY_PATH=/library
QBITTORRENT_DOWNLOAD_PATH=/downloads
```

### SSH Key for Remote Servers
If your library is on a remote server accessed via SSH:

1. Generate SSH key in container:
   ```bash
   docker exec -it librarian-bot ssh-keygen -t rsa
   ```

2. Copy public key to remote server:
   ```bash
   docker exec -it librarian-bot cat /root/.ssh/id_rsa.pub
   # Add this to remote server's ~/.ssh/authorized_keys
   ```

3. Mount SSH directory as volume:
   ```yaml
   volumes:
     - ./ssh:/root/.ssh:ro
   ```

## Management Commands

### View Logs
```bash
# With docker-compose
docker-compose logs -f librarian-bot

# With docker
docker logs -f librarian-bot
```

### Restart Bot
```bash
# With docker-compose
docker-compose restart librarian-bot

# With docker
docker restart librarian-bot
```

### Stop Bot
```bash
# With docker-compose
docker-compose down

# With docker
docker stop librarian-bot
```

### Update Bot
```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Access Container Shell
```bash
docker exec -it librarian-bot bash
```

## Troubleshooting

### Bot Won't Start
1. Check logs: `docker-compose logs librarian-bot`
2. Verify `.env` file exists and has correct permissions
3. Ensure all required environment variables are set

### Permission Issues
```bash
# Fix data directory permissions
chmod -R 755 /mnt/user/appdata/librarian-bot/data
```

### Network Issues
- Ensure container can reach qBittorrent, Prowlarr, and Audiobookshelf
- If services are on host: use `host.docker.internal` or host IP
- If services are in other containers: use Docker network

### qBittorrent Connection Failed
- Update qBittorrent URL in `.env` to use host IP or `host.docker.internal`
- Ensure qBittorrent web UI is accessible from container network

## Unraid Specific Tips

1. **User Scripts Plugin:** Create a script to auto-start on array start
2. **CA Auto Update:** Use Community Applications to auto-update
3. **Notifications:** Configure Unraid notifications for container status
4. **Backup:** Use Appdata Backup plugin to backup `appdata/librarian-bot`

## Resource Usage

Typical resource consumption:
- **CPU:** < 5% (spikes during organization)
- **RAM:** ~100-200 MB
- **Disk:** Minimal (mainly logs and database files)

## Security Recommendations

1. Store `.env` file outside container and mount as read-only
2. Use strong passwords for all services
3. Limit container network access if possible
4. Regularly update base image and dependencies
5. Monitor logs for suspicious activity
