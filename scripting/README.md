# Nemerle scripts

This optional library compiles ordinary Nemerle syntax with the existing compiler,
macros and CLR backend. Script mode adds a generated instance for supplied inputs,
script fields and execution. It does not introduce an interpreter or another language.

The .NET 10 toolchain includes `Nemerle.Scripting.dll` and `nscript`. A script is a `.ns` file (as Kotlin's are
`.kts`); `nscript` runs a plain `.n` file the same way, for running ordinary Nemerle directly. A kind's extension
(`[ScriptDefinition(".build.n")]`) matches both `x.build.ns` and `x.build.n`.

```sh
./toolchain/coreclr/nscript run demo.ns -- first second
./toolchain/coreclr/nscript compile demo.ns demo.dll
./toolchain/coreclr/nscript run-compiled demo.dll -- first second
```

Standalone scripts receive `args : array[string]`. For example, `demo.ns` can contain:

```nemerle
using System;
mutable calls : int = 0;
mask math {
  Double(n : int) : int { calls = calls + 1; n * 2 }
}
demo.math.Double(args.Length + 19)
```

Compilation produces a library, optional portable PDB and `demo.dll.script`
descriptor. Keep the descriptor with the assembly; keep the PDB for source locations
in exception stacks. `run-compiled` needs the CLR runtime, Nemerle runtime,
platform adapter and scripting library. It does not need the compiler, macros or
SDK reference assemblies. Running source additionally needs the compiler, macros
and their dependencies. Bundled `references/` supplies the target CLR contracts.

## Embedded API

The library itself uses file modules. C# can import the nested public types with
`using static`; Nemerle can import their file owners with `using`.

```csharp
using static Nemerle.Scripting.contracts;
using static Nemerle.Scripting.host;

var host = new ScriptHost();
var definition = new ScriptDefinition();
definition.Properties.Add("counter", typeof(Counter));
definition.TargetReferenceDirectory = targetReferences;

var compilation = host.Compile(new ScriptSource(
    "mask math { Double(n : int) : int { counter.Add(n * 2) } }\n" +
    "demo.math.Double(21)\n", "demo.n"), definition);
if (!compilation.Success) {
    foreach (var diagnostic in compilation.Diagnostics)
        Console.Error.WriteLine($"{diagnostic.File}:{diagnostic.Line}: {diagnostic.Message}");
    return;
}

var inputs = new ScriptInputs();
inputs.Properties.Add("counter", counter);
var evaluation = host.Evaluate(compilation.Script, inputs);
if (evaluation.Kind == ScriptResultKind.Error) throw evaluation.Error;
var twice = (Func<int, int>)evaluation.GetFunction("demo.math.Double", typeof(Func<int, int>));
Console.WriteLine(twice(2));

host.Save(compilation.Script, "demo.dll");
var loaded = host.Load("demo.dll", definition);
var another = host.Evaluate(loaded, inputs);
```

`Counter` is an ordinary host type. Typed supplied properties are read-only script
fields; the referenced host objects retain their identities. Evaluation checks
missing, extra and wrongly typed inputs before constructing the script.
Compilation snapshots the definition, so later changes to the original
configuration do not change an existing artifact.

`ScriptDefinition` also accepts default `Imports`, explicit assembly `References`,
actual `SharedAssemblies`, `BaseType`, `BaseArgumentTypes`, ordered `ReceiverTypes`
and `Debug`. `ScriptInputs` supplies matching `BaseArguments` and `Receivers`.
Receiver types are configured outer to inner. The nearest applicable receiver wins;
overload selection within a receiver uses the existing Nemerle rules. Script and
inherited members precede receivers. Supplied property, receiver, base and generic
argument assemblies are automatically shared with their actual host identities.
Additional dependencies and macro assemblies use explicit references.

A loaded artifact is checked against the supplied definition's property, receiver
and base schemas. This lets a host relocate its explicit reference paths when
loading. The versioned descriptor includes a hash of the assembly, its generated
evaluation method and its public function map. Artifact identities are unique;
loading a new artifact does not replace an earlier script or its bound delegates.

## State, masks and results

