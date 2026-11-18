param([switch]$EvaluationFaults)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $python -c 'from backend.app.deployment import require_native_primary; require_native_primary()'
if ($LASTEXITCODE -ne 0) { throw 'Native startup blocked by the primary-database handoff guard.' }
$stateDir = Join-Path $projectRoot '.local\native-demo'
$stateFile = Join-Path $stateDir 'status.json'
if (Test-Path -LiteralPath $stateFile) {
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    if ($state.owner -ne 'qinggui-assessment-native-demo') { throw 'Unknown native-demo state; preserved.' }
    $running = Get-CimInstance Win32_Process -Filter "ProcessId = $($state.supervisor_pid)" -ErrorAction SilentlyContinue
    if ($running -and $running.CommandLine -like '*scripts/native_demo.py*') {
        if ([bool]$state.evaluation_faults -ne [bool]$EvaluationFaults) { throw 'Stop this preview before changing evaluation-fault mode.' }
        Write-Output "Native preview is $($state.stage): $($state.url)"
        return
    }
}
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$nativeArgs = @('-u','scripts/native_demo.py')
if ($EvaluationFaults) { $nativeArgs += '--evaluation-faults' }
$process = Start-Process -FilePath $python -ArgumentList $nativeArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $stateDir 'supervisor.log') -RedirectStandardError (Join-Path $stateDir 'supervisor-error.log')
Write-Output "Starting native preview at http://127.0.0.1:15174 (launcher PID $($process.Id))."
Write-Output 'Startup state and logs: .local/native-demo'
