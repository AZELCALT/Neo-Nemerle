# Shared by the Windows installer and its prerequisite/repair checks. No work runs when this file is dot-sourced.
function Update-InstallPath {
  $parts = New-Object Collections.Generic.List[string]
  foreach ($value in @([Environment]::GetEnvironmentVariable('Path', 'Machine'),
                       [Environment]::GetEnvironmentVariable('Path', 'User'), $env:Path)) {
    foreach ($part in ($value -split [IO.Path]::PathSeparator)) {
      if ($part -and -not $parts.Contains($part)) { $parts.Add($part) }
    }
  }
  foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if (-not $base) { continue }
    foreach ($relative in @('dotnet', 'Mono\bin', 'Git\cmd', 'nodejs', 'Microsoft VS Code\bin', 'VSCodium\bin')) {
      $part = Join-Path $base $relative
      if ((Test-Path $part) -and -not $parts.Contains($part)) { $parts.Add($part) }
    }
  }
  if ($env:LOCALAPPDATA) {
    foreach ($relative in @('Microsoft\WindowsApps', 'Programs\Microsoft VS Code\bin', 'Programs\VSCodium\bin')) {
      $part = Join-Path $env:LOCALAPPDATA $relative
      if ((Test-Path $part) -and -not $parts.Contains($part)) { $parts.Add($part) }
    }
  }
  $env:Path = $parts -join [IO.Path]::PathSeparator
}

function Install-WinGetDependency([string]$id, [string]$label) {
  if (-not $onWindows -or $NoDependencies) { throw "$label is required. Automatic dependency installation is disabled." }
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing Windows Package Manager for the current user'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Install-PackageProvider -Name NuGet -Scope CurrentUser -Force | Out-Null
    Install-Module -Name Microsoft.WinGet.Client -Repository PSGallery -Scope CurrentUser -Force
    Import-Module Microsoft.WinGet.Client
    Repair-WinGetPackageManager -Latest -Force
    Update-InstallPath
  }
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Windows Package Manager repair did not make winget available.' }
  Write-Host "Installing $label with winget ($id)"
  $arguments = @('install', '--id', $id, '--exact', '--source', 'winget', '--silent',
                 '--accept-source-agreements', '--accept-package-agreements', '--disable-interactivity')
  New-Item -ItemType Directory -Force -Path $Prefix | Out-Null
  $log = Join-Path $Prefix 'dependencies.log'
  Invoke-Native {
    & winget @arguments 2>&1 | Tee-Object -FilePath $log -Append | Out-Host
    $script:DependencyExitCode = $LASTEXITCODE
  }
  if ($script:DependencyExitCode -ne 0 -and $script:DependencyExitCode -ne 3010) {
    throw "winget could not install $label (exit $script:DependencyExitCode); see $log"
  }
  Update-InstallPath
  Note 'installed' "$label ($id)"
}

function Test-DotNet([bool]$sdk) {
  $option = if ($sdk) { '--list-sdks' } else { '--list-runtimes' }
  $candidates = @()
  $command = Get-Command dotnet -ErrorAction SilentlyContinue
  if ($command) { $candidates += $command.Source }
  if ($onWindows) {
    foreach ($base in @($env:ProgramFiles, $env:ProgramW6432, $env:DOTNET_ROOT)) {
      if (-not $base) { continue }
      $path = if ($base -eq $env:DOTNET_ROOT) { Join-Path $base 'dotnet.exe' } else { Join-Path $base 'dotnet\dotnet.exe' }
      if ((Test-Path $path) -and $candidates -notcontains $path) { $candidates += $path }
    }
  }
  foreach ($candidate in $candidates) {
    $rows = @(Invoke-Native { & $candidate $option 2>$null })
    if ($LASTEXITCODE -ne 0) { continue }
    $usable = if ($sdk) { [bool]($rows | Where-Object { $_ -match '^10\.\d+\.\d+\s' }) }
              else { [bool]($rows | Where-Object { $_ -match '^Microsoft\.NETCore\.App 10\.\d+\.\d+\s+\[' }) }
    if ($usable) {
      $directory = Split-Path -Parent $candidate
      $env:Path = $directory + [IO.Path]::PathSeparator + $env:Path
      return $true
    }
  }
  return $false
}

function Find-InstallPython {
  $candidates = @()
  if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += @{ Command = 'py'; Arguments = @('-3') } }
  foreach ($name in @('python', 'python3')) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notmatch 'WindowsApps[\\/]python') {
      $candidates += @{ Command = $command.Source; Arguments = @() }
    }
  }
  if ($env:LOCALAPPDATA) {
    $folder = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    if (Test-Path $folder) {
      foreach ($directory in Get-ChildItem $folder -Directory | Sort-Object Name -Descending) {
        $path = Join-Path $directory.FullName 'python.exe'
        if (Test-Path $path) { $candidates += @{ Command = $path; Arguments = @() } }
      }
    }
  }
  foreach ($candidate in $candidates) {
    $command = $candidate.Command; $arguments = @($candidate.Arguments) + @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)')
    Invoke-Native { & $command @arguments *> $null }
    if ($LASTEXITCODE -eq 0) { return $candidate }
  }
  return $null
}

