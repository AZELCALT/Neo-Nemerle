# CoreCLR backend result

The fork now has a working .NET 10/CoreCLR toolchain, alongside the Mono
bootstrap path. Language typing, expressions, macros and file/mask semantics
remain in Nemerle. Runtime-specific implementation lives in Nemerle.Platform.
No Nemerle license or copyright notices were changed.

## What changed

- `ClrAssemblySession`: owns assembly/module creation, runnable versus persisted
  output, entry points, resources and executable access. Modern output uses
  PersistedAssemblyBuilder and ManagedPEBuilder. Executables get a runtimeconfig.
- `ClrAssemblyLoader` / `ClrLibrarySession`: explicit reference paths load in a
  compilation-owned context, sharing compiler/runtime/framework identities.
  A same-named DLL beside the host no longer replaces a requested macro DLL.
- `ClrSigning`: reads signing key files without constructing StrongNameKeyPair
  on CoreCLR. Saved metadata is signed through Cecil. Friend-access public-key
  checking uses the same adapter and correctly parses PublicKey/PublicKeyToken.
- `ClrTargetReferences`: binds implementation type references to the supplied
  public reference contracts. Normal SDK C# consumers can compile against output
  without referencing System.Private.CoreLib. No SDK-layout discovery in ncc.
- Old permission requests and declarative-security emission are isolated to the
  legacy backend; modern source builds exclude their types and calls.
- Builder token access goes through the adapter; removed MethodToken/FieldToken
  structures are no longer dependencies of compiler IL generation.
- Source calls with newly ambiguous BCL overloads use explicit common signatures.
  Unsupported struct+Enum generic overloads are filtered without poisoning the
  existing Enum APIs; this does not add enum-generic language semantics.
- The Resource macro uses a portable XML reader on CoreCLR rather than WinForms.
  Strings, invariant type converters, byte arrays, explicit nulls, and string/byte
  file references with declared encodings work. The wrapper handles array types.
  Legacy serialized binary/SOAP objects remain unsupported.
- Portable PDBs retain documents, sequence points, scopes and local names through
  metadata repair and signing. `-debug` enables them for persisted output.
- Native resource-compiler `.res` containers are converted to PE resource sections
  without Windows APIs, preserving named/numeric identifiers and language IDs.

## Use the workspace toolchain

(The installed `toolchain/coreclr` predates branch lang/file-modules. Compilers built from that branch treat every file as a
module and reject `-file-modules`; drop the flag there.)

From the workspace root:

```sh
toolchain/coreclr/ncc -file-modules -source-root:src \
  src/alpha.n src/beta.n -target:library -out:game.dll
```

The launcher runs `dotnet ncc.exe` and supplies the bundled .NET 10 reference
contracts. Running this compiler requires the .NET 10 runtime, not Mono or SDK
installation-layout discovery. Rebuilding the C# adapter and C# test consumers
requires the SDK. Existing Nemerle syntax is still accepted in legacy mode when
`-file-modules` is omitted.

Direct use accepts explicit contracts:

```sh
dotnet toolchain/coreclr/ncc.exe -target-references:toolchain/coreclr/references \
  -file-modules -source-root:src src/example.n -target:library -out:example.dll
```

A DLL consumed by a C# project needs the normal Nemerle runtime dependency when
its exported code/types use Nemerle library facilities. File and mask usage is
covered in `FILE-MODULE-RESULT.md`.

## Reproduce

1. Build the Mono bootstrap with `build-first-slice.py --runtime` and
   `build-file-toolchain.py --bootstrap PRINTED_DIRECTORY`.
2. `probe-coreclr.py --compiler MONO_STAGE --support MONO_STAGE` builds the modern
   platform offline and tests the actual compiler, macro compilation/expansion,
   C# consumption, signing, in-memory hosting and saved executable execution.
3. `build-coreclr-toolchain.py --bootstrap PRINTED_CORE_DIRECTORY --references
   TARGET_REF_DIRECTORY` rebuilds the compiler, then runtime, compiler again,
   standard macros and CLI entirely under CoreCLR; each output is signed.
