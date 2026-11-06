param([ValidateSet('smoke', 'smoke_authoring', 'smoke_plugins')][string]$Suite = 'smoke')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$settings = @{}
foreach ($line in [System.IO.File]::ReadAllLines((Join-Path $taskRoot '.env'))) {
    if ($line -match '^(BOOTSTRAP_ADMIN_USERNAME|BOOTSTRAP_ADMIN_PASSWORD)=(.*)$') {
        $settings[$Matches[1]] = $Matches[2]
    }
}
if (-not $settings['BOOTSTRAP_ADMIN_PASSWORD']) { throw 'Run scripts/init-env.ps1 and bootstrap the administrator first.' }
$payload = @{username=$settings['BOOTSTRAP_ADMIN_USERNAME']; password=$settings['BOOTSTRAP_ADMIN_PASSWORD']} | ConvertTo-Json -Compress
Push-Location $taskRoot
try {
    $payload | docker compose exec -T api python ('scripts/' + $Suite + '.py')
    $result = $LASTEXITCODE
} finally { Pop-Location }
exit $result
