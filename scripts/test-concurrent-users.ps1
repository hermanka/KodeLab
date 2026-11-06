param([switch]$SelfCheck)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $PSScriptRoot 'load-concurrent.py'
$runName = 'concurrent-30-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 6)
$outputDirectory = Join-Path $taskRoot ('artifacts/performance/' + $runName)
$monitorJob = $null
Push-Location $taskRoot
try {
    if ($SelfCheck) {
        docker compose run --rm --no-deps -T -v "${scriptPath}:/loadtest.py:ro" api python /loadtest.py --self-check
        if ($LASTEXITCODE -ne 0) { throw 'Load-test self-check failed' }
        return
    }
    $settings = @{}
    foreach ($line in [System.IO.File]::ReadAllLines((Join-Path $taskRoot '.env'))) {
        if ($line -match '^(BOOTSTRAP_ADMIN_USERNAME|BOOTSTRAP_ADMIN_PASSWORD)=(.*)$') {
            $settings[$Matches[1]] = $Matches[2]
        }
    }
    if (-not $settings['BOOTSTRAP_ADMIN_PASSWORD']) { throw 'Bootstrap credentials are required for temporary test accounts.' }
    New-Item -ItemType Directory -Path $outputDirectory | Out-Null
    $info = docker info --format '{{json .}}' | ConvertFrom-Json
    $services = docker compose ps --format json | ForEach-Object { $_ | ConvertFrom-Json } |
        Select-Object Service, Image, State, Health
    @{
        started_local = (Get-Date -Format o)
        docker_cpus = $info.NCPU
        docker_memory_bytes = $info.MemTotal
        docker_version = $info.ServerVersion
        operating_system = $info.OperatingSystem
        architecture = $info.Architecture
        services = @($services)
        load_generator = 'Separate one-off container, same Docker host, HTTP to api:8000'
        configuration = 'Unmodified: worker concurrency=2, validator=1, runner slots=3; class pending cap=20'
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $outputDirectory 'environment.json') -Encoding utf8
    $monitorJob = Start-Job -ArgumentList $outputDirectory -ScriptBlock {
        param($directory)
        $deadline = (Get-Date).AddMinutes(30)
        while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath (Join-Path $directory 'monitor.stop'))) {
            $timestamp = Get-Date -Format o
            docker stats --no-stream --format '{{json .}}' 2>$null | ForEach-Object {
                $stats = $_ | ConvertFrom-Json
                if ($stats.Name -like 'judgementsystem*') {
                    @{at=$timestamp; name=$stats.Name; cpu=$stats.CPUPerc; memory=$stats.MemUsage; pids=$stats.PIDs} |
                        ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $directory 'resources.jsonl') -Encoding utf8
                }
            }
            Start-Sleep -Seconds 2
        }
    }
    $payload = @{username=$settings['BOOTSTRAP_ADMIN_USERNAME']; password=$settings['BOOTSTRAP_ADMIN_PASSWORD']} | ConvertTo-Json -Compress
    Write-Output ('Results directory: ' + $outputDirectory)
    $loadArgs = @('compose', 'run', '--rm', '--no-deps', '-T', '-e', 'LOAD_BASE_URL=http://api:8000',
        '-v', "${scriptPath}:/loadtest.py:ro", '-v', "${outputDirectory}:/results", 'api', 'python', '/loadtest.py')
    $payload | & docker @loadArgs | Tee-Object -FilePath (Join-Path $outputDirectory 'run.log')
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) { throw ('Load generator failed with exit code ' + $exitCode) }
    $resultFile = Join-Path $outputDirectory 'results.json'
    if (-not (Test-Path -LiteralPath $resultFile)) { throw 'No result file was generated' }
    $results = Get-Content -LiteralPath $resultFile -Raw | ConvertFrom-Json
    if ($results.summary.status -ne 'completed') { throw ('Test incomplete; see ' + $resultFile) }
} finally {
    if ($monitorJob) {
        Set-Content -LiteralPath (Join-Path $outputDirectory 'monitor.stop') -Value 'stop' -Encoding utf8
        Stop-Job $monitorJob
        Receive-Job $monitorJob | Out-Null
        Remove-Job $monitorJob
    }
    Pop-Location
}
