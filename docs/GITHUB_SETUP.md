# GitHub Setup Instructions

## Creating a GitHub Repository

Follow these steps to set up your GitHub repository and webhooks:

### 1. Create Repository on GitHub

1. Go to [github.com](https://github.com) and sign in
2. Click **New** button or go to https://github.com/new
3. Configure:
   - **Repository name**: `librarian-bot`
   - **Description**: `Discord bot for automated audiobook/ebook downloads with library organization`
   - **Public/Private**: Choose based on preference
   - **Initialize**: Don't initialize (we already have local content)
   - Click **Create repository**

### 2. Link Local Repository to GitHub

After creating the repository, GitHub will show commands. Run:

```bash
cd c:\TOOLS-LAPTOP\Projects\Librarian-Bot

# Add the remote repository
git remote add origin https://github.com/YOUR-USERNAME/librarian-bot.git

# Rename branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

Replace `YOUR-USERNAME` with your actual GitHub username.

### 3. Generate Personal Access Token (for HTTPS)

If you use HTTPS and get authentication errors:

1. Go to GitHub Settings > Developer settings > Personal access tokens
2. Click **Generate new token**
3. Select scopes: `repo` (full control of private repositories)
4. Copy the token
5. Use as password when Git prompts for it

### 4. Set Up Webhooks (Optional but Recommended)

Webhooks allow GitHub to notify your bot of repository events.

#### Webhook URL Format
```
https://your-server.com/webhook/github
```

#### To Add a Webhook:

1. Go to your repository on GitHub
2. Settings > Webhooks > Add webhook
3. Configure:
   - **Payload URL**: `https://your-server.com/webhook/github`
   - **Content type**: `application/json`
   - **Events**: Select events (see below)
   - **Active**: Check this
   - Click **Add webhook**

#### Recommended Events to Trigger:
- Push events (for auto-deployment)
- Pull request events (for CI/CD)
- Issues (for notification)
- Release events (for version tracking)

### 5. Set Up GitHub Actions (Optional CI/CD)

Create `.github/workflows/tests.yml` for automated testing:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.8', '3.9', '3.10', '3.11']
    
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest pytest-cov
    - name: Run tests
      run: pytest
```

### 6. Protect Main Branch (Recommended)

To prevent accidental pushes:

1. Go to Settings > Branches
2. Add rule for `main`
3. Check:
   - Require pull request reviews before merging
   - Require status checks to pass before merging
   - Include administrators

### 7. Useful Git Workflow Commands

```bash
# Create a new feature branch
git checkout -b feature/your-feature-name

# Make changes and commit
git add .
git commit -m "Description of changes"

# Push to GitHub
git push origin feature/your-feature-name

# Create pull request on GitHub website, then merge

# Update local main after merge
git checkout main
git pull origin main
```

### 8. Secrets Management

Store sensitive data as GitHub Secrets:

1. Go to Settings > Secrets and variables > Actions
2. Click **New repository secret**
3. Add secrets (used in GitHub Actions):
   - `DISCORD_TOKEN`
   - `PROWLARR_API_KEY`
   - `QBIT_PASSWORD`
   - etc.

Then reference in workflows:
```yaml
- run: echo ${{ secrets.DISCORD_TOKEN }}
```

### 9. Quick Reference: Common Git Commands

```bash
# Check status
git status

# See commit history
git log --oneline

# Undo last commit (local only)
git reset --soft HEAD~1

# Force push (use carefully!)
git push -f origin main

# Clone locally
git clone https://github.com/YOUR-USERNAME/librarian-bot.git

# Update from upstream
git fetch origin
git merge origin/main
```

## Next Steps

1. Create your GitHub repository
2. Push the local repo using the commands above
3. Consider setting up GitHub Actions for CI/CD
4. Enable branch protection on `main`
5. Start feature development on separate branches
