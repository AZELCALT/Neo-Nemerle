# Experimental dialect references and shared scopes

Enabled by `-experimental-nitra-source` or `NitraSourceConfiguration(true)`.
Nitra notation remains inside `grammar`; custom input remains inside `space`.
These services belong to one compiler session, not a runtime dictionary.

## Source interface

```nemerle
scope A;

grammar Demo {
  using Nemerle.Compiler;
  using Nemerle.Compiler.Parsetree;
  syntax module Query {
    using Nitra.Core;
    [StartRule] syntax Input = "answer" {
      map (context : NitraDialectContext) PExpr = {
        context.Scope("A").Get("answer").Value :> PExpr
      };
    }
  }
}

module Program {
  Main() : int {
    scope.A.registery("answer", type("integer"));
    scope.A.answer = 42;
    space Demo [A] { answer }
  }
}
```

`scope A;` and `scope A {}` declare an empty shared scope. The first `registery`
operation can also create its scope. Registration declares a binding and its
custom type token; assignment updates an existing binding. Duplicate bindings,
missing bindings, and reading a binding before it has a value are errors.
Assignments record Nemerle expression AST in the compiler scope, rather than
executing the expression during compilation. Its runtime behavior is determined
when a mapping inserts that expression into the output. Ordinary CLR type
checking still applies to the generated expression.

`[A]` attaches a shared configuration scope to a space. It does not import
surrounding globals or publish the space's internal declarations. Mappings and
resolvers access attached scopes through `context.Scope("A")`. Register shared
bindings before mappings consume them; for sharing across files/methods, declare
the scope at top level or in compiler configuration instead of depending on
method visitation order. A custom type token is resolved by the consuming
dialect's `ResolveType`, so it does not need to be a CLR type upfront.

## Addressing a dialect

```nemerle
Demo:.demo::answer()
Demo:.demo::answer             // reference; no invocation yet
scope.A.registery("f", Demo:.demo::answer);
scope.A.f()
```

`Demo` selects the dialect (the selected source grammar's name). `demo` is the
owning file namespace in file-module mode, relative to the existing source root.
For compatibility in ordinary mode it is the filename without its extension.
Qualified dialect names and nested file namespaces are supported.

Each file may contain one source space per selected dialect. Different dialects
may coexist in the file. Anonymous spaces remain addressable through their file
namespace. An optional `space Demo as Query [A] { ... }` also registers
`Demo:.demo.Query::answer()` as an alias of that same space. This does not create
a second space or change the one-space-per-dialect rule.

The registry finds the owning space first. Its resolver receives only the member
request for that space; it does not search neighboring spaces. The resolver
supplies signatures/overload candidates and decides reachability and selection.
A reference registered in a scope retains those inferred signatures and the
target identity. Calling it resolves against that target with the current call's
arguments and compiler context; callers never have to repeat its signature.

## Resolver API

Implement `INitraDialectResolver` in a referenced compiler-support library:

- `Resolve(NitraDialectRequest)` returns `NitraDialectResolution`, or null for an
  unreachable name. Requests contain the name, argument ASTs, `IsCall`, and context.
- `ResolveType(string, NitraDialectContext)` returns a dialect-owned type token,
  or null when unknown. Tokens and signatures can carry opaque dialect metadata.
- A resolution supplies `Signatures`, optional metadata, and a `Lower` delegate
  returning a Nemerle `PExpr`. Resolving a reference need not lower/invoke it.
- Overload selection belongs to the resolver. `context.Typer` provides the current
  Nemerle type environment and compiler services for explicit symbol/type probes.
  The compiler checks the returned AST through its normal pipeline.

Register a resolver through host configuration:

```csharp
var configuration = new NitraSourceConfiguration(true);
configuration.ConfigureDialects = registry =>
    registry.RegisterResolver("Demo", "demo", new MyResolver());
options.NitraSources = configuration;
```

Or register it from native mapping code using
`context.RegisterResolver(resolver)`. A forward dialect reference initializes
that target's mapping if no resolver was configured yet. Mapping-based setup
should register only when `context.Space.Resolver == null`, since a mapping may
be invoked more than once. The support implementation must already be available
to the grammar-only compiler as a referenced assembly.

Root mappings may take a single `NitraDialectContext` parameter, as above.
Existing parameterless mappings keep working and can use
`NitraDialectContext.Current`. If both forms exist, the contextual form is chosen.
The active context is restored after nested invocations and failures.

`context.Reference(name)` returns a typed `NitraDialectReference` carrying its
inferred resolution. `context.Scope("A").Register(name, reference, location)`
registers it without repeating its signatures. The registry also exposes source
registration locations and a compilation-local `Trace` of registrations/lookups.
Compiler API access is explicit; scope attachments grant access only to those
shared scopes.

## Verification and boundaries

`baseline/check-native-source.py --checks NitraDialectChecks.cs` exercises calls,
method-group callbacks, CLR calls/type errors, automatic signatures, scope
updates, custom types, contextual mappings, mapping-provided resolvers, file
ownership, multiple dialects/files, diagnostics, and failure recovery.

This is an experimental source-compilation API. Registries are not persisted in
output assemblies, scopes are not a runtime scripting session, and alternate
`runtime`/`compile`/form/semantic-kind notation remains inactive. Native shorthand
for list/optional PExpr output containers remains a separate unfinished feature.
