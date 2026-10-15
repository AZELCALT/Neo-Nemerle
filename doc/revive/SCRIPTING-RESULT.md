# CoreCLR scripting result

The approved core compile/load/evaluate plan and its API/history/cache/package
follow-up are implemented. The optional host is
Nemerle-authored and uses the existing parser, AST, macro phases, typer and backend.
The updated `toolchain/coreclr` distribution includes `Nemerle.Scripting.dll`,
`nscript.exe` and the `nscript` launcher.

Implemented and exercised:

- Separate compilation definitions and evaluation inputs, typed supplied properties,
  actual host-object/assembly identity, fresh script-local state per evaluation.
- Script constructor lowering with inputs before source-order initializers and
  statements. Existing initializer macros retain inference without also running
  relocated initializers before input assignment.
- File/mask qualification, private access, normal local shadowing, script and
  masked functions sharing one instance, instance-bound delegates and static exports.
- Ordinary classes, masked types/signatures, closures, properties, automatic
  property initialization and the existing Record declaration macro.
- Base constructor arguments/inherited members, default imports and outer-to-inner
  implicit receivers, including nearest applicable overloads and property precedence.
- Distinct value/null/void/error results, positioned compilation errors, recovery,
  compiler serialization and restoration of the previous compiler context.
- Unique artifact identities, versioned/schema-checked descriptors with assembly
  hashes, byte-loaded PE/PDB, original source lines in saved and loaded exception stacks.
- Source execution, ahead-of-time artifact compilation, artifact execution and
  artifact evaluation with compiler/macros/SDK reference assemblies absent.

No new source keyword or second scripting language was introduced. Generated
internal member names use a unique prefix. Top-level `def` bindings become inferred
immutable script-instance fields, including tuple/variant bindings and closures;
nested bindings retain their lexical meaning. Numeric inference
also remains Nemerle's rather than adopting Kotlin literal types.

Guide/API examples and explicit initial limitations:
[`nemerle/scripting/README.md`](../nemerle/scripting/README.md).
Persistent source history, package resolution and compiled caching are included.
Physical unloading is not guaranteed. Closed managed and nested generic contract
types are supported. Generic delegates can be bound with explicit type arguments;
normal source calls continue to use Nemerle inference.

The facilities follow-up additionally verifies:

- Definition selection, both refinement stages, snapshots and async cancellation.
- Typed previous-instance chaining, qualified declarations/types, retained imports
  and aliases, typed null results, shadowing, async submissions and failure recovery.
  Earlier-instance side effects survive a failed evaluation; its entry is not committed.
- Versioned source history and explicit replay. Sources remain readable when
  configuration changes; incompatible replay is rejected before execution.
- Bounded atomic compiled cache publication, cache hits, source invalidation,
  corrupt-artifact recovery and live host-input identity without caching input values.
- Literal package/assembly metadata, relative DLL references, transitive diamond
  resolution, conflict rejection, pinned offline reuse and extracted-asset integrity.
- Native assets with portable RID fallback and dependency-provided syntax macros.
- Saved v2 dependency bundles and relocated execution without the compiler,
  macro/compiler SDK contracts or NuGet adapter. Existing v1 descriptors remain readable.
- CLI multiline REPL, persistent source listing without automatic replay, and
  source/AOT/artifact paths.

The optional NuGet adapter pins client 7.0.3-rc.65534 from SDK 10.0.112 as verified
build inputs. Its distributed libraries and notices are bundled; runtime resolution
does not locate or invoke an SDK/MSBuild process. Local feeds and offline operation
were exercised. The user-run `http-fetch-user.log` additionally verifies HTTP v3
index/package requests, transitive dependency execution, and a fresh public HTTPS
download of Newtonsoft.Json 13.0.3 followed by script execution returning 42.
Socket creation is still blocked inside the agent sandbox. Package MSBuild
targets, analyzers and build scripts are deliberately outside the resolver contract.

Verification evidence is retained under `baseline/coreclr-verification/`:

