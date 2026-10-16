<#
.SYNOPSIS
  Run llama-server natively on Windows (Intel Arc via Vulkan or SYCL) on 127.0.0.1:8080.

.DESCRIPTION
  Native Windows avoids the WSL2 GPU translation layer, which is often slow on Intel
  graphics. LiteLLM inside WSL reaches this server at http://127.0.0.1:8080/v1 when WSL
  uses mirrored networking (see .wslconfig.example).

  Downloads the pinned llama.cpp release on first run into %USERPROFILE%\tools\llama.cpp,
  and the model on first start into llama.cpp's cache.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\llama-server.ps1
  powershell -ExecutionPolicy Bypass -File scripts\windows\llama-server.ps1 -Preset small
  powershell -ExecutionPolicy Bypass -File scripts\windows\llama-server.ps1 -Backend sycl
  powershell -ExecutionPolicy Bypass -File scripts\windows\llama-server.ps1 -ListDevices
#>
param(
  [ValidateSet('vulkan', 'sycl', 'cpu')]
  [string]$Backend = 'vulkan',

  # qwen36 = Qwen3.6-35B-A3B Q4_K_M (about 20 GB); small = Qwen2.5-Coder-7B Q4_K_M (about 5 GB)
  [ValidateSet('qwen36', 'small')]
  [string]$Preset = 'qwen36',

  # Context window in tokens. Agent tools need 32k or more.
  [int]$Ctx = 32768,

  # Keep the experts of this many layers on the CPU if the model does not fit in GPU memory.
  [int]$NCpuMoe = 0,

  # Pinned llama.cpp release. Bump deliberately.
  [string]$Tag = 'b11600',

  # A local .gguf file instead of a preset.
  [string]$ModelFile = '',

  [switch]$ListDevices
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # makes Invoke-WebRequest much faster

$installDir = Join-Path $env:USERPROFILE "tools\llama.cpp\$Tag-$Backend"
$server = Get-ChildItem -Path $installDir -Filter 'llama-server.exe' -Recurse -ErrorAction SilentlyContinue |
  Select-Object -First 1

if (-not $server) {
  $asset = "llama-$Tag-bin-win-$Backend-x64.zip"
  $url = "https://github.com/ggml-org/llama.cpp/releases/download/$Tag/$asset"
  $zip = Join-Path $env:TEMP $asset
  Write-Host "Downloading $url"
  Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
  New-Item -ItemType Directory -Force -Path $installDir | Out-Null
  Expand-Archive -Path $zip -DestinationPath $installDir -Force
  Remove-Item $zip
  $server = Get-ChildItem -Path $installDir -Filter 'llama-server.exe' -Recurse | Select-Object -First 1
  if (-not $server) { throw "llama-server.exe not found in $asset" }
}

if ($ListDevices) {
  & $server.FullName --list-devices
  exit $LASTEXITCODE
}

if ($ModelFile) {
  $modelArgs = @('-m', $ModelFile)
} else {
  $hf = @{
    'qwen36' = 'ggml-org/Qwen3.6-35B-A3B-GGUF:Q4_K_M'
    'small'  = 'Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M'
  }[$Preset]
  $modelArgs = @('-hf', $hf)
}

# 127.0.0.1 only: never expose the model server to your network.
$serverArgs = $modelArgs + @('--host', '127.0.0.1', '--port', '8080', '-ngl', '99', '-c', "$Ctx", '--jinja')
if ($NCpuMoe -gt 0) { $serverArgs += @('--n-cpu-moe', "$NCpuMoe") }

Write-Host "Starting: $($server.FullName) $($serverArgs -join ' ')"
& $server.FullName @serverArgs
exit $LASTEXITCODE
