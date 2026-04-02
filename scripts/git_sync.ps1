# IATB Git Sync Script
# This script initializes Git repository and creates a private GitHub repo

Write-Host "=== IATB Git Sync ===" -ForegroundColor Cyan
Write-Host ""

# Check if git is installed
Write-Host "Checking Git installation..." -ForegroundColor Yellow
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Git is not installed. Please install Git first." -ForegroundColor Red
    exit 1
}
Write-Host "Git is installed: $(git --version)" -ForegroundColor Green
Write-Host ""

# Check if gh CLI is installed
Write-Host "Checking GitHub CLI installation..." -ForegroundColor Yellow
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "WARNING: GitHub CLI (gh) is not installed." -ForegroundColor Yellow
    Write-Host "Git initialization will proceed, but GitHub repo creation requires gh CLI." -ForegroundColor Yellow
    Write-Host "Visit: https://cli.github.com/" -ForegroundColor Cyan
    $ghInstalled = $false
} else {
    Write-Host "GitHub CLI is installed: $(gh --version)" -ForegroundColor Green
    $ghInstalled = $true
}
Write-Host ""

# Check if already a git repository
if (Test-Path ".git") {
    Write-Host "Git repository already initialized." -ForegroundColor Yellow
    $initGit = Read-Host "Do you want to reinitialize? (y/N)"
    if ($initGit -ne "y" -and $initGit -ne "Y") {
        Write-Host "Skipping git initialization." -ForegroundColor Yellow
    } else {
        Remove-Item -Recurse -Force ".git"
        git init
        Write-Host "Git repository reinitialized." -ForegroundColor Green
    }
} else {
    git init
    Write-Host "Git repository initialized." -ForegroundColor Green
}
Write-Host ""

# Create .gitignore if it doesn't exist
Write-Host "Creating .gitignore..." -ForegroundColor Yellow
$gitignoreContent = @"
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environments
venv/
ENV/
env/
.venv
iatb020426/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Environment variables
.env
.env.local
.env.*.local

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
.hypothesis/

# MyPy
.mypy_cache/
.dmypy.json
dmypy.json

# Ruff
.ruff_cache/

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db
"@

if (-not (Test-Path ".gitignore")) {
    $gitignoreContent | Out-File -FilePath ".gitignore" -Encoding UTF8
    Write-Host "Created .gitignore" -ForegroundColor Green
} else {
    Write-Host ".gitignore already exists" -ForegroundColor Yellow
}
Write-Host ""

# Create GitHub repository if gh CLI is available
if ($ghInstalled) {
    Write-Host "Checking GitHub authentication..." -ForegroundColor Yellow
    $authStatus = gh auth status 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARNING: Not authenticated with GitHub CLI." -ForegroundColor Yellow
        Write-Host "Run 'gh auth login' to authenticate." -ForegroundColor Cyan
    } else {
        Write-Host "Authenticated with GitHub." -ForegroundColor Green
        
        # Check if remote already exists
        $remote = git remote get-url origin 2>$null
        if ($remote) {
            Write-Host "Remote origin already exists: $remote" -ForegroundColor Yellow
            $changeRemote = Read-Host "Do you want to create a new remote? (y/N)"
            if ($changeRemote -eq "y" -or $changeRemote -eq "Y") {
                $repoName = Read-Host "Enter repository name (default: IATB-02Apr26)"
                if (-not $repoName) {
                    $repoName = "IATB-02Apr26"
                }
                
                Write-Host "Creating private GitHub repository: $repoName" -ForegroundColor Yellow
                gh repo create $repoName --private --source=. --push
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "GitHub repository created and code pushed successfully." -ForegroundColor Green
                } else {
                    Write-Host "ERROR: Failed to create GitHub repository." -ForegroundColor Red
                }
            }
        } else {
            $repoName = Read-Host "Enter repository name (default: IATB-02Apr26)"
            if (-not $repoName) {
                $repoName = "IATB-02Apr26"
            }
            
            Write-Host "Creating private GitHub repository: $repoName" -ForegroundColor Yellow
            gh repo create $repoName --private --source=. --push
            if ($LASTEXITCODE -eq 0) {
                Write-Host "GitHub repository created and code pushed successfully." -ForegroundColor Green
            } else {
                Write-Host "ERROR: Failed to create GitHub repository." -ForegroundColor Red
            }
        }
    }
} else {
    Write-Host "Skipping GitHub repository creation (gh CLI not installed)." -ForegroundColor Yellow
}
Write-Host ""

Write-Host "=== Git Sync Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Add your files: git add ." -ForegroundColor White
Write-Host "2. Commit changes: git commit -m 'Initial commit'" -ForegroundColor White
Write-Host "3. Push to remote: git push" -ForegroundColor White
Write-Host ""