$ErrorActionPreference = 'Stop'
$projectWork = Join-Path $PSScriptRoot '.cache/work'
$projectDirectories = @{
    TEMP = 'tmp'; TMP = 'tmp'; UV_CACHE_DIR = 'uv-cache'
    UV_PYTHON_INSTALL_DIR = 'python'; PIP_CACHE_DIR = 'pip-cache'; HF_HOME = 'huggingface'
}
foreach ($projectVariable in $projectDirectories.Keys) {
    $directory = Join-Path $projectWork $projectDirectories[$projectVariable]
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    [Environment]::SetEnvironmentVariable($projectVariable, $directory, 'Process')
}
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
