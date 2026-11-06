$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $taskRoot '.env'
function New-TaskSecret {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
}
$lines = @(
    'API_PORT=8000'
    'BOOTSTRAP_ADMIN_USERNAME=admin'
    ('BOOTSTRAP_ADMIN_PASSWORD=' + (New-TaskSecret))
    'SESSION_COOKIE_SECURE=false'
    ('RUNNER_TOKEN=' + (New-TaskSecret))
    ('CLASS_INVITE_SECRET=' + (New-TaskSecret))
    'MARIADB_DATABASE=judgement'
    'MARIADB_USER=judgement'
    ('MARIADB_PASSWORD=' + (New-TaskSecret))
    ('MARIADB_ROOT_PASSWORD=' + (New-TaskSecret))
)
if (Test-Path -LiteralPath $envPath) {
    $existing = [System.IO.File]::ReadAllLines($envPath)
    $newLines = @($existing)
    foreach ($line in $lines) {
        $key = $line.Split('=', 2)[0]
        if (-not ($existing | Where-Object { $_.StartsWith($key + '=') })) {
            $newLines += $line
        }
    }
    [System.IO.File]::WriteAllLines($envPath, $newLines, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host 'Existing settings kept; missing local account settings added. Secrets were not printed.'
    exit 0
}
[System.IO.File]::WriteAllLines($envPath, $lines, (New-Object System.Text.UTF8Encoding($false)))
Write-Host 'Created .env with random local credentials. Values were not printed.'
