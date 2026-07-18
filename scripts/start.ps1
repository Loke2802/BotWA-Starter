Write-Host ""
Write-Host "====================================="
Write-Host "        BotWA Development"
Write-Host "====================================="
Write-Host ""

Write-Host "[1/3] Starting PostgreSQL..."

docker compose up -d db

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Failed to start PostgreSQL."
    Write-Host "Check Docker Desktop and run 'docker compose logs db' for details."
    exit 1
}

Write-Host "OK: PostgreSQL is ready."
Write-Host ""

Write-Host "[2/3] Running database migrations..."

docker compose run --rm api alembic upgrade head

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Database migration failed."
    Write-Host "Review the Alembic output above."
    exit 1
}

Write-Host "OK: Database schema is up to date."
Write-Host ""

Write-Host "[3/3] Starting BotWA..."

docker compose up