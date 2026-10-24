param([string]$Repository, [string]$Work, [string]$CodeDomPackage)
$ErrorActionPreference = 'Stop'
$helper = Join-Path $Repository 'install/dependencies.ps1'
. $helper
function Check([bool]$condition, [string]$message) { if (-not $condition) { throw $message } }
function Invoke-Native([scriptblock]$command) { & $command }
function Note([string]$what, [string]$text) { }
$Prefix = $Work
$onWindows = $true
$NoDependencies = $false

# A successful winget process must install an exact package and refresh the current process's PATH.
& {
  $script:wingetArguments = @()
  $script:refreshed = 0
  function winget { $script:wingetArguments = @($args); $global:LASTEXITCODE = 0 }
  function Update-InstallPath { $script:refreshed++ }
  Install-WinGetDependency 'Microsoft.DotNet.Runtime.10' '.NET runtime'
  Check ($script:wingetArguments -contains '--exact') 'winget must use an exact ID'
  Check ($script:wingetArguments -contains '--accept-package-agreements') 'package agreements must be handled'
  Check ($script:wingetArguments -contains 'Microsoft.DotNet.Runtime.10') 'wrong runtime package'
  Check ($script:refreshed -eq 1) 'the process PATH was not refreshed'
  function winget { $global:LASTEXITCODE = 17 }
  $failed = $false
  try { Install-WinGetDependency 'Microsoft.DotNet.Runtime.10' '.NET runtime' } catch { $failed = $_.Exception.Message -match 'exit 17' }
  Check $failed 'a failed package installation was reported as success'
}

# Missing prerequisites are installed once; existing prerequisites produce no package-manager actions.
& {
  $script:wingetReady = $false
  $script:bootstrapped = @()
  function Get-Command([string]$Name, $ErrorAction) { if ($script:wingetReady) { return @{ Source = 'winget.exe' } }; return $null }
  function Install-PackageProvider { param($Name, $Scope, [switch]$Force); Check ($Scope -eq 'CurrentUser') 'provider must not require a machine-wide bootstrap'; $script:bootstrapped += 'provider' }
  function Install-Module { param($Name, $Repository, $Scope, [switch]$Force); Check ($Name -eq 'Microsoft.WinGet.Client') 'wrong WinGet module'; $script:bootstrapped += 'module' }
  function Import-Module { param($Name) }
  function Repair-WinGetPackageManager { param([switch]$Latest, [switch]$Force); $script:wingetReady = $true; $script:bootstrapped += 'repair' }
  function Update-InstallPath { }
  function winget { $global:LASTEXITCODE = 0 }
  Install-WinGetDependency 'Microsoft.DotNet.Runtime.10' '.NET runtime'
  Check (($script:bootstrapped -join ',') -eq 'provider,module,repair') 'missing winget was not bootstrapped'
}
& {
  $Build = $false
  $script:available = $false
  $script:installs = @()
  function Update-InstallPath { }
  function Test-DotNet([bool]$sdk) { return $script:available }
  function Install-WinGetDependency([string]$id, [string]$label) { $script:installs += $id; $script:available = $true }
  Install-NemerlePrerequisites
  Install-NemerlePrerequisites
  Check ($script:installs.Count -eq 1 -and $script:installs[0] -eq 'Microsoft.DotNet.Runtime.10') 'runtime installation is not idempotent'
}
& {
  $Build = $true
  $script:ready = @{}
  $script:installs = @()
  function Update-InstallPath { }
  function Test-DotNet([bool]$sdk) { return $script:ready.ContainsKey('Microsoft.DotNet.SDK.10') }
  function Find-InstallPython { if ($script:ready.ContainsKey('Python.Python.3.14')) { return @{ Command = 'py'; Arguments = @('-3') } }; return $null }
  function Get-Command([string]$Name, $ErrorAction) {
    if ($Name -eq 'sn' -and $script:ready.ContainsKey('Mono.Mono')) { return @{ Source = 'sn.bat' } }
    if ($Name -eq 'git' -and $script:ready.ContainsKey('Git.Git')) { return @{ Source = 'git.exe' } }
    return $null
  }
  function Install-WinGetDependency([string]$id, [string]$label) { $script:installs += $id; $script:ready[$id] = $true }
  Install-NemerlePrerequisites
  Check (($script:installs -join ',') -eq 'Microsoft.DotNet.SDK.10,Python.Python.3.14,Mono.Mono,Git.Git') 'source-build prerequisites are incomplete'
}
& {
  $NoDependencies = $true
  $failed = $false
  try { Install-WinGetDependency 'anything' 'dependency' } catch { $failed = $_.Exception.Message -match 'disabled' }
  Check $failed '-NoDependencies did not prevent package installation'
}

$toolchain = Join-Path $Work 'codedom repair'
New-Item -ItemType Directory -Path $toolchain | Out-Null
$boot = Join-Path $Repository 'boot/coreclr'
Copy-Item (Join-Path $boot 'Nemerle.Compiler.dll') $toolchain
$required = Get-CompilerCodeDomIdentity (Join-Path $toolchain 'Nemerle.Compiler.dll')
Check (Test-CodeDomIdentity (Join-Path $boot 'System.CodeDom.dll') $required) 'the compiler reference was read incorrectly'
Set-Content (Join-Path $toolchain 'System.CodeDom.dll') 'an incompatible assembly'
$NoDependencies = $true
Repair-ToolchainCodeDom $toolchain $boot
Check (Test-CodeDomIdentity (Join-Path $toolchain 'System.CodeDom.dll') $required) 'local CodeDOM repair failed'
if ($CodeDomPackage) {
  Remove-Item (Join-Path $toolchain 'System.CodeDom.dll')
  $NoDependencies = $false
  function Invoke-WebRequest {
    param([switch]$UseBasicParsing, [string]$Uri, [string]$OutFile)
    Check ($Uri -eq 'https://api.nuget.org/v3-flatcontainer/system.codedom/10.0.0/system.codedom.10.0.0.nupkg') 'wrong dependency origin'
    Copy-Item $CodeDomPackage $OutFile
  }
  Repair-ToolchainCodeDom $toolchain (Join-Path $Work 'missing')
  Check (Test-CodeDomIdentity (Join-Path $toolchain 'System.CodeDom.dll') $required) 'NuGet CodeDOM repair failed'
}
Write-Host 'PASS: winget arguments, failure handling, PATH refresh, idempotence, build prerequisites and CodeDOM identity/repair'
