# Kotlin scripting facility comparison

The baseline is the installed **Kotlin 2.4.20** distribution under
`/usr/share/kotlin/lib`, with its common scripting API, JVM host and `main-kts`.
The executable comparison uses those jars without mixing Gradle's Kotlin 2.4.10
copies or fetching dependencies. Exact jar SHA-256 hashes and the compiler/JRE
version are retained in `baseline/coreclr-verification/scripting-composition-kotlin.log`.
The Nemerle comparison runs on .NET 10 through the source-built compiler.

This is a host-facility comparison. It does not equate Kotlin and Nemerle language
semantics, their standard libraries or JVM and CLR capabilities. Kotlin compiler
plugins, Gradle adapters and IDE integration are outside this comparison.

| Kotlin common/main-kts facility | Nemerle facility | Evidence or deliberate difference |
| --- | --- | --- |
| `displayName` | `ScriptDefinition.DisplayName` | Definition label; no IDE adapter |
| `defaultIdentifier` / source name | `ScriptSource.Path`, file owner | Nemerle requires a source path and derives qualification from its filename |
| `fileExtension`, `filePathPattern` | `FileExtension`, regex `FilePathPattern`, registry | Longest suffix, specific matching pattern, explicit definition wins; path selection tests |
| `baseClass` | `BaseType` | Typed base contracts and inherited members tested |
| `implicitReceivers` | `ReceiverTypes`, `ScriptInputs.Receivers` | Ordered receiver resolution and overload/precedence tests; paired Kotlin host fixture |
| `providedProperties` | `Properties`, `ScriptInputs.Properties` | CLR type and object identity, typed/null values, missing/extra/type checks; paired host fixture |
| `constructorArgs` | `BaseArgumentTypes`, `BaseArguments` | Normal Nemerle/CLR base constructor invocation tested |
| `scriptFileLocationVariable` / location | `FileLocationProperty` | Supplied string path; Kotlin supplies a JVM `File` |
| `defaultImports` | `Imports`, `Aliases`, normal `using` | Existing module/alias tests; no Kotlin package model substituted |
| `importScripts`, main-kts `Import` | `ImportScripts`, literal assembly `Import`, source resolver | Typed child instances, cycles/duplicates, selected definitions, input inheritance, source/CLR collision and diamond tests |
| Opening imported script names | Explicit file qualification or `using` | Deliberate Nemerle file/mask lookup: acquisition alone does not open members |
| `resultField` | Default result plus optional `ResultField` / `ResultType` | Named CLR field needs an explicit host type; value/null/void/error and disabled-capture tests |
| `dependencies`, main-kts `DependsOn` / `Repository` | Explicit DLLs and optional NuGet resolver | Exact roots, transitive constraints, lock/integrity/offline/native/macro tests; .NET assets replace JVM Maven artifacts |
| `compilerOptions`, main-kts `CompilerOptions` | Definition options / literal assembly metadata | Existing Nemerle option parser; attached defines/diagnostic/optimization/checked options; host-controlled modes rejected |
| Before parsing refinement | Existing `IScriptConfigurationRefiner.BeforeParsing` | Compatibility and snapshot tests |
| Annotation refinement | `IScriptCompilationRefiner.OnAnnotations` | Filtered literal metadata with locations, no CLR attribute construction; paired Kotlin host fixture |
| Before compiling refinement | `IScriptCompilationRefiner.BeforeCompiling` | Final definition before dependency linking/full parsing; paired fixture |
| `sourceFragments` | Character-range `SourceFragments` | Excluded text is blanked, original offsets/lines retained; selection and PDB tests |
| Host configuration | `ScriptHostOptions`, definition snapshots | Compiler services remain optional; no SDK process at execution |
| `isStandalone` | CLI source/AOT execution or embedded API | Same compilation model; no standalone-only source dialect |
| Previous snippets | `ScriptSession` typed predecessor inputs | Generic aliases/types, overloads, closures, masks/imports, shadowing and failure tests |
| Sharing imported instances | Root graph sharing / optional branch separation | Paired Kotlin main-kts diamond: one initialization and result 3; Nemerle fresh/shared/separate/session tests |
| Evaluation refinement | `IScriptEvaluationRefiner.BeforeEvaluate` | Snapshot then full typed validation; paired Kotlin fixture |
| Execution wrapper | `IScriptExecutionWrapper` | Constructor and execution thunk, repeated calls rejected; paired Kotlin fixture |
| Compile then evaluate later | `Compile`, `Save`, `Load`, `Evaluate` | Relocated graph bundle and compiler-free evaluation tests; descriptor v3 reads v1/v2 |
| Interactive incomplete input | Parse-only `ClassifyInput` and CLI accumulation | Complete/incomplete/invalid, unfinished expressions/brackets, closed malformed expressions, automatic/manual multiline tests |
| Persistent sessions/history | Source/config/dependency history and explicit replay | Nonexecuting reads; inputs supplied again; incompatible configuration/dependencies rejected before affected execution |
| Compiled artifact reuse | Bounded graph-aware artifact cache | Imported changes invalidate, hashes checked, dependencies bundled, input values excluded |
| Callable exports | Bound delegate APIs, explicit generic arguments | CLR delegate signature/constraint checks; normal source calls still use Nemerle inference |
| Host-defined source additions / interfaces | Separately located `Preludes`, `Interfaces` | Existing AST and normal CLR interface implementation, portable PDB and generic contract tests |

## Running the comparison

From the workspace root:

```sh
python3 baseline/check-kotlin-scripting-comparison.py
python3 tests/check-scripting.py --toolchain toolchain/coreclr --references toolchain/coreclr/references
python3 tests/check-scripting-nuget.py --toolchain toolchain/coreclr --references toolchain/coreclr/references
```

`HostChecks.kt` exercises Kotlin bindings, receivers, a named result, all three
compilation refinement stages, evaluation refinement and the execution wrapper.
The `*.main.kts` fixtures exercise diamond sharing and fresh independent runs.
`ScriptingChecks.cs` contains the corresponding Nemerle behavior tests and the
CLR-specific composition, persistence, generic, mask and debug checks. The test
reports, rather than an unrestricted parity claim, define what was verified.

Nemerle keeps its own type inference, overload rules, macros and file ownership.
Macros transform compile-time syntax; runtime loading uses compiled assemblies.
CLR input objects cannot be reconstructed from history or a compiled cache, and
retained delegates can keep script instances alive. Reset/disposal drops owned
references without promising physical assembly unloading. Cancellation does not
interrupt arbitrary executing CLR code. These remain ordinary platform/language
constraints, not a second script subsystem.
