# File modules and masks

On branch lang/file-modules file modules are the only layout (see nemerle/doc/FILE-MODULES.md): `namespace` is an error
and `-legacy-namespaces` / `-file-modules` are gone. The compiler, runtime, macros and Nitra are file modules. Earlier:
opt-in `-file-modules` mode on Mono and .NET 10/CoreCLR (the commands below are for those toolchains). See
`CORECLR-RESULT.md` for the modern toolchain. No licenses or
copyright notices were changed.

## Use

From the workspace root, using the verified toolchain:

```sh
mono toolchain/mono/ncc.exe -file-modules -source-root:src \
  src/alpha.n src/beta.n -target:library -out:game.dll
```

`src/alpha.n` owns module `alpha`; `src/physics/body.n` owns `physics.body`.
Imports are file-local. Ordinary input files can appear in either order.
Namespaces and cross-file partial declarations are rejected in this mode.
File names and directory names must be valid identifiers (currently ASCII).
Paths outside the source root, duplicate identities and file/directory conflicts
are rejected. Moving a file changes its public module identity.

```nemerle
// alpha.n
mask math {
  Twice(value : int) : int { value * 2 }
  private Secret() : int { 7 }
}

// beta.n
using alpha;
Run() : int { math.Twice(3) }
```

File and mask members default to public; functions and fields are static.
Ordinary classes retain existing Nemerle instance/member semantics. Private
masks, types and members remain private through qualified references and DLL
consumption. C# can call `beta.Run()` and `alpha.math.Twice(3)` directly.

Directory imports do not open neighboring source files. External CLR namespaces
remain importable, including when a namespace shares a source directory's name.
A selected source file prevents fallback to foreign types or macros under the
same name. Generic arity overloads, properties, mutual type references and the
existing Record macro are covered by executable checks.

Macros may be declared at file level or inside masks. Compile their DLL first;
then reference it from consumers. Existing syntax-extension compilation stages
are preserved. Quoted helper names retain their defining file's scope when a
consumer declares a same-named helper.

## Verified result

On 2026-10-08 the complete runner passed using Mono 6.12.0 and xbuild 14.0.
Artifacts: `/tmp/nemerle-toolchain-ier7ibvh/stage3`; the usable compiler and
supporting assemblies are copied to `toolchain/mono`. The workspace copy also
compiled the alpha/beta sample successfully. Both file-level and mask-level
macro helper capture passed with competing helpers in the consuming file.
Retained evidence is in `baseline/file-module-verification/`.

## Rebuild and verify

```sh
python3 baseline/build-first-slice.py --runtime
python3 baseline/build-file-toolchain.py --bootstrap /tmp/nemerle-first-slice-PRINTED
```

The runner prints its artifact directory and retains separate logs. It rebuilds
runtime, compiler, standard macros and CLI; the next compiler is built with the
preceding source-built compiler. The transitional compiler stage disables XML
documentation because its bootstrap predates a runtime enumerator representation
change; the final stage enables documentation again.

It checks all four strong-name signatures, C# runtime consumption, in-memory
compiler hosting, saved execution, file-module fixtures and 22 selected upstream
positive/negative regressions. The full upstream suite is not covered.

Additional direct checks:

```sh
python3 tests/check-file-modules.py toolchain/mono/ncc.exe
python3 baseline/check-legacy-toolchain.py toolchain/mono/ncc.exe
python3 nemerle/platform/tests/run-checks.py
```

The original Mono toolchain remains available. A subsequently source-built
CoreCLR compiler is described in `CORECLR-RESULT.md`. Script
sessions, Kotlin syntax compatibility, engine allocation/thread integration,
IDE tooling and debug-symbol preservation remain future work.
