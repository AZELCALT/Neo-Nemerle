# Portable PDB and resource follow-up

The workspace `toolchain/coreclr/ncc` now produces portable PDBs with `-debug`.
The compiler's existing debug emission supplies source documents, sequence points,
lexical scopes and local names. The platform writes the portable PDB and PE
CodeView entry; metadata repair/signing preserves them and references the final
PDB filename. A release rebuild removes a stale portable PDB beside the output.
Debug output currently requires persisted compilation; this does not add symbols
to directly runnable in-memory Reflection.Emit assemblies.

Native Windows resource-compiler `.res` input now works through `-win32res:path`.
A managed parser builds the PE `.rsrc` directory with numeric/string identifiers,
language IDs and original payloads. Invalid/truncated input and duplicate resource
keys are rejected. This imports prepared `.res` files; it does not compile `.rc`
source or automatically generate a default version resource. Assembly version
attributes continue to work.

The portable ResX reader now supports invariant string type converters (including
Guid and TimeSpan), explicit nulls, byte-array MIME type converters, and string/byte
file references resolved against a base directory with declared text encodings.
Converter support requires the resource's type and converter to exist on the target
platform. The Resource macro now handles array types and null values. The macro
creates typed accessors; it does not itself turn XML into binary `.resources` files.

Legacy serialized binary/SOAP object resources remain rejected. Arbitrary typed
file references, such as Windows-only drawing objects, are not implemented here.
External linked resources also remain rejected: emitting their manifest is possible,
but actual .NET 10 `GetManifestResourceStream` returns null. The runtime's
[file-resource handling](https://github.com/dotnet/runtime/blob/v10.0.0/src/coreclr/vm/peassembly.cpp#L549-L564)
explicitly declines external file entries. Embedded resources work.

## Verification

- Both Mono and .NET 10 platform suites passed, including converter/null/file
  encoding checks, portable PDB metadata after signing, numeric/named native
  resource trees and payloads, malformed native input, and explicit linked errors.
- The compiler/runtime/CLI were source/self-built under CoreCLR; standard macros
  were rebuilt with the array/null changes and passed strong-name verification.
- A signed real compiler DLL generated typed resource properties that returned
  UTF-16 file text, an integer, a byte array and null. Its exception stack trace
  reported the actual Nemerle source file and line; the PDB retained `answer`.
- That DLL retained native resource data and the correct CodeView PDB filename
  after compiler metadata repair/signing. Release rebuilding removed its old PDB.
- The CoreCLR hosting/C# consumption checks and full file-module suite passed.

Reproduce the integration test:

```sh
python3 tests/check-coreclr-debug-resources.py \
  --toolchain toolchain/coreclr --references toolchain/coreclr/references
```

Evidence: `baseline/coreclr-verification/debug-resources.log`, `platform.log`,
`resource-macros.log`, `source-toolchain.log`, `compiler-hosting.log`, and
`file-modules.log`. No interactive debugger or Windows execution was tested.
No license changes were made.