Each `Evaluate` constructs a fresh script instance. Inputs are assigned before
script initializers and statements execute in source order. Script field
syntax is ordinary Nemerle, such as `mutable count : int = 0;`. A top-level `def`
becomes an inferred immutable field on the script instance, including tuple and
variant-pattern bindings. Declared methods can use these bindings. Nested `def`
bindings remain lexical locals, which lambdas can capture. Explicit `static` declarations keep their
ordinary Nemerle semantics.

Masks qualify names and filter lookup. Their functions share the same script
instance as unmasked functions. They do not create separate runtime state or
per-mask receiver objects. Masked types retain CLR type grouping. File
qualification uses the source filename without its extension, so `demo.math.Double`
refers to the example above. The filename must be an identifier. Imports remain
local to the source, and normal local-variable shadowing and macro hygiene apply.
Private functions are absent from the host function map and remain inaccessible
outside their source scope.

`GetFunction(qualifiedName, delegateType)` checks the delegate signature and binds
an exported instance method to that evaluation's instance. Static exports bind as
ordinary static delegates. There is no global current script. A constructor that
fails does not yield an instance for function binding.

`EvaluationResult.Kind` distinguishes `Value`, `Void` and `Error`. A successful
`Value` can be null; `ValueType` preserves its declared CLR type. A `Void` result
has `typeof(void)`. An `Error` retains the underlying user exception rather than
its reflection invocation wrapper. Syntax and type inference remain Nemerle's;
use an annotation such as `42 : int` when an exact numeric result type matters.
Debug builds and saved PDBs retain original source locations.

Compilation errors return positioned `ScriptDiagnostic` values and no artifact.
Invalid host configurations and input schemas throw argument exceptions. Compiler
use through this API is serialized and restores `ManagerClass.Instance` on success
and failure. This does not make unrelated direct compiler-manager use concurrent.

Contracts support closed managed types, one-dimensional arrays and closed nested
generic types. Pointer/by-reference/open generic contracts are rejected.
`GetFunction(name, delegateType, genericArguments)` closes a generic export with
explicit CLR type arguments and checks its constraints and delegate signature;
the original two-argument overload remains available.
REPL sessions, persistent source history, dependency resolution and compiled artifact
caching are described below. Physical unloading is not guaranteed.

## Build and checks

From the workspace root, with a working source-built .NET 10 toolchain:

```sh
python3 build/build-scripting.py --toolchain toolchain/coreclr --references toolchain/coreclr/references
python3 tests/check-scripting.py --toolchain toolchain/coreclr --references toolchain/coreclr/references
```

The checks exercise embedded compilation/evaluation, source order, supplied-object
identity, bound delegates, fresh state, masks/privacy, local shadowing, classes,
closures, declaration macros, base constructors, receiver ordering/applicability,
imports, null/void/errors, failure recovery, original PDB source locations, saved
artifacts and all CLI paths. Artifact execution is also tested with the compiler,
macros and SDK reference assemblies absent from the execution directory.

## REPL sessions and history

`Nemerle.Scripting.session.ScriptSession` uses the same compiler and evaluator.
Later submissions receive typed references to earlier instances. They do not
reexecute earlier statements. Public declarations, generic types/type aliases, overloaded functions, closures,
masks, source imports, ordinary imports and qualified aliases remain available.
Imported instances remain alive in a shared session graph. Replacing an imported
source/configuration requires `Reset`; changed dependencies are rejected before
execution. New declarations shadow earlier
ones; earlier functions and closures keep their original bindings. Successful
expression results are available as `resN`, where N is the submission index.

```csharp
using static Nemerle.Scripting.session;
using var session = new ScriptSession(host, definition, inputs);
var first = session.Submit(new ScriptSource(
    "mutable count : int = 0; Inc() : int { count = count + 1; count }\n",
    "state.n"));
var next = await session.SubmitAsync(new ScriptSource("state.Inc()\n", "next.n"),
    CancellationToken.None);
session.SaveHistory("session.history");
```

`History` contains successful sources; `HistoryEntries` also records effective
configuration/dependency fingerprints. `ReadHistory`/`ReadHistoryEntries` read data
without running code, even if the current configuration differs. `ReplayHistory`
validates the saved configuration before resetting, then explicitly rebuilds a
saved chain, checking dependency fingerprints; `Replay(sources)` executes an explicit source
list. Host input objects must be supplied again. History does not serialize CLR
objects. Replay can repeat side effects.

