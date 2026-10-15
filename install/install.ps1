<#
.SYNOPSIS
Installs Nemerle for the current user on Windows: the compiler (ncc), scripting (nscript), Nitra and the language
server (nemerle-lsp), plus optionally the VS Code / VSCodium extension. Run it from a clone of the repository.

.EXAMPLE
install\install.cmd
install\install.cmd -Editor none
install\install.cmd -Uninstall

Needs only the .NET 10 runtime (https://dotnet.microsoft.com/download/dotnet/10.0). The editor extension also needs
npm. -Build compiles everything from source first and needs Python 3 and the strong-name tool sn as well.
#>
param(
  [string]$Prefix = $(if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'Nemerle' } else { Join-Path $HOME '.local/share/nemerle' }),
  [switch]$Build,
  [switch]$NoLsp,
  [ValidateSet('auto', 'code', 'codium', 'none')][string]$Editor = 'auto',
  [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 has no $IsWindows; PowerShell 7 on Linux/macOS gets shell launchers instead of .cmd ones.
$onWindows = ($null -eq $IsWindows) -or $IsWindows

$repo = Split-Path -Parent $PSScriptRoot
$bin = Join-Path $Prefix 'bin'
$extension = 'nemerle.nemerle-nitra-0.1.0'
$extensionRoots = @{ code = (Join-Path $HOME '.vscode\extensions'); codium = (Join-Path $HOME '.vscode-oss\extensions') }

function Set-UserPath([string]$dir, [bool]$add) {
  $current = [Environment]::GetEnvironmentVariable('Path', 'User')
  $parts = @($current -split ';' | Where-Object { $_ -and $_ -ne $dir })
  if ($add) { $parts += $dir }
  [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
}

if ($Uninstall) {
  Remove-Item -Recurse -Force $Prefix -ErrorAction SilentlyContinue
  foreach ($root in $extensionRoots.Values) { Remove-Item -Recurse -Force (Join-Path $root $extension) -ErrorAction SilentlyContinue }
  if ($onWindows) { Set-UserPath $bin $false }
  Write-Host "Nemerle removed from $Prefix."
  exit 0
}

# --- the .NET 10 runtime ---
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
  throw 'dotnet not found. Install the .NET 10 runtime: https://dotnet.microsoft.com/download/dotnet/10.0'
}
if (-not (& dotnet --list-runtimes | Where-Object { $_ -match '^Microsoft\.NETCore\.App 10\.' })) {
  throw 'The .NET 10 runtime is missing. Install it: https://dotnet.microsoft.com/download/dotnet/10.0'
}

# --- which toolchain ---
$source = Join-Path $repo 'boot\coreclr'
if ($Build) {
  Write-Host 'Building from source (build\bootstrap.py --quick); this takes a few minutes...'
  & python (Join-Path $repo 'build\bootstrap.py') --quick
  if ($LASTEXITCODE -ne 0) { throw "The build failed; see $repo\out\bootstrap\logs" }
  $source = Join-Path $repo 'out\bootstrap\toolchain'
}
if (-not (Test-Path (Join-Path $source 'ncc.exe'))) { throw "No toolchain in $source" }

Write-Host "Installing the toolchain from $source to $Prefix"
$tc = Join-Path $Prefix 'toolchain'
New-Item -ItemType Directory -Force -Path $Prefix, $bin | Out-Null
Remove-Item -Recurse -Force $tc -ErrorAction SilentlyContinue
Copy-Item -Recurse $source $tc

# --- the language server, compiled from source with the installed compiler ---
if (-not $NoLsp) {
  Write-Host 'Building the language server'
  $serverSources = @(Get-ChildItem (Join-Path $repo 'tools\language-server') -Filter '*.n' | ForEach-Object { $_.FullName })
  $references = @('Nemerle.Compiler', 'Integrated.Nitra.Runtime', 'Integrated.Nitra.Grammar', 'Integrated.Nitra.Compiler', 'Integrated.DotNetLang') |
    ForEach-Object { "-r:$(Join-Path $tc "$_.dll")" }
  $log = Join-Path $Prefix 'lsp-build.log'
  & dotnet (Join-Path $tc 'ncc.exe') "-source-root:$(Join-Path $repo 'tools\language-server')" @serverSources -target:exe `
    "-out:$(Join-Path $tc 'nemerle-lsp.exe')" "-target-references:$(Join-Path $tc 'references')" -no-color @references *> $log
  if ($LASTEXITCODE -ne 0) { throw "Building the language server failed; see $log" }
  Copy-Item (Join-Path $tc 'ncc.runtimeconfig.json') (Join-Path $tc 'nemerle-lsp.runtimeconfig.json')
}

# --- launchers (bin is added to the user's PATH) ---
function New-Launcher([string]$name, [string]$program, [bool]$references) {
  if ($onWindows) {
    $extra = if ($references) { '-target-references:"%~dp0..\toolchain\references" ' } else { '' }
    Set-Content -Encoding ASCII -Path (Join-Path $bin "$name.cmd") -Value "@dotnet `"%~dp0..\toolchain\$program`" $extra%*"
  } else {
    $extra = if ($references) { "-target-references:`"$tc/references`" " } else { '' }
    $path = Join-Path $bin $name
    Set-Content -Encoding ASCII -Path $path -Value "#!/bin/sh`nexec dotnet `"$tc/$program`" $extra`"`$@`""
    & chmod 755 $path
  }
}
New-Launcher 'ncc' 'ncc.exe' $true
New-Launcher 'nscript' 'nscript.exe' $false
if (-not $NoLsp) { New-Launcher 'nemerle-lsp' 'nemerle-lsp.exe' $false }
if ($onWindows) { Set-UserPath $bin $true }
$env:Path = "$bin$([IO.Path]::PathSeparator)$env:Path"

# --- the editor extension ---
function Install-Extension([string]$editorName) {
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Write-Host "Skipping the $editorName extension: npm is needed to install its one dependency."; return }
  $dir = Join-Path $extensionRoots[$editorName] $extension
  Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  foreach ($file in 'package.json', 'extension.js', 'language-configuration.json') {
    Copy-Item (Join-Path $repo "tools\language-server\vscode\$file") $dir
  }
  Push-Location $dir
  try { & npm install --omit=dev --no-audit --no-fund --silent *> $null; $ok = ($LASTEXITCODE -eq 0) } finally { Pop-Location }
  if ($ok) { Write-Host "Installed the $editorName extension in $dir" }
  else { Remove-Item -Recurse -Force $dir; Write-Host "Skipping the $editorName extension: npm install failed." }
}
if (-not $NoLsp) {
  switch ($Editor) {
    'auto' {
      if (Get-Command code -ErrorAction SilentlyContinue) { Install-Extension 'code' }
      if (Get-Command codium -ErrorAction SilentlyContinue) { Install-Extension 'codium' }
    }
    'code' { Install-Extension 'code' }
    'codium' { Install-Extension 'codium' }
  }
}

# --- check it works ---
$check = Join-Path ([IO.Path]::GetTempPath()) ("nemerle-install-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $check | Out-Null
Set-Content -Path (Join-Path $check 'hello.n') -Value 'System.Console.WriteLine("Nemerle is installed")'
$output = & (Join-Path $bin $(if ($onWindows) { 'nscript.cmd' } else { 'nscript' })) run (Join-Path $check 'hello.n') --no-cache 2>&1
$status = $LASTEXITCODE
Remove-Item -Recurse -Force $check
if ($status -ne 0) { throw "The installed nscript does not run: $output" }
Write-Host $output
Write-Host ''
$where = if ($onWindows) { 'added to your user PATH; open a new terminal' } else { 'add it to your PATH' }
Write-Host "ncc, nscript$(if (-not $NoLsp) { ' and nemerle-lsp' }) are in $bin ($where)."
Write-Host 'Next: doc\book\src\SUMMARY.md'
