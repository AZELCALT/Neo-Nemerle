# CLR boundary result

Subsequent full CoreCLR compiler/toolchain results are in `CORECLR-RESULT.md`; earlier Mono-only limitations below describe the first boundary slice.

Validated on 2026-10-08 with Mono 6.12.0, xbuild 14.0, .NET SDK 10.0.112 and runtime/reference pack 10.0.12.

## Implemented

- `nemerle/platform/ClrEmission.cs`: compilation-local emission adapter; normalized method/field modifiers; explicit generated-attribute and override dependencies; deferred finalization; builder identity keys; managed dependency diagnostics.
- `nemerle/platform/ClrMetadata.cs`: exclude legacy-unsupported ref-return and stack-only signatures during member discovery, preserving ordinary ref parameters. This makes existing overloads usable without importing unrelated span overloads. It does not add span or ref-return language support.
- `nemerle/platform/ClrAttributes.cs`: retain generated attribute constructors, copied arguments, named members and target identities independently of Mono live emission. Persist self/cyclic annotations without forcing an impossible creation order.
- `nemerle/platform/MonoPersistence.cs`: serialize retained attributes and repair explicit generic override declarations symbolically after saving. Temporary Mono interface bridges and private method aliases are removed from final metadata. Re-sign with the original key pair.
- Compiler references, signature/field emission, attribute registration, finalization phases, member discovery and persistence now use the boundary. Nested enums finalize before their owners. The old runtime-type name guess is replaced with the actual runtime type representation.
- A null argument in `String.Split` is explicitly typed to avoid newer overload ambiguity. Build-task diagnostics without a source location no longer enter invalid-path parsing.

The boundary itself preserves legacy language behavior. A separate opt-in file-module mode now changes source namespace/import rules; see `FILE-MODULE-RESULT.md`. Scripting sessions remain unchanged. Engine sources are absent.

## Reproduce

From the workspace root:

```sh
python3 nemerle/platform/tests/run-checks.py
python3 baseline/build-first-slice.py
python3 baseline/build-first-slice.py --runtime
```

The first command compiles and runs adapter checks on both installed Mono and CoreCLR using local reference assemblies, without package restore. Both pass: saved methods and generic explicit interface implementations execute from C#; nonempty method/field modifiers survive; later-defined type, constructor and parameter attributes survive; nested enum fields execute; dependency cycles/unresolved types produce managed errors; unsupported metadata is filtered without losing ordinary ref parameters.

The second command creates an isolated temporary bootstrap, builds the source compiler, then verifies C# hosting, saved execution, a Nemerle forward-attribute fixture and its C# consumer, and the compiler's strong-name signature. These checks pass. It prints the temporary artifact directory and retains logs.

The patch uses installed Mono.Cecil 0.11.1 and a temporary bridge; checked-in bootstrap binaries are unchanged. Temporary patched binaries are a bootstrap aid, not release artifacts. The production Mono persistence adapter also depends on Mono.Cecil 0.11.1. The CoreCLR adapter checks exclude the Mono persistence implementation and use PersistedAssemblyBuilder; the Nemerle compiler itself has not been ported to CoreCLR.

## Runtime rebuild now passes

The third command rebuilds Nemerle.dll successfully. Its C# consumer verifies list enumeration, generic heap interfaces (including private explicit Remove), and MappedMemberAttribute's self-applied constructor-parameter annotation. The rebuilt runtime also passes strong-name verification.

Adapter checks on Mono and .NET 10 cover self/cyclic attributes, constructor and return parameters, fields/properties, named arguments, arrays, enums, typeof values and generic interface calls. Persisted Mono output retains attributes as data and writes them through Cecil. In-memory compilation still uses live emission and reports unsupported attribute cycles as managed errors; it does not silently discard annotations.

The staged toolchain runner now rebuilds the compiler, runtime, macros and CLI, rebuilds the compiler using the preceding source-built compiler, and runs selected upstream regressions. The entire upstream suite has not been verified. Debug-symbol preservation through metadata rewriting has not been verified. File modules are documented separately. Script sessions, full modern CoreCLR compiler hosting and engine/native platform contracts remain later work.
