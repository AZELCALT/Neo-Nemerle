# Licensing and credits

This repository is a revival of [Nemerle](https://github.com/rsdn/nemerle) for .NET 10, with
[Nitra](https://github.com/rsdn/nitra) integrated as `grammar`/`space`, file modules, scripting and a language server.

## License of this fork

The fork as a whole, and every change made in it, is distributed under the **GNU General Public License,
version 2 or (at your option) any later version** (`GPL-2.0-or-later`). The full text is in [LICENSE](LICENSE).

Copyright (C) 2026 azelcalt and the contributors of this fork.

## Original work (BSD-3-Clause, notices kept)

The code this fork is built on remains under its original BSD-style licenses. Their notices are kept unchanged
and must stay with that code:

- **Nemerle**: Copyright (c) 2003-2008 The University of Wroclaw, Copyright (c) 2008-2014 Nemerle Project Team.
  See [COPYRIGHT](COPYRIGHT) and [License.rtf](License.rtf); the original authors are listed in [AUTHORS](AUTHORS).
- **Nitra** (`native-nitra/upstream`): Copyright (c) 2014 JetBrains s.r.o. See
  [native-nitra/upstream/License.txt](native-nitra/upstream/License.txt).

As those licenses require, the names of the University of Wroclaw and of JetBrains are not used to endorse or
promote this fork. Neither the original Nemerle team nor JetBrains is responsible for it; all errors here are ours.

## Third-party components shipped with the toolchain

| Component | License | Where |
|---|---|---|
| Mono.Cecil | MIT | `boot/coreclr/Mono.Cecil-LICENSE.txt` |
| .NET reference assemblies and runtime pieces | MIT | `boot/coreclr/Dotnet-LICENSE.txt`, `Dotnet-ThirdPartyNotices.txt` |
| NuGet client libraries (optional scripting adapter) | Apache-2.0 | `scripting-nuget/THIRD-PARTY-NOTICES.txt` |
| Newtonsoft.Json | MIT | `scripting-nuget/THIRD-PARTY-NOTICES.txt` |

Apache-2.0 is not compatible with GPL version 2 alone; the NuGet scripting adapter is therefore distributed under
the terms of GPL version 3, which `GPL-2.0-or-later` permits.

## Thanks

To Michal Moskal, Kamil Skalski, Pawel Olszta and everyone in [AUTHORS](AUTHORS) who created Nemerle at the
University of Wroclaw; to the RSDN community who carried it on; and to the Nitra team at JetBrains. This fork exists because their work was good enough to bring back.
