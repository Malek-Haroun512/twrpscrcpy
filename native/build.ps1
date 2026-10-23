# Cross compile the freestanding ARM helper from Windows with LLVM.
# Install LLVM first: winget install LLVM.LLVM
# Then run from a PowerShell prompt: .\build.ps1
param(
    [string]$Clang = "clang",
    [string]$LlvmStrip = "llvm-strip"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$out = Join-Path (Split-Path -Parent $PSScriptRoot) "twrpscrcpy\bin"
New-Item -ItemType Directory -Force -Path $out | Out-Null

$cflags = @(
    "-nostdlib", "-static", "-O2", "-fno-stack-protector",
    "-fno-pic", "-fno-builtin", "-ffreestanding"
)
$ldflags = @("-fuse-ld=lld", "-Wl,-e,_start", "-Wl,--build-id=none")

& $Clang "--target=aarch64-linux-gnu" @cflags @ldflags -o (Join-Path $out "fbstream-arm64") "fbstream.c"
if ($LASTEXITCODE -ne 0) { throw "arm64 build failed" }

& $Clang "--target=armv7a-linux-gnueabi" "-march=armv7-a" @cflags @ldflags -o (Join-Path $out "fbstream-arm") "fbstream.c"
if ($LASTEXITCODE -ne 0) { throw "arm32 build failed" }

if (Get-Command $LlvmStrip -ErrorAction SilentlyContinue) {
    & $LlvmStrip -s (Join-Path $out "fbstream-arm64")
    & $LlvmStrip -s (Join-Path $out "fbstream-arm")
}

Get-ChildItem $out | Format-Table Name, Length