4. Run `check-file-modules.py CORE_STAGE/ncc.exe --runtime dotnet
   --target-references TARGET_REF_DIRECTORY` for the full module suite.
5. `nemerle/platform/tests/run-checks.py` verifies both platform implementations.
6. `check-coreclr-debug-resources.py --toolchain CORE_STAGE --references
   TARGET_REF_DIRECTORY` checks signed compiler output, actual source stack traces,
   named locals, generated Resource properties, native resources and release rebuilds.

The initial transition uses a Mono-built compiler DLL executing under CoreCLR.
The final CoreCLR compiler/runtime/macros/CLI are rebuilt from source on CoreCLR.
The SDK is discovered by the offline build/test scripts, not the compiler backend.
Cecil resolution uses explicit directories instead of the old GAC assumptions.

## Verification (2026-10-08)

The compiler/runtime/CLI were source-built in
`/tmp/nemerle-core-selfbuild-4_rznxrp/stage2`; the modern adapter was rebuilt in
`/tmp/nemerle-coreclr-7f3xc43x` and standard macros were refreshed in
`/tmp/nemerle-symbol-macros`. Their usable binaries and reference contracts are
in `toolchain/coreclr`.
Verified with .NET SDK 10.0.112 and runtime/reference contracts 10.0.12:

- Compiler source build, runtime source build, compiler self-build, standard
  macro source build and CLI source build all passed on CoreCLR; signatures pass.
- Real compiler tests passed for C# consumption, macro compilation/expansion,
  in-memory hosting, saved executable execution and generated runtimeconfig.
- The full file-module suite passed on the final source-built CoreCLR compiler:
  reverse order/mutual types, masks, privacy, imports, names, generic arities,
  DLL reuse, source precedence, syntax macros and definition-site helper capture.
- Rebuilt runtime C# checks passed for collections, private generic interface
  implementation and self-applied constructor-parameter attributes.
- Platform tests passed on Mono and .NET 10, including signing and resource data.
- Final Mono compiler self-build and 22 upstream regression fixtures also passed.
- A runtime-only dotnet host reporting an empty SDK list compiled the sample
  using bundled contracts. Reproduce: `python3 tests/check-runtime-only.py`.
- Signed debug output retained source lines, local names and the correct PDB
  reference; an actual exception stack trace reported `debug.n:line 10`.
- Generated Resource macro properties returned encoded text, integers, byte arrays
  and nulls. Native numeric/named resources and payloads survived signing.
- Rebuilding debug output without `-debug` removed stale PDBs.
- The full file-module suite passed again with the refreshed macros and adapter.
- See `DEBUG-RESOURCE-RESULT.md` for this follow-up's exact scope.

Evidence is retained in `baseline/coreclr-verification/`. This is a working
CoreCLR compiler result, not merely isolated adapter tests.

## Current limits

This targets .NET 10 on the tested Linux machine. Public contracts must match
host runtime major version; independent cross-version targeting is not implemented.
The frontend still imports runtime metadata rather than a complete independent
metadata-only target universe. Contract rebinding does not establish arbitrary
cross-framework compatibility.

Portable PDBs work for persisted output; debug compilation directly to runnable
in-memory assemblies remains unsupported. Linked resources are explicitly rejected:
CoreCLR does not load external resource-file manifest entries. Use embedded resources.
Legacy binary/SOAP object resources and arbitrary typed file references remain
unsupported. Native `.res` input works; automatic default Win32 version resources
remain omitted, while assembly version attributes remain. Declarative security/CAS has no
modern equivalent here. Ref-return, stack-only and struct+Enum signatures remain
outside the legacy frontend's supported subset.

Script-session APIs, collectible script lifetime, IDE tooling and engine/native
allocation/thread contracts remain separate work. The whole upstream suite and
other operating systems/runtime versions have not been verified.