Compilation failure changes no live session state. A runtime failure contributes
no declarations/history entry, but cannot undo mutations to earlier instances or
host objects. `Reset` drops visible declarations; `Dispose` releases owned references.
Caller-retained results/delegates can keep earlier instances alive. Session calls
are serialized; compiler access remains serialized across hosts.

```sh
./toolchain/coreclr/nscript repl --cache-dir ./script-cache
```

The CLI uses parse-only Complete/Incomplete/Invalid classification to collect
unfinished brackets, comments, multiline strings and trailing expressions
automatically. It performs no evaluation during this check.
Use `:begin` and `:end` for an explicit multiline submission, `:history` to list stored source,
`:recall N` to display an entry, `:replay` to execute saved history, `:reset` to clear
live declarations, and `:quit` to exit. Opening a REPL never automatically replays
history. `--history PATH` selects its file. The CLI defaults to a Nemerle directory
under the platform's local application data directory.

## Dependencies and host configuration

Literal assembly attributes are script metadata, collected with Nemerle's lexer
before full parsing. Ordinary attributes continue through the ordinary compiler.
No new keyword or interpreter is introduced.

```nemerle
[assembly: Repository("https://api.nuget.org/v3/index.json")]
[assembly: DependsOn("Example.Package", "1.2.3")]
[assembly: DependsOn("relative-library.dll")]
using Example;
Run()
```

An assembly path resolves relative to the source file. Package roots require exact
versions. `ScriptDefinition.Packages` and `Repositories` provide the same host-side
configuration. `TargetFramework` defaults to `net10.0`; `RuntimeIdentifier` defaults
to the executing CLR's RID. Dependency assembly identity/content conflicts are
reported before execution. A live session cannot replace earlier dependency versions.

The optional `Nemerle.Scripting.NuGet.dll` implements
`Nemerle.Scripting.dependencies.IScriptDependencyResolver`. It selects compatible
compile/runtime assets and transitive versions, records content hashes in a lock,
and resolves native assets through the bundled portable RID graph. Selected
extracted assets are checked against the pinned package archive. Configure
`NuGetScriptResolver(cacheDirectory, feeds)` on `ScriptHostOptions.Resolver`.
`Offline` allows only available cache/local-feed contents; `UpdateLock` explicitly
re-resolves a graph. No SDK or MSBuild process is invoked at runtime. Package build
scripts, analyzers and MSBuild targets are not executed.

The CLI loads this adapter when present. It accepts `--package ID VERSION`,
`--repository FEED`, `--offline`, `--update-lock`, `--target-framework TFM`, and
`--runtime RID`. The standard adapter's default feed is NuGet's public v3 feed.
Saved version-three artifacts include source identity, result metadata, hashes,
binding/member metadata, diagnostics and the complete imported script graph.
A `.dll.dependencies/` directory bundles imported assemblies/descriptors and
explicit managed/native dependencies.
Keep that directory with the DLL and descriptor when relocating an artifact.
Version-one and version-two descriptors remain readable.

`ScriptHostOptions.Refiners` accepts `IScriptConfigurationRefiner` implementations
with `BeforeParsing` and `OnDependencies` callbacks. They receive snapshots and
return effective definitions; `ScriptDependencyException` reports a positioned
failure. A refiner's `Version` must identify its behavior for caching; an empty version
bypasses the compiled cache. Compiler phases and macro expansion remain Nemerle's.

`IScriptDefinitionSelector` and `ScriptDefinitionRegistry` select definitions by
extension and optional `FilePathPattern` regular expressions. The longest
registered suffix wins; a matching path pattern takes precedence at the same
suffix. Ambiguous matching patterns are rejected. `DisplayName` labels a definition. Use `Compile(source)` for
selection or pass a definition explicitly. Each definition has `Id`, `Version`,
`FileExtension`, typed inputs, imports/aliases, base/receiver configuration and
explicit references. A custom suffix is removed when deriving file qualification.

## Script kinds declared by libraries

