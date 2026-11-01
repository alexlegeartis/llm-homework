<#
.SYNOPSIS
    Switch the Colab CLI between several Google accounts.

.DESCRIPTION
    The CLI keeps one set of credentials at ~/.config/colab-cli/token.json and one map of
    live runtimes at sessions.json.  Both belong to whichever account authenticated, so
    they have to travel together: activating account B's token while account A's
    sessions.json is in place leaves the CLI trying to address A's runtimes with B's
    credentials, which is how a live VM ends up unreachable (see reattach.py).

    This stores a named profile per account under ~/.config/colab-cli/profiles/<name>/
    and swaps both files as a unit.  Nothing is ever deleted: -Use snapshots whatever is
    currently live before overwriting it.

    Note that a session belongs to the account that created it.  Sessions on the account
    you switch away from keep running and keep consuming its quota; stop them first
    (.\colab_flows.ps1 -Stop) unless you mean to leave them going.

.EXAMPLE
    .\colab_account.ps1 -List
    .\colab_account.ps1 -Save personal      # name the credentials that are live now
    .\colab_account.ps1 -New work           # authenticate another account, then save it
    .\colab_account.ps1 -Use work
#>
[CmdletBinding(DefaultParameterSetName = "List")]
param(
    [Parameter(ParameterSetName = "List")][switch]$List,
    [Parameter(ParameterSetName = "Save")][string]$Save,
    [Parameter(ParameterSetName = "Use")][string]$Use,
    [Parameter(ParameterSetName = "New")][string]$New
)

. (Join-Path $PSScriptRoot "../project_env.ps1")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
# uv installs to ~\.local\bin, which is not always on PATH in a fresh shell; colab.ps1
# does the same thing before invoking the CLI
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
$root = Join-Path $env:USERPROFILE ".config\colab-cli"
$profiles = Join-Path $root "profiles"
$activeFile = Join-Path $profiles ".active"
$files = @("token.json", "sessions.json")

New-Item -ItemType Directory -Force -Path $profiles | Out-Null

function Get-Active {
    if (Test-Path $activeFile) { (Get-Content $activeFile -Raw).Trim() } else { "" }
}

function Save-Profile([string]$name) {
    $dst = Join-Path $profiles $name
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    foreach ($f in $files) {
        $src = Join-Path $root $f
        if (Test-Path $src) { Copy-Item $src (Join-Path $dst $f) -Force }
    }
    Set-Content $activeFile $name -NoNewline
    Write-Host "==> saved current credentials as profile '$name'" -ForegroundColor Green
}

# --- list -------------------------------------------------------------------
if ($PSCmdlet.ParameterSetName -eq "List" ) {
    $active = Get-Active
    $dirs = Get-ChildItem $profiles -Directory -ErrorAction SilentlyContinue
    if (-not $dirs) {
        Write-Host "no profiles yet. Save the credentials you are using now with:"
        Write-Host "    .\colab_account.ps1 -Save <name>"
    }
    foreach ($d in $dirs) {
        $mark = if ($d.Name -eq $active) { "*" } else { " " }
        $tok = Join-Path $d.FullName "token.json"
        $acct = ""
        if (Test-Path $tok) {
            try { $acct = (Get-Content $tok -Raw | ConvertFrom-Json).account } catch {}
        }
        Write-Host ("{0} {1,-16} {2}" -f $mark, $d.Name, $acct)
    }
    if (-not (Test-Path (Join-Path $root "token.json"))) {
        Write-Host "`n(no live token.json right now)" -ForegroundColor Yellow
    }
    return
}

# --- save the live credentials under a name ---------------------------------
if ($Save) { Save-Profile $Save; return }

# --- authenticate a new account ---------------------------------------------
if ($New) {
    if (Test-Path (Join-Path $profiles $New)) { throw "profile '$New' already exists" }
    $active = Get-Active
    if ($active) {
        Save-Profile $active   # do not lose the credentials that are live
    } elseif (Test-Path (Join-Path $root "token.json")) {
        Save-Profile "_unnamed"
    }
    Write-Host "`n==> authenticating a new account for profile '$New'" -ForegroundColor Cyan
    Write-Host "    Sign in with the account you want to use, approve, copy the code.`n"
    & uv run --python 3.12 --with google-auth-oauthlib python (Join-Path $here "colab_auth.py") --start
    $code = Read-Host "`nPaste the authorization code"
    & uv run --python 3.12 --with google-auth-oauthlib python (Join-Path $here "colab_auth.py") --finish $code
    if ($LASTEXITCODE -ne 0) { throw "authentication failed; the previous profile is still saved" }
    # a fresh account owns no runtimes yet
    Set-Content (Join-Path $root "sessions.json") "{}" -NoNewline
    Save-Profile $New
    Write-Host "`n==> now using '$New'. Check with: .\colab.ps1 sessions" -ForegroundColor Green
    return
}

# --- activate a saved profile ------------------------------------------------
if ($Use) {
    $src = Join-Path $profiles $Use
    if (-not (Test-Path $src)) { throw "no profile '$Use'. Run -List to see what exists." }
    $active = Get-Active
    if ($active -and $active -ne $Use) {
        Save-Profile $active            # snapshot before overwriting
    } elseif (-not $active -and (Test-Path (Join-Path $root "token.json"))) {
        Save-Profile "_unnamed"
    }
    foreach ($f in $files) {
        $from = Join-Path $src $f
        if (Test-Path $from) { Copy-Item $from (Join-Path $root $f) -Force }
        elseif ($f -eq "sessions.json") { Set-Content (Join-Path $root $f) "{}" -NoNewline }
    }
    Set-Content $activeFile $Use -NoNewline
    Write-Host "==> now using profile '$Use'" -ForegroundColor Green
    & (Join-Path $here "colab.ps1") sessions
}
