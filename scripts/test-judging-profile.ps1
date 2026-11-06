param(
    [switch]$SelfCheck,
    [ValidateRange(1, 50)][Nullable[int]]$Slots = $null,
    [string]$ResultDirectory
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$profilePath = Join-Path $PSScriptRoot 'profiling'
$loadPath = Join-Path $PSScriptRoot 'load-concurrent.py'
$runName = 'judging-profile-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 6)
$outputDirectory = if ($ResultDirectory) { [System.IO.Path]::GetFullPath($ResultDirectory) } else { Join-Path $taskRoot ('artifacts/performance/' + $runName) }
$sandboxTag = 'judgementsystem-sandbox:profile-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$overridePath = $null
$activated = $false
$restorePath = $null
$monitorId = $null
Push-Location $taskRoot
try {
    if ($SelfCheck) {
        docker compose run --rm --no-deps -T -v "${profilePath}:/profiling:ro" api python /profiling/check.py
        if ($LASTEXITCODE -ne 0) { throw 'Profiling self-check failed' }
        return
    }
    docker compose run --rm --no-deps -T -v "${profilePath}:/profiling:ro" api python /profiling/runtime_config.py --preflight
    if ($LASTEXITCODE -ne 0) { throw 'Active jobs must finish before profiling restarts services' }
    $settings = @{}
    foreach ($line in [System.IO.File]::ReadAllLines((Join-Path $taskRoot '.env'))) {
        if ($line -match '^(BOOTSTRAP_ADMIN_USERNAME|BOOTSTRAP_ADMIN_PASSWORD)=(.*)$') { $settings[$Matches[1]] = $Matches[2] }
    }
    if (-not $settings['BOOTSTRAP_ADMIN_PASSWORD']) { throw 'Missing bootstrap credentials' }
    New-Item -ItemType Directory -Path $outputDirectory | Out-Null
    $traceDirectory = Join-Path $outputDirectory 'traces'
    New-Item -ItemType Directory -Path $traceDirectory | Out-Null
    $buildDirectory = Join-Path $outputDirectory 'sandbox-profile'
    New-Item -ItemType Directory -Path $buildDirectory | Out-Null
    $composeConfig = docker compose config --format json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read Compose configuration' }
    if ($null -ne $Slots) {
        $composeConfig.services.worker.command = @($composeConfig.services.worker.command | ForEach-Object { $_ -replace '^--concurrency=\d+$', "--concurrency=$Slots" })
        $composeConfig.services.runner.environment.RUNNER_SLOTS = [string]$Slots
    }
    Copy-Item -LiteralPath (Join-Path $taskRoot 'sandbox/entrypoint.py') -Destination (Join-Path $buildDirectory 'entrypoint.py')
    Copy-Item -LiteralPath (Join-Path $profilePath 'sandbox_entrypoint.py') -Destination (Join-Path $buildDirectory 'profiled_entrypoint.py')
    @"
FROM $($composeConfig.services.runner.environment.SANDBOX_IMAGE)
COPY entrypoint.py /opt/judge/original_entrypoint.py
COPY profiled_entrypoint.py /opt/judge/entrypoint.py
"@ | Set-Content -LiteralPath (Join-Path $buildDirectory 'Dockerfile') -Encoding utf8
    $dockerInfo = docker info --format '{{json .}}' | ConvertFrom-Json
    $originalImages = @{}
    $restoreServices = @{}
    foreach ($component in @('api','worker','validator','scheduler','runner')) {
        $originalImages[$component] = (docker compose images -q $component).Trim()
        if (-not $originalImages[$component]) { throw ('Missing running image for '+$component) }
        $restoreServices[$component] = @{image=$originalImages[$component]}
    }
    $restorePath = Join-Path $outputDirectory 'compose-restore.json'
    @{services=$restoreServices} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $restorePath -Encoding utf8
    @{started_local=(Get-Date -Format o); docker_cpus=$dockerInfo.NCPU; docker_memory_bytes=$dockerInfo.MemTotal;
      docker_version=$dockerInfo.ServerVersion; sandbox_profile_image=$sandboxTag;
      original_images=$originalImages; config=@{worker_command=$composeConfig.services.worker.command;
        validator_command=$composeConfig.services.validator.command;
        runner_slots=$composeConfig.services.runner.environment.RUNNER_SLOTS;
        config_note='Live configuration also verified in runtime-config.json; quotas unchanged; cases sequential'}} |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outputDirectory 'environment.json') -Encoding utf8
    Write-Output ('Results directory: '+$outputDirectory)
    $baseArgs = @('compose','run','--rm','--no-deps','-T','-v',"${profilePath}:/profiling:ro",'-v',"${loadPath}:/loadtest.py:ro",'-v',"${outputDirectory}:/results",'api','python','/profiling/detailed_load.py')
    & docker @baseArgs --calibrate unprofiled | Tee-Object -FilePath (Join-Path $outputDirectory 'calibration-unprofiled.log')
    if ($LASTEXITCODE -ne 0) { throw 'Unprofiled control failed' }
    docker build -t $sandboxTag $buildDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Profiling sandbox build failed' }
    $services = @{}
    foreach ($component in @('api','worker','validator','scheduler','runner')) {
        $environment = @{JUDGE_PROFILE_DIR='/profiles'; JUDGE_PROFILE_COMPONENT=$component}
        if ($component -eq 'runner') {
            $environment['SANDBOX_IMAGE']=$sandboxTag
            $environment['RUNNER_SLOTS']=$composeConfig.services.runner.environment.RUNNER_SLOTS
        }
        $profileCommand = @('python','/profiling/launch.py',$component)
        if ($component -in @('worker','validator','scheduler')) {
            $profileCommand += @($composeConfig.services.$component.command)[3..($composeConfig.services.$component.command.Count-1)]
        }
        $services[$component] = @{image=$originalImages[$component];command=$profileCommand;environment=$environment;
            volumes=@("${profilePath}:/profiling:ro","${traceDirectory}:/profiles")}
    }
    $overridePath = Join-Path $outputDirectory 'compose-profile.json'
    @{services=$services} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $overridePath -Encoding utf8
    $activated = $true
    docker compose -f compose.yaml -f $overridePath up -d --no-deps --wait --wait-timeout 90 api worker validator scheduler runner
    if ($LASTEXITCODE -ne 0) { throw 'Profiling services failed readiness' }
    $workerConcurrency = @($composeConfig.services.worker.command | Where-Object { $_ -like '--concurrency=*' })[0].Split('=')[1]
    docker compose run --rm --no-deps -T -v "${profilePath}:/profiling:ro" -v "${outputDirectory}:/results" api python /profiling/runtime_config.py $workerConcurrency
    if ($LASTEXITCODE -ne 0) { throw 'Actual Celery capacity does not match Compose' }
    $runnerConfig = docker compose -f compose.yaml -f $overridePath exec -T runner python /profiling/runtime_config.py --runner | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $runnerConfig.runner_slots -ne [int]$composeConfig.services.runner.environment.RUNNER_SLOTS) { throw 'Actual runner capacity does not match Compose' }
    $runnerConfig | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputDirectory 'runner-runtime.json') -Encoding utf8
    $monitorId = (docker compose run --rm -d --no-deps -v "${profilePath}:/profiling:ro" -v "${outputDirectory}:/results" api python /profiling/resources.py).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Resource monitor failed to start' }
    & docker @baseArgs --calibrate profiled | Tee-Object -FilePath (Join-Path $outputDirectory 'calibration-profiled.log')
    if ($LASTEXITCODE -ne 0) { throw 'Profiled control failed' }
    $payload = @{username=$settings['BOOTSTRAP_ADMIN_USERNAME'];password=$settings['BOOTSTRAP_ADMIN_PASSWORD']} | ConvertTo-Json -Compress
    $payload | & docker @baseArgs | Tee-Object -FilePath (Join-Path $outputDirectory 'run.log')
    if ($LASTEXITCODE -ne 0) { throw 'Detailed benchmark process failed' }
    $result=Get-Content -LiteralPath (Join-Path $outputDirectory 'results.json') -Raw | ConvertFrom-Json
    if ($result.summary.status -ne 'completed') { throw 'Detailed benchmark incomplete; inspect results.json' }
    docker compose -f compose.yaml -f $overridePath logs --no-color api worker validator scheduler runner 2>&1 | Set-Content -LiteralPath (Join-Path $outputDirectory 'service-profile.log') -Encoding utf8
    docker compose run --rm --no-deps -T -v "${profilePath}:/profiling:ro" -v "${outputDirectory}:/results" api python /profiling/analyze.py /results
    if ($LASTEXITCODE -ne 0) { throw 'Detailed timing analysis failed; inspect traces' }
    $historyPath = Join-Path $taskRoot 'artifacts/performance'
    docker compose run --rm --no-deps -T -v "${profilePath}:/profiling:ro" -v "${outputDirectory}:/results" -v "${historyPath}:/history:ro" api python /profiling/report.py /results /history/judging-profile-20261104-112759-70e705
    if ($LASTEXITCODE -ne 0) { throw 'Detailed report generation failed' }
} finally {
    if ($monitorId) {
        try {
            New-Item -ItemType File -Path (Join-Path $outputDirectory 'monitor.stop') -Force | Out-Null
            docker stop --timeout 3 $monitorId | Out-Null
        } catch { Write-Warning 'Resource monitor cleanup failed; service restoration will continue.' }
    }
    if ($activated) {
        try {
            docker compose -f compose.yaml -f $overridePath logs --no-color api worker validator scheduler runner 2>&1 | Set-Content -LiteralPath (Join-Path $outputDirectory 'service-profile.log') -Encoding utf8
        } catch { Write-Warning 'Service log capture failed; service restoration will continue.' }
        docker compose -f compose.yaml -f $restorePath up -d --no-deps --wait --wait-timeout 90 api worker validator scheduler runner
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Automatic restore failed; inspect services before normal use.' }
        else { Write-Output 'Original service commands, sandbox image and profiling-disabled configuration restored.' }
    }
    Pop-Location
}
