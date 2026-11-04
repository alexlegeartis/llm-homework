<#
.SYNOPSIS
    Windows launcher for the Google Colab CLI.

.DESCRIPTION
    google-colab-cli is documented as Linux/macOS only. The sole obstacle on Windows is
    an unconditional `import termios` / `import tty` in colab_cli/console.py, which is
    imported at module load but used only by the interactive `console` / `repl` TTY.
    ./colab_shim/ provides stubs for those two modules; this script puts them on
    PYTHONPATH and forwards every argument to the real CLI.

    Installed with:  uv tool install google-colab-cli   (uv brings its own Python 3.12+;
    the system Python 3.9 is too old for the package's requires-python.)

.EXAMPLE
    .\colab.ps1 new --gpu T4
    .\colab.ps1 exec -f smoke_test.py
    .\colab.ps1 run --gpu T4 smoke_test.py
    .\colab.ps1 stop
#>
# Not named $Args: that is a PowerShell automatic variable, and shadowing it in a
# param block is a latent source of very confusing argument bugs.
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CliArgs)

. (Join-Path $PSScriptRoot "../project_env.ps1")
$ErrorActionPreference = 'Continue'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$env:PYTHONPATH = Join-Path $here 'colab_shim'
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

$colab = Join-Path $env:USERPROFILE '.local\bin\colab.exe'
if (-not (Test-Path $colab)) {
    Write-Error "colab CLI not found at $colab. Install it with: uv tool install google-colab-cli"
    exit 1
}

& $colab @CliArgs
exit $LASTEXITCODE
