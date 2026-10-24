<#
.SYNOPSIS
Installs Nemerle for the current user on Windows: the compiler (ncc), scripting (nscript), Nitra and the language
server (nemerle-lsp), and the VS Code / VSCodium extension as a .vsix next to this script (install\nemerle-<version>.vsix),
which it also installs in VS Code or VSCodium (-Editor none: only the .vsix). Run it from a clone of the repository.

.EXAMPLE
install\install.cmd
install\install.cmd -Editor none
install\install.cmd -Uninstall

Installs missing Windows prerequisites with winget (runtime for an install; SDK, Python and Mono for -Build).
-NoDependencies uses existing prerequisites and disables online CodeDOM repair. The editor extension's JavaScript
dependencies are downloaded from the npm registry as package-lock.json pins them (checked against its hashes); npm
itself is used only when that cannot be done. -Build compiles everything from source first and needs Python 3 and the
strong-name tool sn as well.
#>
param(
  [string]$Prefix = $(if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'Nemerle' } else { Join-Path $HOME '.local/share/nemerle' }),
  [switch]$Build,
  [switch]$NoLsp,
  [switch]$NoDebugger,
  [switch]$NoDependencies,
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

# Windows PowerShell 5.1 turns a native program's redirected stderr into errors, which 'Stop' makes fatal (a
# warning would end the install): native calls whose output is redirected run with 'Continue', judged by exit code
function Invoke-Native([scriptblock]$command) {
  $saved = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { & $command } finally { $ErrorActionPreference = $saved }
}

# what was installed and what was skipped (and why), printed at the end
$notes = New-Object Collections.Generic.List[string]
function Note([string]$what, [string]$text) { $notes.Add(('  {0,-10} {1}' -f $what, $text)) }
. (Join-Path $PSScriptRoot 'dependencies.ps1')

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

# --- install prerequisites, then refresh this process so no terminal restart is needed ---
Install-NemerlePrerequisites

# --- which toolchain ---
$source = Join-Path $repo 'boot\coreclr'
function Build-SourceToolchain {
  $script:Build = $true
  Install-NemerlePrerequisites
  Write-Host 'Building from source (build\bootstrap.py --build-only); this takes a few minutes...'
  $python = Find-InstallPython
  $pythonCommand = $python.Command
  $buildOutput = Join-Path $Prefix 'build'
  $buildSeed = Join-Path ([IO.Path]::GetTempPath()) ('nemerle-install-boot-' + [Guid]::NewGuid().ToString('N'))
  try {
    Copy-Item -Recurse (Join-Path $repo 'boot\coreclr') $buildSeed
    Repair-ToolchainCodeDom $buildSeed (Join-Path $repo 'boot\coreclr')
    $pythonArgs = @($python.Arguments) + @((Join-Path $repo 'build\bootstrap.py'), '--build-only', '--boot', $buildSeed, '--output', $buildOutput)
    & $pythonCommand @pythonArgs
    if ($LASTEXITCODE -ne 0) { throw "The build failed; see $buildOutput\logs" }
  } finally { Remove-Item -Recurse -Force $buildSeed -ErrorAction SilentlyContinue }
  $script:source = Join-Path $buildOutput 'toolchain'
}
if ($Build) { Build-SourceToolchain }
if (-not (Test-Path (Join-Path $source 'ncc.exe'))) { throw "No toolchain in $source" }