As with Kotlin's `@KotlinScript` definitions, a library can declare a **script kind**. Every script whose file name ends
with the kind's extension is compiled as that kind, so it needs no setup lines:

```nemerle
// buildkind.n, compiled to buildkind.dll (references Nemerle.Scripting.dll)
using Nemerle.Scripting.kinds;

[ScriptDefinition(".build.n", DisplayName = "Build script", Imports = array["System.Console", "buildkind"])]
public class BuildScript
{
  public Target : string { get { "release" } }
  public Log(message : string) : void { System.Console.WriteLine("[build] " + message) }
}
```

```nemerle
// deploy.build.n
Log("target " + Target);          // members of the kind's base class
WriteLine(space Steps { copy });   // the library's grammar, through its continuation section
```

- The annotated class is the scripts' **base class**. A static module only configures and is not a base class.
- `Imports` are opened in every script of the kind, and `DisplayName` labels the definition.
- The **library** is a reference of every script of the kind. Its grammars, macros and the helpers those macros use
  come with it (see `doc/CONTINUATION.md`).
- An optional `public static Configure(definition : ScriptDefinition) : void` on the class refines the rest, as a
  Kotlin compilation configuration does: receivers, properties, packages, compiler options.

`nscript` looks for kinds in the dlls of its own directory, of every directory in `NEMERLE_SCRIPT_PATH` and of the
script's directory. It reads only their metadata, and loads a library only when a script of its kind runs. The longest
matching extension wins, and the default definition handles everything else. A file named like a kind that no library
declares is reported, together with the directories that were searched. Embedded hosts use `ScriptKinds.Find`,
`ScriptKinds.Definition` and `ScriptKinds.Register` with a `ScriptDefinitionRegistry`.

## Source-script composition

Acquiring a script and opening its names are separate operations:

```nemerle
[assembly: Import("math.n")]
math.nested.Double(21)
```

`ScriptDefinition.ImportScripts` provides the same facility from the host.
`math.nested.Double` is qualified through the imported file owner and mask.
Use `using math;` to omit the file owner, or `using math.nested;` to open that
mask explicitly. `using M = math.nested;` permits `M.Double(21)`. Importing a
source alone does not open its functions. Private declarations stay private;
ambiguous opened names are errors and local declarations retain precedence.
Importing types uses the same file qualification and normal Nemerle type syntax.
Known source types resolve before competing CLR types and their overloads;
qualified paths absent from the source can still resolve through CLR namespaces.

Paths resolve relative to the importing source. `IScriptSourceResolver` can replace
filesystem acquisition; its `Version` participates in cache identity. Imported
scripts use the configured definition selector, or inherit the root host's input
contracts when no selector is configured. Their file owners stay independent of
the generated CLR class names. Duplicate direct imports and cycles produce source
locations; importing different files with the same owner is an ambiguity error.

Dependencies compile before their importers. A diamond shares one compiled child
for the same source/configuration. Evaluation initializes it once per root graph;
a second `Evaluate` creates fresh instance state. Set
`ShareImportedInstances = false` to create separate instances per import branch.
Matching supplied properties are inherited. `IScriptImportedInputProvider` can
supply a child's properties, receivers and base arguments explicitly. The host
validates the entire graph before any script constructor executes.

`Save` bundles the graph for relocated, compiler-free execution. Imported scripts
are ordinary compiled Nemerle instances passed as typed constructor inputs, using
the same mechanism as previous REPL submissions. Masks continue to filter lookup;
they do not introduce another runtime object or evaluator.

## Additional configuration and execution facilities

Public optional interfaces live in `Nemerle.Scripting.facilities`:

- `IScriptCompilationRefiner` adds annotation-filtered `OnAnnotations` and
  `BeforeCompiling` callbacks. Register it in `CompilationRefiners`. Annotation
  arguments are literal strings with original source locations, collected without
  constructing CLR attributes. `OriginalSource` retains original text; `Source`
  contains metadata-masked compiler input. Existing `Refiners` continue to work.
- `IScriptEvaluationRefiner` receives a `ScriptEvaluationContext` and returns
  an input snapshot before validation. Register it in `EvaluationRefiners`.
