# Licensing and credits

This repository revives [Nemerle](https://github.com/rsdn/nemerle) on .NET 10, with [Nitra](https://github.com/rsdn/nitra)
built in. Different parts are under different licenses, so that the compiler stays free software while the programs
you build with it remain yours.

| Part | License |
|---|---|
| The compiler (`ncc/`), the standard macros (`macros/`), Nitra (`native-nitra/`: runtime, grammar, compiler, DotNetLang), scripting (`scripting*/`), the language server (`tools/language-server/`), `platform/`, `build/`, `tests/` | **GPL-2.0-or-later** with the **Nemerle Compiler Output Exception** ([LICENSE](LICENSE), [exception](LICENSES/LicenseRef-Nemerle-Output-Exception.txt)) |
| The standard library (`lib/`, `Nemerle.dll`) | **BSD-3-Clause** ([lib/LICENSE](lib/LICENSE)) |
| The pinned toolchain (`boot/coreclr/`) | binaries of all of the above, plus the third-party components below |

[REUSE.toml](REUSE.toml) holds the same map in machine-readable form.

**What this means in practice:**
- **Programs you compile can be closed.** The output exception says that code the compiler, macros, quotations or
  `space` blocks put into your assemblies is not covered by the GPL. The standard library those assemblies use at run
  time is BSD; a compiled `space` needs no Nitra at run time.
- **Language extensions are always open.** Macros and Nitra grammars change the language itself. Macro libraries and
  compiled grammar images are GPL, and a program keeps its exception only if the source of every macro or grammar it
  contains or was built with is published under the GPL. The program's ordinary code, and the text inside its `space`
  blocks, may stay closed. That way nobody ships a private dialect that users mistake for Nemerle.
- **The compiler and Nitra stay free.** If you distribute a modified compiler or Nitra, you distribute its source
  under the GPL too.

The exception is new legal text, written for this fork. Have a lawyer review it before relying on it commercially.

## Original work

The GPL parts include code written by the original Nemerle and Nitra teams under BSD-3-Clause; Nitra is entirely such code. BSD-3 allows a modified
version to be distributed under the GPL. Its conditions are kept here:
- The original copyright notices and license texts stay with the code.
  - **Nemerle:** Copyright (c) 2003-2008 The University of Wroclaw, Copyright (c) 2008-2014 Nemerle Project Team.
    See [COPYRIGHT](COPYRIGHT) and [License.rtf](License.rtf).
  - **Nitra:** Copyright (c) 2014 JetBrains s.r.o. See [native-nitra/upstream/License.txt](native-nitra/upstream/License.txt).
- The names of the University of Wroclaw and of JetBrains are not used to endorse or promote this fork.
  Neither the original team nor JetBrains is responsible for it.

The original upstream code itself remains available under BSD-3 from [rsdn/nemerle](https://github.com/rsdn/nemerle).
The standard macros keep the original BSD notice in their file headers ([COPYRIGHT](COPYRIGHT)); this fork's version of
them is GPL.

## Third-party components in boot/coreclr

| Component | License | Notice |
|---|---|---|
| Mono.Cecil | MIT | `boot/coreclr/Mono.Cecil-LICENSE.txt` |
| .NET reference assemblies and runtime pieces | MIT | `boot/coreclr/Dotnet-LICENSE.txt`, `Dotnet-ThirdPartyNotices.txt` |
| NuGet client libraries (scripting NuGet adapter) | Apache-2.0 | `boot/coreclr/Nemerle.Scripting.NuGet.NOTICES.txt` |
| Newtonsoft.Json | MIT | same file |

Apache-2.0 is not compatible with GPL version 2 alone. Because this fork is GPL-2.0-*or-later*, the NuGet adapter is
distributed under the terms of GPL version 3.