Write-Host "Installing the toolchain from $source to $Prefix"
$finalToolchain = Join-Path $Prefix 'toolchain'
$tc = Join-Path $Prefix ('.toolchain-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Prefix, $bin | Out-Null
try {
Copy-Item -Recurse $source $tc
Repair-ToolchainCodeDom $tc (Join-Path $repo 'boot\coreclr')

# --- the language server, compiled from source with the installed compiler ---
if (-not $NoLsp) {
  Write-Host 'Building the language server'
  $serverSources = @(Get-ChildItem (Join-Path $repo 'tools\language-server') -Filter '*.n' | ForEach-Object { $_.FullName })
  $references = @('Nemerle.Compiler', 'Integrated.Nitra.Runtime', 'Integrated.Nitra.Grammar', 'Integrated.Nitra.Compiler', 'Integrated.DotNetLang', 'Nemerle.Scripting') |
    ForEach-Object { "-r:$(Join-Path $tc "$_.dll")" }
  $log = Join-Path $Prefix 'lsp-build.log'
  # the server stays a .NET assembly run by dotnet (the .cmd launcher and the extension start it so): on Windows the
  # compiler would otherwise make nemerle-lsp.exe a native launcher, with the server in nemerle-lsp.dll
  # one argument list, with no empty entries: Windows PowerShell 5.1 passes a splatted $null (an empty option list)
  # to a native program as an empty argument, which ncc refuses
  $nccArgs = @("-source-root:$(Join-Path $repo 'tools\language-server')") + $serverSources + @('-target:exe',
    "-out:$(Join-Path $tc 'nemerle-lsp.exe')", "-target-references:$(Join-Path $tc 'references')", '-no-color') + @($references)
  if ($onWindows) { $nccArgs += '-launcher-' }
  $nccArgs = @($nccArgs | Where-Object { $_ })
  Invoke-Native { & dotnet (Join-Path $tc 'ncc.exe') $nccArgs *> $log }
  if ($LASTEXITCODE -ne 0 -and -not $Build -and -not $NoDependencies) {
    Write-Host 'The pinned compiler could not build this checkout''s language server; rebuilding the matching source toolchain.'
    Copy-Item $log (Join-Path $Prefix 'lsp-bootstrap-build.log')
    Build-SourceToolchain
    Remove-Item -Recurse -Force $tc
    Copy-Item -Recurse $source $tc
    Repair-ToolchainCodeDom $tc (Join-Path $repo 'boot\coreclr')
    Invoke-Native { & dotnet (Join-Path $tc 'ncc.exe') $nccArgs *> $log }
  }
  if ($LASTEXITCODE -ne 0) { throw "Building the language server failed; see $log" }
  Copy-Item (Join-Path $tc 'ncc.runtimeconfig.json') (Join-Path $tc 'nemerle-lsp.runtimeconfig.json')
  Note 'installed' 'the language server (nemerle-lsp)'
} else { Note 'skipped' 'the language server, the debugger and the editor extension: -NoLsp' }

# Prove both entry points work before replacing an existing installation or changing PATH.
$check = Join-Path ([IO.Path]::GetTempPath()) ('nemerle-install-check-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $check | Out-Null
try {
  $hello = Join-Path $check 'hello.n'
  Set-Content -Path $hello -Value 'System.Console.WriteLine("Nemerle is installed")'
  $testArgs = @($hello, "-source-root:$check", "-target-references:$(Join-Path $tc 'references')",
                "-out:$(Join-Path $check 'hello.dll')", '-launcher-', '-no-color')
  $compilerOutput = Invoke-Native { & dotnet (Join-Path $tc 'ncc.exe') @testArgs 2>&1 }
  if ($LASTEXITCODE -ne 0) { throw "The staged compiler does not run: $compilerOutput" }
  Copy-Item (Join-Path $tc 'Nemerle.dll') $check
  $programOutput = Invoke-Native { & dotnet (Join-Path $check 'hello.dll') 2>&1 }
  if ($LASTEXITCODE -ne 0 -or "$programOutput" -notmatch 'Nemerle is installed') { throw "The compiled program does not run: $programOutput" }
  $scriptOutput = Invoke-Native { & dotnet (Join-Path $tc 'nscript.exe') run $hello --no-cache 2>&1 }
  if ($LASTEXITCODE -ne 0 -or "$scriptOutput" -notmatch 'Nemerle is installed') { throw "The staged script host does not run: $scriptOutput" }
} finally { Remove-Item -Recurse -Force $check }

$previousToolchain = Join-Path $Prefix ('.toolchain-previous-' + [Guid]::NewGuid().ToString('N'))
if (Test-Path $finalToolchain) { Move-Item $finalToolchain $previousToolchain }
try { Move-Item $tc $finalToolchain }
catch {
  if (Test-Path $previousToolchain) { Move-Item $previousToolchain $finalToolchain }
  throw
}
Remove-Item -Recurse -Force $previousToolchain -ErrorAction SilentlyContinue
$tc = $finalToolchain
Note 'installed' "the toolchain (ncc, nscript, Nitra) in $tc; compiler and scripting checks passed"
} catch {
  if ($tc -ne $finalToolchain) { Remove-Item -Recurse -Force $tc -ErrorAction SilentlyContinue }
  throw
}

# --- launchers (bin is added to the user's PATH) ---
function New-Launcher([string]$name, [string]$program, [bool]$references) {
  $dotnetCommand = (Get-Command dotnet).Source
  if ($onWindows) {
    $extra = if ($references) { '-target-references:"%~dp0..\toolchain\references" ' } else { '' }
    Set-Content -Encoding ASCII -Path (Join-Path $bin "$name.cmd") -Value "@`"$dotnetCommand`" `"%~dp0..\toolchain\$program`" $extra%*"
  } else {
    $extra = if ($references) { "-target-references:`"$tc/references`" " } else { '' }
    $path = Join-Path $bin $name
    Set-Content -Encoding ASCII -Path $path -Value "#!/bin/sh`nexec `"$dotnetCommand`" `"$tc/$program`" $extra`"`$@`""
    & chmod 755 $path
  }
}
New-Launcher 'ncc' 'ncc.exe' $true
New-Launcher 'nscript' 'nscript.exe' $false
if (-not $NoLsp) { New-Launcher 'nemerle-lsp' 'nemerle-lsp.exe' $false }
if ($onWindows) { Set-UserPath $bin $true }
Note 'installed' "the commands in $bin"
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
  if (-not $asset) { Write-Host "Skipping the debugger: netcoredbg has no build for this machine ($arch)."; Note 'skipped' "the debugger: netcoredbg has no build for this machine ($arch)" }
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
      Note 'installed' "the debugger (netcoredbg) in $dbg"
    } catch {
      Remove-Item -Recurse -Force $dbg -ErrorAction SilentlyContinue
      Write-Host "Skipping the debugger: netcoredbg could not be downloaded ($($_.Exception.Message)); debug later with netcoredbg on PATH."
      Note 'skipped' 'the debugger: netcoredbg could not be downloaded (debug later with netcoredbg on PATH)'
    }
  }
} elseif (-not $NoLsp) { Note 'skipped' 'the debugger: -NoDebugger' }

