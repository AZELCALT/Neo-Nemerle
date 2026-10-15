# legacy/

Upstream Nemerle's files for the original .NET Framework / Mono / Visual Studio era, moved here unchanged so that the
repository root shows what this fork actually builds. None of this is used by `./bootstrap`.

| Here | What it was |
|---|---|
| `*.cmd`, `*.sln`, `*.nproj`, `*.csproj`, `*.nuspec`, `Nemerle.build`, `Makefile`, `configure`, `Build-Mono.sh`, `INSTALL` | upstream build, installer and registration scripts (MSBuild 4 / xbuild / NAnt) |
| `boot/`, `boot-4.0/` | upstream's pinned .NET Framework compilers (this fork's pinned compiler is `boot/coreclr/` at the root) |
| `VsIntegration/`, `ExternalDependences/` | Visual Studio 2008-2017 integration and its SDK submodules |
| `snippets/` | upstream examples and side projects (Statechart, PEG parser, computation expressions, ...), still in classic `namespace` style |
| `Linq/` | Nemerle.Linq |
| `github-workflows/` | upstream's Windows CI, disabled here |
| `README`, `NEWS`, `SECURITY.md` | upstream text files |

These files still use classic Nemerle (`namespace` blocks) and old .NET APIs. Porting any of them is welcome; a
ported project moves out of `legacy/`.