- `IScriptExecutionWrapper` surrounds initialization and execution through a
  thunk. Each thunk can execute once, including under concurrent calls. The context
  contains the compiled script, original source, definition and an input snapshot.

`CompilerOptions` and literal `[assembly: CompilerOptions("-checked+", "-warn:4")]`
use Nemerle's option parser. Supported options control defines, warnings, checked
arithmetic and optimization. Use attached option values. References, output paths,
sources, signing, targets and compilation modes remain host-controlled.

`FileLocationProperty` binds the source path as a supplied string.
`CaptureResult = false` executes the final expression and reports Void.
`ResultField` with `ResultType` exposes the captured result in a named typed field;
ordinary result capture remains the default. Configured `Interfaces` are emitted
as normal CLR interfaces, implemented by ordinary Nemerle declarations.

`SourceFragments` selects ranges by character offset/length; excluded characters
are blanked while preserving line numbers. Finalize fragments in `BeforeParsing`;
later fragment changes are rejected. `Preludes` adds separately located host AST
sources before user statements. Prelude syntax and macros use the same parser;
configure their dependencies through the definition. Portable PDBs retain both
source identities. No persistence keyword or additional script language is needed.

The tested Kotlin baseline and deliberate differences are recorded in
[`KOTLIN-FACILITIES.md`](KOTLIN-FACILITIES.md).

## Compiled artifact caching and cancellation

Set `ScriptHostOptions.Cache` to a `FileScriptArtifactCache(directory, maximumBytes)`
to opt in from an embedded host. The CLI enables a bounded compiled cache by default;
`--no-cache` disables it and `--cache-dir` selects storage. Package and compiled
artifact caches are separate.

Keys include source content/path, effective configuration, target contracts,
compiler/platform/runtime identity, referenced/macro/native content and previous
submission schemas, imported source/configuration graphs, source fragments,
preludes, compiler options, result contracts and hook versions. Runtime input values and live instances are never cached.
Loading a hit shares the current host and predecessor assemblies. Corrupt artifacts
are invalidated and rebuilt. Publication uses a temporary directory and atomic
rename; artifacts larger than the configured limit are not stored.

Set `ScriptDefinition.Cacheable = false` for macros/configuration that depend on
untracked external state or require compile-time side effects on every compile.
Caching skips compiler/macro execution on a hit. Explicit static declarations keep
ordinary CLR static lifetimes; fresh evaluation applies to instance state.

`CompileAsync`, `CompileAndEvaluateAsync` and `SubmitAsync` accept a
`CancellationToken`. Cancellation reaches package operations and is checked around
compiler execution and before evaluation. It does not interrupt an executing CLR
script or an already-running compiler phase. Evaluation inputs stay separate from
compilation configuration.

## Optional NuGet adapter build

```sh
python3 build/build-scripting-nuget.py --toolchain toolchain/coreclr \
  --references toolchain/coreclr/references \
  --nuget-libraries /usr/share/dotnet/sdk/10.0.112
python3 tests/check-scripting-nuget.py --toolchain toolchain/coreclr \
  --references toolchain/coreclr/references
```

The offline build verifies hashes in `scripting-nuget/client-libraries.lock.json`
and distributes the needed libraries beside the adapter. The current input pin is
NuGet client 7.0.3-rc.65534 from SDK 10.0.112; changing that dependency requires an
explicit lock update and adapter verification. This build input does not create a
runtime SDK dependency. Third-party notices accompany the optional adapter.
The checks use local packages and offline locks. A loopback HTTP v3 test is
available, but is skipped when the environment disallows sockets. The user-run
`baseline/coreclr-verification/http-fetch-user.log` verifies both that fixture and
a fresh public HTTPS download with successful script execution.

To verify HTTP outside the sandbox, run from the workspace root:

```sh
python3 baseline/test-http-fetch.py
```

This requires the loopback HTTP fixture to pass, then downloads Newtonsoft.Json
13.0.3 from the public HTTPS feed into a fresh temporary cache and executes a script
using it. Output and failures are recorded in
`baseline/coreclr-verification/http-fetch-user.log`. Use `--local-only` to omit the
public feed check. Unlike the general suite, this runner fails if HTTP is skipped.
