<#
.SYNOPSIS
Installs Nemerle for the current user on Windows: the compiler (ncc), scripting (nscript), Nitra and the language
server (nemerle-lsp), and the VS Code / VSCodium extension as a .vsix next to this script (install\nemerle-<version>.vsix),
which it also installs in VS Code or VSCodium (-Editor none: only the .vsix). Run it from a clone of the repository.

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
  [switch]$NoDebugger,
  [ValidateSet('auto', 'code', 'codium', 'none')][string]$Editor = 'auto',
  [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 has no $IsWindows; PowerShell 7 on Linux/macOS gets shell launchers instead of .cmd ones.
$onWindows = ($null -eq $IsWindows) -or $IsWindows

$repo = Split-Path -Parent $PSScriptRoot
$bin = Join-Path $Prefix 'bin'
$extension = 'neo-nemerle.nemerle-0.2.0'
$oldExtension = 'nemerle.nemerle-nitra-0.1.0'
$extensionRoots = @{ code = (Join-Path $HOME '.vscode\extensions'); codium = (Join-Path $HOME '.vscode-oss\extensions') }

function Set-UserPath([string]$dir, [bool]$add) {
  $current = [Environment]::GetEnvironmentVariable('Path', 'User')
  $parts = @($current -split ';' | Where-Object { $_ -and $_ -ne $dir })
  if ($add) { $parts += $dir }
  [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
}

if ($Uninstall) {
  Remove-Item -Recurse -Force $Prefix -ErrorAction SilentlyContinue
  foreach ($root in $extensionRoots.Values) {
    foreach ($name in $extension, $oldExtension) { Remove-Item -Recurse -Force (Join-Path $root $name) -ErrorAction SilentlyContinue }
  }
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

# --- the debugger: netcoredbg (MIT), which the extension debugs with; it looks in $Prefix\tools\netcoredbg ---
if (-not $NoLsp -and -not $NoDebugger) {
  # the machine's architecture: Windows says it in PROCESSOR_ARCHITECTURE (Windows PowerShell 5.1 on .NET Framework
  # has no RuntimeInformation.OSArchitecture); PowerShell 7 elsewhere asks .NET
  $arch = if ($onWindows) { if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE } }
          else { [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString() }
  $asset = if ($onWindows) { if ($arch -eq 'AMD64') { 'netcoredbg-win64.zip' } else { $null } }
           elseif ($IsMacOS) { 'netcoredbg-osx-amd64.tar.gz' }
           elseif ($arch -eq 'Arm64') { 'netcoredbg-linux-arm64.tar.gz' } else { 'netcoredbg-linux-amd64.tar.gz' }
  $dbg = Join-Path $Prefix 'tools\netcoredbg'
  if (-not $asset) { Write-Host "Skipping the debugger: netcoredbg has no build for this machine ($arch)." }
  else {
    Remove-Item -Recurse -Force $dbg -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $dbg | Out-Null
    $download = Join-Path $dbg $asset
    try {
      $ProgressPreference = 'SilentlyContinue'
      # Windows PowerShell 5.1 may default to TLS versions GitHub refuses
      [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
      Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/Samsung/netcoredbg/releases/latest/download/$asset" -OutFile $download
      if ($asset.EndsWith('.zip')) { Expand-Archive -Path $download -DestinationPath $dbg -Force } else { & tar -xzf $download -C $dbg }
      Remove-Item -Force $download
      Write-Host "The debugger: $(Join-Path $dbg 'netcoredbg')"
    } catch {
      Remove-Item -Recurse -Force $dbg -ErrorAction SilentlyContinue
      Write-Host "Skipping the debugger: netcoredbg could not be downloaded ($($_.Exception.Message)); debug later with netcoredbg on PATH."
    }
  }
}

# --- the editor extension: a .vsix (next to this script) that carries the server, installed by the editor ---
function New-Vsix {
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Write-Host 'Skipping the editor extension: npm is needed to fetch its one dependency.'; return $null }
  $source = Join-Path $repo 'tools\language-server\vscode'
  $manifest = Get-Content -Raw (Join-Path $source 'package.json') | ConvertFrom-Json
  $vsix = Join-Path $PSScriptRoot "$($manifest.name)-$($manifest.version).vsix"
  $work = Join-Path ([IO.Path]::GetTempPath()) ("nemerle-vsix-" + [Guid]::NewGuid().ToString('N'))
  $ext = Join-Path $work 'extension'
  New-Item -ItemType Directory -Force -Path $ext | Out-Null
  try {
    foreach ($file in 'package.json', 'extension.js', 'language-configuration.json', 'README.md') { Copy-Item (Join-Path $source $file) $ext }
    Copy-Item -Recurse (Join-Path $source 'syntaxes') $ext
    Copy-Item -Recurse (Join-Path $source 'images') $ext
    Copy-Item (Join-Path $repo 'LICENSES\GPL-2.0-or-later.txt') (Join-Path $ext 'LICENSE.txt')
    # the client library, the extension's one production dependency
    Push-Location $ext
    try { & npm install --omit=dev --no-audit --no-fund --silent *> $null; $ok = ($LASTEXITCODE -eq 0) } finally { Pop-Location }
    if (-not $ok) { Write-Host 'Skipping the editor extension: npm install failed.'; return $null }
    Remove-Item -Force (Join-Path $ext 'package-lock.json') -ErrorAction SilentlyContinue
    # the server: the installed toolchain with nemerle-lsp.exe and its reference assemblies
    Copy-Item -Recurse $tc (Join-Path $ext 'server')
    $escape = { param($s) [Security.SecurityElement]::Escape([string]$s) }
    $tags = ($manifest.keywords -join ',')
    $utf8 = New-Object Text.UTF8Encoding $false   # no byte-order mark (Windows PowerShell 5.1 would write one)
    [IO.File]::WriteAllText((Join-Path $work 'extension.vsixmanifest'), @"
<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="$($manifest.name)" Version="$($manifest.version)" Publisher="$($manifest.publisher)" />
    <DisplayName>$(& $escape $manifest.displayName)</DisplayName>
    <Description xml:space="preserve">$(& $escape $manifest.description)</Description>
    <Tags>$tags</Tags>
    <Categories>$($manifest.categories -join ',')</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Icon>extension/images/icon.png</Icon>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="$($manifest.engines.vscode)" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace" />
      <Property Id="Microsoft.VisualStudio.Code.LocalizedLanguages" Value="" />
      <Property Id="Microsoft.VisualStudio.Services.Links.Source" Value="$($manifest.repository.url)" />
    </Properties>
    <License>extension/LICENSE.txt</License>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code" /></Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE.txt" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Icons.Default" Path="extension/images/icon.png" Addressable="true" />
  </Assets>
</PackageManifest>
"@, $utf8)
    $kinds = @{ '.json' = 'application/json'; '.js' = 'application/javascript'; '.md' = 'text/markdown'; '.txt' = 'text/plain';
                '.png' = 'image/png'; '.svg' = 'image/svg+xml'; '.vsixmanifest' = 'text/xml'; '.xml' = 'text/xml' }
    $files = @(Get-ChildItem -Recurse -File $work)
    $types = ($files | ForEach-Object { $_.Extension.ToLowerInvariant() } | Where-Object { $_ } | Sort-Object -Unique |
      ForEach-Object { $kind = if ($kinds.ContainsKey($_)) { $kinds[$_] } else { 'application/octet-stream' }; "<Default Extension=`"$_`" ContentType=`"$kind`" />" }) -join ''
    # (a literal path: [ and ] are wildcards to -Path)
    [IO.File]::WriteAllText((Join-Path $work '[Content_Types].xml'), "<?xml version=`"1.0`" encoding=`"utf-8`"?>`n<Types xmlns=`"http://schemas.openxmlformats.org/package/2006/content-types`">$types</Types>", $utf8)
    # the zip, with forward slashes in its entry names (Compress-Archive on Windows PowerShell writes backslashes)
    Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
    Remove-Item -Force $vsix -ErrorAction SilentlyContinue
    $zip = [IO.Compression.ZipFile]::Open($vsix, [IO.Compression.ZipArchiveMode]::Create)
    try {
      $root = (Resolve-Path $work).Path.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
      foreach ($file in Get-ChildItem -Recurse -File $work) {
        $name = $file.FullName.Substring($root.Length).Replace('\', '/')
        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, $name)
      }
    } finally { $zip.Dispose() }
    Write-Host "The editor extension: $vsix (install it by hand with Extensions > ... > Install from VSIX)"
    return $vsix
  } finally { Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue }
}
function Install-Vsix([string]$editorName, [string]$vsix) {
  # the editor's own command installs it (the old copied-in folder goes first)
  foreach ($name in $extension, $oldExtension) { Remove-Item -Recurse -Force (Join-Path $extensionRoots[$editorName] $name) -ErrorAction SilentlyContinue }
  & $editorName --install-extension $vsix --force *> $null
  if ($LASTEXITCODE -eq 0) { Write-Host "Installed the extension in $editorName" } else { Write-Host "$editorName could not install $vsix; install it by hand from the Extensions view." }
}
if (-not $NoLsp) {
  $vsix = New-Vsix
  if ($vsix) {
    switch ($Editor) {
      'auto' {
        if (Get-Command code -ErrorAction SilentlyContinue) { Install-Vsix 'code' $vsix }
        if (Get-Command codium -ErrorAction SilentlyContinue) { Install-Vsix 'codium' $vsix }
      }
      'code' { Install-Vsix 'code' $vsix }
      'codium' { Install-Vsix 'codium' $vsix }
    }
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