# --- the editor extension's JavaScript dependencies, as package-lock.json pins them ---
function Expand-Package([byte[]]$tgz, [string]$target) {
  # an npm package: a gzip'd tar whose entries sit under one top folder ("package/"), which is dropped. Read here
  # with .NET's GZipStream (Windows PowerShell 5.1 included), so no tar is needed: Windows' own is missing before
  # Windows 10 1803, and Git's GNU tar reads `C:\...' as a remote host.
  $gzip = New-Object IO.Compression.GZipStream((New-Object IO.MemoryStream(, $tgz)), [IO.Compression.CompressionMode]::Decompress)
  $tar = New-Object IO.MemoryStream
  try { $gzip.CopyTo($tar) } finally { $gzip.Dispose() }
  $data = $tar.ToArray()
  $text = { param($at, $length) [Text.Encoding]::UTF8.GetString($data, $at, $length).Split([char]0)[0] }
  $longName = $null
  $at = 0
  while ($at + 512 -le $data.Length) {
    $name = & $text $at 100
    if (-not $name) { break }   # the end: blocks of zeros
    $sizeText = (& $text ($at + 124) 12).Trim()
    $size = if ($sizeText) { [int][Convert]::ToInt64($sizeText, 8) } else { 0 }
    $type = [char]$data[$at + 156]
    if ((& $text ($at + 257) 5) -eq 'ustar') {
      $prefix = & $text ($at + 345) 155
      if ($prefix) { $name = $prefix + '/' + $name }
    }
    $body = $at + 512
    if ($type -eq 'x') {
      # a pax header: its path= record names the next entry
      foreach ($record in ([Text.Encoding]::UTF8.GetString($data, $body, $size) -split "`n")) {
        if ($record -match '^\d+ path=(.*)$') { $longName = $Matches[1] }
      }
    } elseif ($type -eq '0' -or $type -eq [char]0) {
      if ($longName) { $name = $longName; $longName = $null }
      $relative = ($name -split '/', 2)[1]
      if ($relative -and -not ($relative -split '/' | Where-Object { $_ -eq '..' })) {
        $path = Join-Path $target ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
        $file = [IO.File]::Create($path)
        try { $file.Write($data, $body, $size) } finally { $file.Dispose() }
      }
    } else { $longName = $null }
    $at = [int]($body + [Math]::Ceiling($size / 512.0) * 512)
  }
}
function Get-NodeModules([string]$lock, [string]$folder) {
  # each "node_modules/..." entry: its registry tarball, checked against its sha512, unpacked without its top folder;
  # throws with the reason when it cannot. (The lock file's root entry is named ""; Windows PowerShell 5.1's
  # ConvertFrom-Json refuses an empty name, so it is renamed first.)
  $text = (Get-Content -Raw $lock) -replace '"packages": \{\s*"": \{', '"packages": { "(root)": {'
  $packages = (ConvertFrom-Json $text).packages
  $ProgressPreference = 'SilentlyContinue'
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
  $download = Join-Path ([IO.Path]::GetTempPath()) ("nemerle-package-" + [Guid]::NewGuid().ToString('N') + '.tgz')
  try {
    foreach ($entry in $packages.PSObject.Properties) {
      if (-not $entry.Name.StartsWith('node_modules/') -or $entry.Value.dev -or $entry.Value.link) { continue }
      $url = $entry.Value.resolved; $integrity = [string]$entry.Value.integrity
      if (-not $integrity.StartsWith('sha512-')) { throw "$($entry.Name) has no sha512 hash in the lock file" }
      try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $download } catch { throw "$url could not be downloaded ($($_.Exception.Message))" }
      $bytes = [IO.File]::ReadAllBytes($download)
      $sha = [Security.Cryptography.SHA512]::Create()
      try { $hash = [Convert]::ToBase64String($sha.ComputeHash($bytes)) } finally { $sha.Dispose() }
      if ($hash -ne $integrity.Substring(7)) { throw "$url does not match its hash in the lock file" }
      $target = Join-Path $folder ($entry.Name.Replace('/', [IO.Path]::DirectorySeparatorChar))
      New-Item -ItemType Directory -Force -Path $target | Out-Null
      try { Expand-Package $bytes $target } catch { throw "$url could not be unpacked ($($_.Exception.Message))" }
    }
  } finally { Remove-Item -Force $download -ErrorAction SilentlyContinue }
}

