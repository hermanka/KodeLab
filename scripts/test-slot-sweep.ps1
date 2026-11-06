param(
    [ValidateRange(1, 50)][int[]]$Slots = @(4, 8, 12, 16),
    [string]$ResumeDirectory
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$sweepName = 'slot-sweep-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 6)
if ($ResumeDirectory) {
    $sweepDirectory = [System.IO.Path]::GetFullPath($ResumeDirectory)
    $sweepName = Split-Path -Leaf $sweepDirectory
    $runs = @((Get-Content -LiteralPath (Join-Path $sweepDirectory 'manifest.json') -Raw | ConvertFrom-Json -AsHashtable).runs)
} else {
    $sweepDirectory = Join-Path $taskRoot ('artifacts/performance/' + $sweepName)
    New-Item -ItemType Directory -Path $sweepDirectory | Out-Null
    $runs = @()
}
Push-Location $taskRoot
try {
    foreach ($capacity in ($Slots | Select-Object -Unique)) {
        if (@($runs | Where-Object { $_.slots -eq $capacity -and $_.status -eq 'completed' }).Count) {
            Write-Output "Keeping completed benchmark: $capacity slots"
            continue
        }
        $directoryName = $sweepName + '-slots-' + $capacity
        $directory = Join-Path $taskRoot ('artifacts/performance/' + $directoryName)
        if (Test-Path -LiteralPath $directory) {
            $directoryName += '-retry-' + [Guid]::NewGuid().ToString('N').Substring(0, 6)
            $directory = Join-Path $taskRoot ('artifacts/performance/' + $directoryName)
        }
        $run = @{slots=$capacity; directory=$directoryName; status='running'}
        $runs += $run
        @{runs=$runs; note='Paired execution-worker concurrency and runner slots; Compose source unchanged'} | ConvertTo-Json -Depth 5 |
            Set-Content -LiteralPath (Join-Path $sweepDirectory 'manifest.json') -Encoding utf8
        Write-Output "Starting benchmark: worker concurrency=$capacity, runner slots=$capacity"
        try {
            & (Join-Path $PSScriptRoot 'test-judging-profile.ps1') -Slots $capacity -ResultDirectory $directory
            $result = Get-Content -LiteralPath (Join-Path $directory 'results.json') -Raw | ConvertFrom-Json
            $analysis = Get-Content -LiteralPath (Join-Path $directory 'stage-analysis.json') -Raw | ConvertFrom-Json
            if ($result.summary.status -ne 'completed' -or $result.summary.anomalies.Count -ne 0 -or
                $analysis.issues.Count -ne 0 -or $analysis.jobs_joined -ne 64) { throw 'Incomplete or anomalous benchmark; inspect raw results' }
            $run.status = 'completed'
        } catch {
            $run.status = 'failed'
            throw
        } finally {
            @{runs=$runs; note='Each child benchmark restores original service images and Compose commands in finally'} | ConvertTo-Json -Depth 5 |
                Set-Content -LiteralPath (Join-Path $sweepDirectory 'manifest.json') -Encoding utf8
        }
    }
    $profilePath = Join-Path $PSScriptRoot 'profiling'
    $historyPath = Join-Path $taskRoot 'artifacts/performance'
    docker compose run --rm --no-deps -T -v "${profilePath}:/profiling:ro" -v "${historyPath}:/history" api python /profiling/slot_report.py "/history/$sweepName"
    if ($LASTEXITCODE -ne 0) { throw 'Slot comparison report failed' }
    Write-Output ('Comparison report: '+(Join-Path $sweepDirectory 'LAPORAN_PERBANDINGAN_SLOT.md'))
} finally { Pop-Location }
