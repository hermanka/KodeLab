$ErrorActionPreference = 'Stop'
$testName = 'judgementsystem-audit-db-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$testContainer = $null
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $testContainer = docker run --rm -d --name $testName --label judgementsystem.audit=1 --network judgementsystem_platform --memory 768m --cpus 1 --tmpfs /var/lib/mysql:rw,size=268435456 -e MARIADB_ROOT_PASSWORD=isolated-audit-test-password -e MARIADB_DATABASE=audit_fix_tests -e MARIADB_USER=audit_tests -e MARIADB_PASSWORD=isolated-audit-test-password mariadb:11.4@sha256:1292844148b311e4ed4300022a996d39083f415a963e970cf47cad1b3b18e3a6
    if ($LASTEXITCODE -ne 0) { throw 'Unable to start disposable MariaDB' }
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        docker exec $testContainer healthcheck.sh --connect --innodb_initialized *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'Disposable MariaDB did not become ready' }
    docker compose run --rm --no-deps -e AUDIT_MYSQL_HOST=$testName -e DB_HOST=$testName -e DB_NAME=audit_fix_tests -e DB_USER=audit_tests -e DB_PASSWORD=isolated-audit-test-password api python -m pytest -q -p no:cacheprovider --tb=short tests/test_mariadb_concurrency.py
    if ($LASTEXITCODE -ne 0) { throw 'MariaDB concurrency regression failed' }
} finally {
    if ($testContainer) { docker stop $testContainer *> $null }
    Pop-Location
}
