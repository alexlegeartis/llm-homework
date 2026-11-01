param([int]$Port = 8089, [int]$Threads = 8)

. (Join-Path $PSScriptRoot 'project_env.ps1')
$ProgressPreference = 'SilentlyContinue'
$runtime = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$parallel = $runtime.local_server.parallel
$context = $runtime.local_server.context_size * $parallel
$cache = Join-Path $PSScriptRoot '.cache/runtime'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
$model = Join-Path $cache $runtime.quantization.file
$archive = Join-Path $cache 'llama.zip'
$bin = Join-Path $cache 'llama'

function Get-VerifiedFile($Url, $Path, $Sha256) {
    if (-not (Test-Path -LiteralPath $Path)) {
        Invoke-WebRequest -Uri $Url -OutFile "$Path.part" -UseBasicParsing
        Move-Item -LiteralPath "$Path.part" -Destination $Path
    }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Sha256) {
        throw "SHA-256 mismatch: $Path"
    }
}

$q = $runtime.quantization
Get-VerifiedFile "https://huggingface.co/$($q.repository)/resolve/$($q.revision)/$($q.file)?download=true" $model $q.sha256
Get-VerifiedFile $runtime.local_server.windows_url $archive $runtime.local_server.windows_sha256
if (-not (Test-Path -LiteralPath (Join-Path $bin 'llama-server.exe'))) {
    Expand-Archive -LiteralPath $archive -DestinationPath $bin
}
& (Join-Path $bin 'llama-server.exe') -m $model --host 127.0.0.1 --port $Port --ctx-size $context --parallel $parallel --threads $Threads --threads-batch $Threads --batch-size 256 --ubatch-size 128 --jinja --alias $runtime.model --cache-ram 0 --no-repack