- `scripting-selfbuild.log`: compiler/runtime/macros/CLI source rebuild and compiler self-hosting.
- `scripting.log`: public API, source/AOT/artifact CLI and runtime-only artifact execution.
- `scripting-file-modules.log`: existing module/mask/privacy/import/DLL/macro checks.
- `scripting-debug-resources.log`: existing portable PDB/signing/resources/stale-symbol checks.
- `scripting-runtime-compilation.log`: existing compiler-hosting/failure/coexistence checks.
- `scripting-platform.log`: platform adapter checks on Mono and CoreCLR.

Current follow-up evidence uses the `scripting-facilities-` prefix: `selfbuild`,
`host-build`, `scripting`, `nuget-build`, `nuget`, `modules`, `debug-resources`,
`runtime-compilation`, `runtime-only` and `platform`. The self-build includes
two compiler stages, the runtime, standard macros, CLI and strong-name validation.
`scripting-facilities-installed.log` additionally checks the installed launcher,
typed session bindings and explicit persisted replay. Shipped core/compiler/host
binary hashes match the verified build artifacts.

The source-text compiler and the scripting host require no Roslyn invocation or SDK
process at runtime. Roslyn is used only to build the C# test driver/platform adapter.

The refreshed CoreCLR distribution also passed `check-runtime-only.py`: no SDK was
visible to the host, and source compilation used bundled reference contracts
(`scripting-runtime-only.log`).

Mono compatibility: direct source compilation of the compiler and macros passed,
along with file-module checks and 22 selected upstream regressions. Evidence is
`scripting-mono-{compiler,macros,modules,legacy}.log`. The XBuild wrapper encountered
a read-only-filesystem error; direct compiler invocation avoided that wrapper and
verified the source changes. The existing Mono distribution was not replaced.

Known diagnostic limitation: debug script scaffolding can produce the compiler's
existing "missing debug location" warning. Original script exception line locations
were verified for freshly compiled and saved/loaded scripts. Unreachable-code and
ignored-value warnings retain ordinary Nemerle behavior.


## Kotlin-inspired composition and configuration follow-up

The approved facilities are implemented in the same compiler/instance model:
source imports and explicit using/aliases, typed dependency graphs, shared/fresh
initialization, selected child definitions and per-source input providers;
annotation/before-compiling and evaluation refinements; once-only execution
wrappers; compiler options, source-location binding, named/disabled results,
fragments, separately located preludes, CLR interfaces and generic delegate binding.

The REPL retains generic aliases/types, overloads, closures, masks/imports and
imported instances. Parse-only classification drives automatic multiline input.
Changed imports are rejected before execution. History remains nonexecuting data
until explicitly replayed; changed import fingerprints stop replay before effects.

Descriptor v3 bundles imported graphs and managed/native assets, verifies child
assembly/descriptor hashes and retains v1/v2 readers. Cache identity covers graphs,
fragments/options/results/hook versions; saved cache-hit graphs do not retain
transient compilation paths. Imported type paths bind to their physical CLR types
before overload lookup, preserving source precedence without combining unrelated
CLR overloads. Qualified CLR fallback remains available for absent source paths.

The pinned baseline is installed Kotlin 2.4.20. `check-kotlin-scripting-comparison.py`
records jar SHA-256 hashes and runs paired binding/receiver/result/refinement/
wrapper and shared/fresh diamond examples. The tested capability matrix and
language/platform differences are in `nemerle/scripting/KOTLIN-FACILITIES.md`.
No unrestricted Kotlin language or JVM feature parity is claimed.

Current evidence uses the `scripting-composition-` prefix: `selfbuild`,
`platform-build`, `host-build`, `nuget-build`, `scripting`, `nuget`, `modules`,
`debug-resources`, `runtime-compilation`, `runtime-only`, `platform`, `kotlin`,
`installed`, and the SHA-256 `distribution.json` manifest. The full source build
contains two compiler stages, runtime, standard macros, CLI and strong-name checks.
The final verified binaries are promoted to `toolchain/coreclr`.

HTTP socket tests remain skipped in the agent sandbox. The earlier user-run
HTTP/public-HTTPS evidence remains available; the HTTP resolver was not changed
in this follow-up. Licenses and third-party notices are unchanged.
