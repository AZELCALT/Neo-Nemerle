# Licensing and credits

This repository revives [Nemerle](https://github.com/rsdn/nemerle) on .NET 10, with [Nitra](https://github.com/rsdn/nitra)
built in. Different parts are under different licenses, so that the compiler stays free software while the programs
you build with it remain yours.

| Part | License |
|---|---|
| The compiler (`ncc/`), the Nitra compiler and grammar (`native-nitra/upstream/Nitra/Nitra.Compiler`, `Nitra.Grammar`), scripting (`scripting*/`), the language server (`tools/language-server/`), `platform/`, `build/`, `tests/` | **GPL-2.0-or-later** with the **Nemerle Compiler Output Exception** ([LICENSE](LICENSE), [exception](LICENSES/LicenseRef-Nemerle-Output-Exception.txt)) |
| The standard library (`lib/`, `Nemerle.dll`) and standard macros (`macros/`, `Nemerle.Macros.dll`) | **BSD-3-Clause** ([lib/LICENSE](lib/LICENSE), [macros/LICENSE](macros/LICENSE)) |
| The Nitra runtime and DotNetLang (`native-nitra/upstream/Nitra/Nitra.Runtime`, `DotNetLang`) | **BSD-3-Clause** ([Nitra.Runtime/LICENSE](native-nitra/upstream/Nitra/Nitra.Runtime/LICENSE), [DotNetLang/LICENSE](native-nitra/upstream/Nitra/DotNetLang/LICENSE)) |
| The pinned toolchain (`boot/coreclr/`) | binaries of all of the above, plus the third-party components below |

[REUSE.toml](REUSE.toml) holds the same map in machine-readable form.

**What this means in practice:**
- **Programs you compile are yours.** The output exception says that code the compiler, its macros, quotations or
  Nitra grammar compiler put into your assemblies is not covered by the GPL. The libraries those assemblies use at run
  time are BSD.
- **The compiler stays free.** If you distribute a modified compiler, you distribute its source under the GPL too.

## Original work

The GPL parts include code written by the original Nemerle and Nitra teams under BSD-3-Clause. BSD-3 allows a modified
version to be distributed under the GPL. Its conditions are kept here:
- The original copyright notices and license texts stay with the code.
  - **Nemerle:** Copyright (c) 2003-2008 The University of Wroclaw, Copyright (c) 2008-2014 Nemerle Project Team.
    See [COPYRIGHT](COPYRIGHT) and [License.rtf](License.rtf).
  - **Nitra:** Copyright (c) 2014 JetBrains s.r.o. See [native-nitra/upstream/License.txt](native-nitra/upstream/License.txt).
- The names of the University of Wroclaw and of JetBrains are not used to endorse or promote this fork.
  Neither the original team nor JetBrains is responsible for it.

The original upstream code itself remains available under BSD-3 from [rsdn/nemerle](https://github.com/rsdn/nemerle).

## Third-party components in boot/coreclr

| Component | License | Notice |
|---|---|---|
| Mono.Cecil | MIT | `boot/coreclr/Mono.Cecil-LICENSE.txt` |
| .NET reference assemblies and runtime pieces | MIT | `boot/coreclr/Dotnet-LICENSE.txt`, `Dotnet-ThirdPartyNotices.txt` |
| NuGet client libraries (scripting NuGet adapter) | Apache-2.0 | `boot/coreclr/Nemerle.Scripting.NuGet.NOTICES.txt` |
| Newtonsoft.Json | MIT | same file |

Apache-2.0 is not compatible with GPL version 2 alone. Because this fork is GPL-2.0-*or-later*, the NuGet adapter is
distributed under the terms of GPL version 3.