# --- the editor extension: a .vsix (next to this script) that carries the server, installed by the editor ---
function New-Vsix {
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
    # the client library, the extension's one production dependency, and what it uses: from the npm registry as the
    # lock file pins them; npm only when that fails
    $lock = Join-Path $source 'package-lock.json'
    try { Get-NodeModules $lock $ext }
    catch {
      $why = $_.Exception.Message
      Remove-Item -Recurse -Force (Join-Path $ext 'node_modules') -ErrorAction SilentlyContinue
      if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        if ($onWindows -and -not $NoDependencies) { Install-WinGetDependency 'OpenJS.NodeJS.LTS' 'Node.js LTS (extension dependency fallback)' }
      }
      if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Host "Skipping the editor extension: its dependencies could not be fetched ($why)."
        Note 'skipped' "the editor extension: its dependencies could not be fetched ($why)"; return $null
      }
      Write-Host "The extension's dependencies could not be fetched directly ($why); using npm"
      Copy-Item $lock $ext
      Push-Location $ext
      try { Invoke-Native { & npm ci --omit=dev --no-audit --no-fund --silent *> $null }; $ok = ($LASTEXITCODE -eq 0) } finally { Pop-Location }
      if (-not $ok) {
        Write-Host "Skipping the editor extension: its dependencies could not be fetched ($why), and npm ci failed."
        Note 'skipped' "the editor extension: its dependencies could not be fetched ($why), nor by npm"; return $null
      }
      Remove-Item -Force (Join-Path $ext 'package-lock.json') -ErrorAction SilentlyContinue
    }
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
    Note 'installed' "the editor extension package: $vsix"
    return $vsix
  } finally { Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue }
}
function Install-Vsix([string]$editorName, [string]$vsix) {
  if ($onWindows -and -not (Get-Command $editorName -ErrorAction SilentlyContinue)) {
    $id = if ($editorName -eq 'code') { 'Microsoft.VisualStudioCode' } else { 'VSCodium.VSCodium' }
    Install-WinGetDependency $id $editorName
  }
  # the editor's own command installs it (the old copied-in folder goes first)
  foreach ($name in $extension, $oldExtension) { Remove-Item -Recurse -Force (Join-Path $extensionRoots[$editorName] $name) -ErrorAction SilentlyContinue }
  Invoke-Native { & $editorName --install-extension $vsix --force *> $null }
  if ($LASTEXITCODE -eq 0) { Write-Host "Installed the extension in $editorName"; Note 'installed' "the extension in $editorName" }
  else { Write-Host "$editorName could not install $vsix; install it by hand from the Extensions view."; Note 'skipped' "the extension in ${editorName}: --install-extension failed (install the .vsix by hand)" }
}
if (-not $NoLsp) {
  $vsix = New-Vsix
  if ($vsix) {
    switch ($Editor) {
      'auto' {
        if (Get-Command code -ErrorAction SilentlyContinue) { Install-Vsix 'code' $vsix }
        if (Get-Command codium -ErrorAction SilentlyContinue) { Install-Vsix 'codium' $vsix }
        if (-not (Get-Command code -ErrorAction SilentlyContinue) -and -not (Get-Command codium -ErrorAction SilentlyContinue)) {
          Note 'skipped' 'installing the extension in an editor: no code or codium on PATH'
        }
      }
      'code' { Install-Vsix 'code' $vsix }
      'codium' { Install-Vsix 'codium' $vsix }
      'none' { Note 'skipped' 'installing the extension in an editor: -Editor none' }
    }
  }
}

# --- check it works ---
$check = Join-Path ([IO.Path]::GetTempPath()) ("nemerle-install-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $check | Out-Null
Set-Content -Path (Join-Path $check 'hello.n') -Value 'System.Console.WriteLine("Nemerle is installed")'
$output = Invoke-Native { & (Join-Path $bin $(if ($onWindows) { 'nscript.cmd' } else { 'nscript' })) run (Join-Path $check 'hello.n') --no-cache 2>&1 }
$status = $LASTEXITCODE
Remove-Item -Recurse -Force $check
if ($status -ne 0) { throw "The installed nscript does not run: $output" }
Write-Host $output
Write-Host ''
Write-Host 'Summary:'
foreach ($line in $notes) { Write-Host $line }
Write-Host ''
$where = if ($onWindows) { 'added to your user PATH; open a new terminal' } else { 'add it to your PATH' }
Write-Host "ncc, nscript$(if (-not $NoLsp) { ' and nemerle-lsp' }) are in $bin ($where)."
Write-Host 'Next: doc\book\src\SUMMARY.md'