function Install-NemerlePrerequisites {
  Update-InstallPath
  if (-not (Test-DotNet ([bool]$Build))) {
    $id = if ($Build) { 'Microsoft.DotNet.SDK.10' } else { 'Microsoft.DotNet.Runtime.10' }
    Install-WinGetDependency $id $(if ($Build) { '.NET 10 SDK' } else { '.NET 10 runtime' })
    if (-not (Test-DotNet ([bool]$Build))) { throw 'The .NET 10 installation is not usable in this process; see dependencies.log.' }
  }
  if (-not $Build) { return }
  if (-not (Find-InstallPython)) {
    Install-WinGetDependency 'Python.Python.3.14' 'Python 3'
    if (-not (Find-InstallPython)) { throw 'Python was installed but cannot be started; see dependencies.log.' }
  }
  if (-not (Get-Command sn -ErrorAction SilentlyContinue)) {
    Install-WinGetDependency 'Mono.Mono' 'Mono strong-name verification tools'
    if (-not (Get-Command sn -ErrorAction SilentlyContinue)) { throw 'Mono was installed but sn is not available; see dependencies.log.' }
  }
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Install-WinGetDependency 'Git.Git' 'Git (source build metadata)'
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git was installed but cannot be started; see dependencies.log.' }
  }
}

function Get-CompilerCodeDomIdentity([string]$compiler) {
  if ($PSVersionTable.PSEdition -ne 'Core') {
    return ([Reflection.Assembly]::ReflectionOnlyLoadFrom($compiler).GetReferencedAssemblies() |
      Where-Object { $_.Name -eq 'System.CodeDom' } | Select-Object -First 1)
  }
  Add-Type -AssemblyName System.Reflection.Metadata
  $stream = [IO.File]::OpenRead($compiler)
  $pe = New-Object Reflection.PortableExecutable.PEReader($stream)
  try {
    $reader = [Reflection.Metadata.PEReaderExtensions]::GetMetadataReader($pe)
    foreach ($handle in $reader.AssemblyReferences) {
      $reference = $reader.GetAssemblyReference($handle)
      if ($reader.GetString($reference.Name) -ne 'System.CodeDom') { continue }
      $identity = New-Object Reflection.AssemblyName 'System.CodeDom'
      $identity.Version = $reference.Version
      $identity.CultureName = ''
      if (-not $reference.Culture.IsNil) { $identity.CultureName = $reader.GetString($reference.Culture) }
      $key = $reader.GetBlobBytes($reference.PublicKeyOrToken)
      if (([int]$reference.Flags -band 1) -ne 0) { $identity.SetPublicKey($key) } else { $identity.SetPublicKeyToken($key) }
      return $identity
    }
  } finally { $pe.Dispose(); $stream.Dispose() }
  throw "No System.CodeDom reference found in $compiler"
}

function Test-CodeDomIdentity([string]$path, [Reflection.AssemblyName]$required) {
  if (-not (Test-Path $path)) { return $false }
  try { return [Reflection.AssemblyName]::GetAssemblyName($path).FullName -eq $required.FullName }
  catch { return $false }
}

function Repair-ToolchainCodeDom([string]$toolchain, [string]$fallback) {
  $required = Get-CompilerCodeDomIdentity (Join-Path $toolchain 'Nemerle.Compiler.dll')
  $destination = Join-Path $toolchain 'System.CodeDom.dll'
  if (Test-CodeDomIdentity $destination $required) { return }
  Write-Host "Repairing System.CodeDom: compiler requires $($required.FullName)"
  $candidate = Join-Path $fallback 'System.CodeDom.dll'
  if (Test-CodeDomIdentity $candidate $required) {
    Copy-Item -Force $candidate $destination
  } else {
    if ($NoDependencies) { throw "A matching $($required.FullName) is missing; dependency downloads are disabled." }
    # CodeDOM is an app-local compiler dependency, not a machine-wide SDK assembly. Fetch its matching NuGet major.
    $version = "$($required.Version.Major).0.0"
    $work = Join-Path ([IO.Path]::GetTempPath()) ('nemerle-codedom-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $work | Out-Null
    try {
      $package = Join-Path $work 'codedom.zip'
      [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
      Invoke-WebRequest -UseBasicParsing -Uri "https://api.nuget.org/v3-flatcontainer/system.codedom/$version/system.codedom.$version.nupkg" -OutFile $package
      if ($version -eq '10.0.0' -and (Get-FileHash -Algorithm SHA256 $package).Hash -ne '7DF3177B7E57544E3D19DE9B6F3D904664E4083793B929C661F29367AFCCB52F') {
        throw 'System.CodeDom 10.0.0 package failed SHA-256 verification.'
      }
      Add-Type -AssemblyName System.IO.Compression.FileSystem
      $archive = [IO.Compression.ZipFile]::OpenRead($package)
      try {
        $entry = $archive.GetEntry('lib/net10.0/System.CodeDom.dll')
        if (-not $entry) { throw "The System.CodeDom $version package has no .NET 10 implementation." }
        $candidate = Join-Path $work 'System.CodeDom.dll'
        $input = $entry.Open(); $output = [IO.File]::Create($candidate)
        try { $input.CopyTo($output) } finally { $input.Dispose(); $output.Dispose() }
        if (-not (Test-CodeDomIdentity $candidate $required)) { throw "The downloaded DLL does not match $($required.FullName)" }
        Copy-Item -Force $candidate $destination
      } finally { $archive.Dispose() }
    } finally { Remove-Item -Recurse -Force $work }
  }
  if (-not (Test-CodeDomIdentity $destination $required)) { throw 'System.CodeDom repair failed verification.' }
  Note 'repaired' "System.CodeDom $($required.Version), matched to the compiler"
}
