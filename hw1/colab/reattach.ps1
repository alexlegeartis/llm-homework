param([string]$Name = 'llm-homework', [string]$Endpoint)

. (Join-Path $PSScriptRoot '../project_env.ps1')
$env:PYTHONPATH = Join-Path $PSScriptRoot 'colab_shim'
$env:PYTHONUTF8 = '1'
$uv = Join-Path $env:USERPROFILE '.local/bin/uv.exe'
$toolRoot = & $uv tool dir
if ($LASTEXITCODE -ne 0) { throw 'Cannot locate the installed Colab CLI' }
$python = Join-Path $toolRoot 'google-colab-cli/Scripts/python.exe'
$arguments = @((Join-Path $PSScriptRoot 'reattach.py'), '--name', $Name)
if ($Endpoint) { $arguments += @('--endpoint', $Endpoint) }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Could not reattach the Colab session' }