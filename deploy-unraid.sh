#!/bin/bash
# Deploy Librarian Bot to Unraid Server
# Usage: ./deploy-unraid.sh <server> [user] [target-path]

set -e

SERVER=${1:-}
USER=${2:-root}
TARGET_PATH=${3:-/mnt/user/appdata/librarian-bot}

if [ -z "$SERVER" ]; then
    echo "❌ Usage: ./deploy-unraid.sh <server> [user] [target-path]"
    echo "Example: ./deploy-unraid.sh 192.168.1.100"
    exit 1
fi

echo "🚀 Deploying Librarian Bot to Unraid..."
echo "Server: $SERVER"
echo "User: $USER"
echo "Target Path: $TARGET_PATH"
echo ""

# Check if git repo is clean
echo "📋 Checking git status..."
if [ -n "$(git status --porcelain)" ]; then
    echo "⚠️  Warning: You have uncommitted changes:"
    git status --short
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Deployment cancelled"
        exit 1
    fi
fi

# Create target directory on Unraid
echo "📁 Creating target directory on Unraid..."
ssh $USER@$SERVER "mkdir -p $TARGET_PATH"

# Sync files using rsync
echo "📦 Syncing files to Unraid..."
echo "This may take a minute..."

rsync -avz --progress \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.vscode' \
    --exclude='venv' \
    --exclude='*.log' \
    --exclude='data/.*.json' \
    . $USER@$SERVER:$TARGET_PATH/

echo "✅ Files synced successfully!"
echo ""

# Check if .env file exists
echo "🔍 Checking configuration..."
if ssh $USER@$SERVER "test -f $TARGET_PATH/config/.env"; then
    echo "✅ Configuration file exists"
else
    echo "⚠️  config/.env not found on server!"
    echo "Creating from example..."
    ssh $USER@$SERVER "cd $TARGET_PATH && cp config/.env.example config/.env"
    echo "📝 Please edit $TARGET_PATH/config/.env on the server with your settings"
fi

echo ""
echo "🐳 Docker deployment options:"
echo "1. Start with Docker Compose: ssh $USER@$SERVER 'cd $TARGET_PATH && docker-compose up -d'"
echo "2. View logs: ssh $USER@$SERVER 'cd $TARGET_PATH && docker-compose logs -f librarian-bot'"
echo "3. Restart: ssh $USER@$SERVER 'cd $TARGET_PATH && docker-compose restart librarian-bot'"
echo ""

# Ask if user wants to start the container
read -p "Start the Docker container now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🚀 Starting Docker container..."
    ssh $USER@$SERVER "cd $TARGET_PATH && docker-compose up -d"
    
    echo "✅ Container started successfully!"
    sleep 2
    echo ""
    echo "📋 Container logs:"
    ssh $USER@$SERVER "cd $TARGET_PATH && docker-compose logs --tail=30 librarian-bot"
fi

echo ""
echo "✅ Deployment complete!"
echo "📖 See DOCKER.md for more management commands"
