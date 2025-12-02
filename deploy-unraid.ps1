# Deploy Librarian Bot to Unraid Server
# Usage: .\deploy-unraid.ps1 -Server "your-unraid-ip" -User "root"

param(
    [Parameter(Mandatory=$true)]
    [string]$Server,
    
    [Parameter(Mandatory=$false)]
    [string]$User = "root",
    
    [Parameter(Mandatory=$false)]
    [string]$TargetPath = "/mnt/user/appdata/librarian-bot"
)

Write-Host "🚀 Deploying Librarian Bot to Unraid..." -ForegroundColor Cyan
Write-Host "Server: $Server" -ForegroundColor Yellow
Write-Host "User: $User" -ForegroundColor Yellow
Write-Host "Target Path: $TargetPath" -ForegroundColor Yellow
Write-Host ""

# Check if git repo is clean
Write-Host "📋 Checking git status..." -ForegroundColor Cyan
$gitStatus = git status --porcelain
if ($gitStatus) {
    Write-Host "⚠️  Warning: You have uncommitted changes:" -ForegroundColor Yellow
    git status --short
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne "y") {
        Write-Host "❌ Deployment cancelled" -ForegroundColor Red
        exit 1
    }
}

# Create target directory on Unraid
Write-Host "📁 Creating target directory on Unraid..." -ForegroundColor Cyan
ssh $User@$Server "mkdir -p $TargetPath"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to create directory on Unraid" -ForegroundColor Red
    exit 1
}

# Sync files using rsync (excluding unnecessary files)
Write-Host "📦 Syncing files to Unraid..." -ForegroundColor Cyan
Write-Host "This may take a minute..." -ForegroundColor Gray

# Check if rsync is available
$rsyncExists = Get-Command rsync -ErrorAction SilentlyContinue
if (-not $rsyncExists) {
    Write-Host "⚠️  rsync not found, using scp instead (slower)..." -ForegroundColor Yellow
    Write-Host "Installing rsync is recommended for faster deployments" -ForegroundColor Gray
    
    # Use scp as fallback
    scp -r `
        -o "ControlMaster=auto" `
        -o "ControlPath=/tmp/ssh-%r@%h:%p" `
        -o "ControlPersist=10m" `
        . "$User@$Server`:$TargetPath/"
} else {
    # Use rsync (much faster for updates)
    rsync -avz --progress `
        --exclude='.git' `
        --exclude='__pycache__' `
        --exclude='*.pyc' `
        --exclude='.vscode' `
        --exclude='venv' `
        --exclude='*.log' `
        --exclude='data/.*.json' `
        . "$User@$Server`:$TargetPath/"
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to sync files to Unraid" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Files synced successfully!" -ForegroundColor Green
Write-Host ""

# Check if .env file exists
Write-Host "🔍 Checking configuration..." -ForegroundColor Cyan
$envExists = ssh $User@$Server "test -f $TargetPath/config/.env && echo 'exists' || echo 'missing'"

if ($envExists -eq "missing") {
    Write-Host "⚠️  config/.env not found on server!" -ForegroundColor Yellow
    Write-Host "Creating from example..." -ForegroundColor Gray
    ssh $User@$Server "cd $TargetPath && cp config/.env.example config/.env"
    Write-Host "📝 Please edit $TargetPath/config/.env on the server with your settings" -ForegroundColor Yellow
} else {
    Write-Host "✅ Configuration file exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "🐳 Docker deployment options:" -ForegroundColor Cyan
Write-Host "1. Start with Docker Compose: ssh $User@$Server 'cd $TargetPath && docker-compose up -d'" -ForegroundColor Gray
Write-Host "2. View logs: ssh $User@$Server 'cd $TargetPath && docker-compose logs -f librarian-bot'" -ForegroundColor Gray
Write-Host "3. Restart: ssh $User@$Server 'cd $TargetPath && docker-compose restart librarian-bot'" -ForegroundColor Gray
Write-Host ""

# Ask if user wants to start the container
$startNow = Read-Host "Start the Docker container now? (y/n)"
if ($startNow -eq "y") {
    Write-Host "🚀 Starting Docker container..." -ForegroundColor Cyan
    ssh $User@$Server "cd $TargetPath && docker-compose up -d"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Container started successfully!" -ForegroundColor Green
        Start-Sleep -Seconds 2
        Write-Host ""
        Write-Host "📋 Container logs:" -ForegroundColor Cyan
        ssh $User@$Server "cd $TargetPath && docker-compose logs --tail=30 librarian-bot"
    } else {
        Write-Host "❌ Failed to start container" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host "📖 See DOCKER.md for more management commands" -ForegroundColor Gray
