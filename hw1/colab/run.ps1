[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Project,
    [string]$Session,
    [ValidateSet("T4", "L4", "A100", "none")][string]$Gpu,
    [switch]$Sync,
    [string]$Job,
    [switch]$Poll,
    [string]$Fetch,
    [switch]$Check,
    [switch]$StopJob,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "../project_env.ps1")
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$colab = Join-Path $here "colab.ps1"

if (-not (Test-Path $Project)) { throw "project file not found: $Project" }
$projectPath = (Resolve-Path $Project).Path
$projectDir = Split-Path -Parent $projectPath
$config = Get-Content $projectPath -Raw | ConvertFrom-Json

if (-not $Session) { $Session = $config.session }
if (-not $Session) { throw "no session name: give -Session or a 'session' field in $Project" }
if (-not $Gpu) { if ($config.gpu) { $Gpu = $config.gpu } else { $Gpu = "T4" } }

function Assert-Within([string]$Path, [string]$Root) {
    $absolute = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $parent = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    if (-not $absolute.StartsWith($parent, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside its expected directory: $absolute"
    }
}
$temp = Join-Path $env:TEMP "colab_run_$PID"
Assert-Within $temp $env:TEMP
function Invoke-Colab { & $colab @args; if ($LASTEXITCODE -ne 0) { throw "colab $($args -join ' ') failed" } }

$needsRuntime = $Sync -or $Job

$pattern = "\[" + [regex]::Escape($Session) + "\]"
$existing = & $colab sessions 2>&1 | Out-String
$listed = ($LASTEXITCODE -eq 0)
if (-not $listed -or $existing -notmatch $pattern) {
    Start-Sleep -Seconds 5
    $existing = & $colab sessions 2>&1 | Out-String
    $listed = ($LASTEXITCODE -eq 0)
}
if ($needsRuntime) {
    if (-not $listed) {
        throw ("cannot list sessions (the CLI failed, most likely a network timeout). " +
               "Refusing to create '$Session': if it already exists, creating would orphan it.")
    }
    if ($existing -notmatch $pattern) {
        Write-Host "==> creating session '$Session' ($Gpu)" -ForegroundColor Cyan
        if ($Gpu -eq "none") { Invoke-Colab new -s $Session } else { Invoke-Colab new -s $Session --gpu $Gpu }
    } else {
        Write-Host "==> reusing session '$Session'" -ForegroundColor Cyan
    }
} elseif (-not $listed) {
    Write-Host "==> cannot list sessions; proceeding blind on an existing runtime" -ForegroundColor Yellow
} elseif ($existing -notmatch $pattern) {
    Write-Host "==> no session '$Session' is live; nothing to do" -ForegroundColor Yellow
    return
}
New-Item -ItemType Directory -Force -Path $temp | Out-Null

if ($Sync -or $Job) { Invoke-Colab exec -s $Session --timeout 60 -f (Join-Path $here "remote\ensure_idle.py") }

if ($Sync) {
    $bundleDir = Join-Path $projectDir $config.bundle
    if (-not (Test-Path $bundleDir)) { throw "bundle directory not found: $bundleDir" }
    Write-Host "==> bundling $bundleDir" -ForegroundColor Cyan

    $zip = Join-Path $temp "bundle.zip"
    $python = Join-Path $here "../.venv/Scripts/python.exe"
    & $python (Join-Path $here "bundle.py") --project $projectPath --output $zip
    if ($LASTEXITCODE -ne 0) { throw "Bundle creation failed" }
    Write-Host ("==> uploading ({0:N0} bytes)" -f (Get-Item $zip).Length) -ForegroundColor Cyan
    Invoke-Colab upload -s $Session $zip /content/bundle.zip

    $setup = Join-Path $temp "setup.json"
    $payload = @{
        pip          = @($config.pip | Where-Object { $_ })
        import_check = $config.import_check
        pack_exclude = @($config.pack_exclude | Where-Object { $_ })
    }
    [System.IO.File]::WriteAllText($setup, ($payload | ConvertTo-Json -Compress),
        (New-Object System.Text.UTF8Encoding $false))
    Invoke-Colab upload -s $Session $setup /content/setup.json

    Invoke-Colab exec -s $Session --timeout 900 -f (Join-Path $here "remote\setup.py")
}

if ($Job) {
    if (-not (Test-Path $Job)) { throw "job file not found: $Job" }
    Write-Host "==> launching $Job" -ForegroundColor Cyan
    Invoke-Colab upload -s $Session (Resolve-Path $Job).Path /content/job_seq.json
    Invoke-Colab upload -s $Session (Join-Path $here "remote\run_sequence.py") /content/run_sequence.py

    $cmd = Join-Path $temp "job_cmd.txt"
    [System.IO.File]::WriteAllText($cmd, "/content/run_sequence.py`n",
        (New-Object System.Text.UTF8Encoding $false))
    Invoke-Colab upload -s $Session $cmd /content/job_cmd.txt

    Invoke-Colab exec -s $Session --timeout 60 -f (Join-Path $here "remote\clear_pid.py")
    Invoke-Colab exec -s $Session --timeout 120 -f (Join-Path $here "remote\launch_detached.py")
}

if ($Poll) {

    & $colab exec -s $Session --timeout 120 -f (Join-Path $here "remote\poll.py")
}

if ($Check) { & $colab exec -s $Session --timeout 120 -f (Join-Path $here "remote\ps_check.py") }
if ($StopJob) { & $colab exec -s $Session --timeout 120 -f (Join-Path $here "remote\stop_job.py") }

if ($Fetch) {
    Write-Host "==> packing outputs" -ForegroundColor Cyan

    Invoke-Colab exec -s $Session --timeout 900 -f (Join-Path $here "remote\pack_outputs.py")
    New-Item -ItemType Directory -Force -Path $Fetch | Out-Null

    $dest = (Resolve-Path $Fetch).Path
    $stage = Join-Path $dest ".fetchstage"
    Assert-Within $stage $dest
    $tries = 4
    $ok = $false
    for ($attempt = 1; $attempt -le $tries -and -not $ok; $attempt++) {
        if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $stage | Out-Null
        $tar = Join-Path $stage "outputs.tar.gz"
        Invoke-Colab download -s $Session /content/outputs.tar.gz $tar
        Push-Location $stage
        tar -xzf outputs.tar.gz
        $rc = $LASTEXITCODE
        Pop-Location
        if ($rc -ne 0) {
            Write-Host "    attempt $attempt/$tries : download truncated (tar exit $rc)" -ForegroundColor Yellow
            continue
        }
        Remove-Item $tar -Force
        $bad = $null
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        foreach ($z in Get-ChildItem $stage -Recurse -File -Filter *.npz) {
            try {
                $zip = [System.IO.Compression.ZipFile]::OpenRead($z.FullName)
                $zip.Dispose()
            } catch { $bad = $z.Name }
        }
        if ($bad) {
            Write-Host "    attempt $attempt/$tries : $bad arrived incomplete" -ForegroundColor Yellow
            continue
        }
        $ok = $true
    }
    if (-not $ok) {
        if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
        throw "could not fetch a complete archive in $tries attempts; nothing in $dest was touched"
    }
    foreach ($f in Get-ChildItem $stage -Recurse -File) {
        $rel = $f.FullName.Substring($stage.Length + 1)
        $target = Join-Path $dest $rel
        Assert-Within $target $dest
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        Move-Item -Force $f.FullName $target
    }
    Remove-Item $stage -Recurse -Force

    Write-Host "==> results in $Fetch" -ForegroundColor Green
    Get-ChildItem $Fetch -Recurse -File | Select-Object FullName, Length | Format-Table -AutoSize
}

if ($Stop) {
    Write-Host "==> stopping session '$Session'" -ForegroundColor Cyan
    & $colab stop -s $Session
}
Assert-Within $temp $env:TEMP
Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
