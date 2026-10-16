# Dials and shared scopes

Active whenever a compilation contains `grammar`/`space` blocks, or continues from a binary that stores grammars or
scopes. Nitra notation stays inside `grammar`; custom input stays inside `space`. These services belong to one
compiler session, not to a runtime dictionary.

A space is a logical file in a grammar's language inside a Nemerle file. It is always at the top level of its file:
a space inside a function or a type, or used as an expression, is an error. The program and its spaces communicate
two ways: **scopes**, a shared memory zone of bindings that both sides read and write, and **dials**, direct calls
into a space (`dial:.file.space::member(...)`). A dial names the file because each file has its own spaces.

## Source interface

```nemerle
scope A;

grammar Demo {
  using Nemerle.Compiler.NitraDialectServices;
  using Nemerle.Compiler.Parsetree;
  syntax module Query {
    using Nitra.Core;
    [StartRule] syntax Input = "answer" {
      map (context : NitraDialectContext) PExpr = {
        def shared = context.Scope("A");
        shared.Set("doubled", <[ $(shared.Get("answer").Value :> PExpr) * 2 ]>);
        <[ () ]>
      };
    }
  }
}

scope.A.registery("answer", type("integer"));
scope.A.registery("doubled", type("integer"));
scope.A.answer = 21;
space Demo [A] { answer }
System.Console.WriteLine(scope.A.doubled);   // 42
```

The space's mapped code takes its place among the file's top-level statements, and its own value is discarded.
Results come back through a scope binding (as `doubled` above) or a dial. An embedding host that tests a mapping can
collect the value instead with `NitraSourceConfiguration.SpaceValueTarget`, an assignable expression such as a static
field.

`scope A;` and `scope A {}` declare an empty shared scope. The first `registery`
operation can also create its scope. Registration declares a binding and its
custom type token; assignment updates an existing binding. Duplicate bindings,
missing bindings, and reading a binding before it has a value are errors.
Assignments record Nemerle expression AST in the compiler scope, rather than
executing the expression during compilation. Its runtime behavior is determined
when a mapping inserts that expression into the output. Ordinary CLR type
checking still applies to the generated expression.

`[A]` attaches a shared scope to a space. It does not import
surrounding globals or publish the space's internal declarations. Mappings and
resolvers access attached scopes through `context.Scope("A")`. Register shared
bindings before the space that consumes them; top-level statements, spaces
included, are handled in source order. A custom type token is resolved by the consuming
dial's `ResolveType`, so it does not need to be a CLR type upfront.

## Dials: addressing a space

The form is `dial:.file.space::member`:

```nemerle
space Demo as Query [A] { answer }
Demo:.demo.Query::answer()
Demo:.demo.Query::answer             // reference; no invocation yet
scope.A.registery("f", Demo:.demo.Query::answer);
scope.A.f()
```

`Demo` is the dial (the grammar the space is written in). `demo` is the file
module that owns the space, relative to the source root (with
`-file-name-namespaces`, the file name). `Query` is the space, named with
`space Demo as Query`. Qualified grammar names and nested file modules are
supported.

Each file may contain one space per grammar. Different grammars may coexist in
the file. The compiler also accepts `Demo:.demo::answer()` without the space
segment for a space that has no `as` name.

The registry finds the owning space first. Its resolver receives only the member
request for that space; it does not search neighboring spaces. The resolver
supplies signatures/overload candidates and decides reachability and selection.
A reference registered in a scope retains those inferred signatures and the
target identity. Calling it resolves against that target with the current call's
arguments and compiler context; callers never have to repeat its signature.

## Resolver API

Implement `INitraDialectResolver` in a referenced compiler-support library, separate from the grammar that uses it
(the grammar is compiled on its own and sees only referenced binaries):

- `Resolve(NitraDialectRequest)` returns `NitraDialectResolution`, or null for an
  unreachable name. Requests contain the name, argument ASTs, `IsCall`, and context.
- `ResolveType(string, NitraDialectContext)` returns a dial-owned type token,
  or null when unknown. Tokens and signatures can carry opaque dial metadata.
- A resolution supplies `Signatures`, optional metadata, and a `Lower` delegate
  returning a Nemerle `PExpr`. Resolving a reference need not lower/invoke it.
- Overload selection belongs to the resolver. `context.Typer` provides the current
  Nemerle type environment and compiler services for explicit symbol/type probes.
  The compiler checks the returned AST through its normal pipeline.

Register a resolver through host configuration:

```csharp
var configuration = new NitraSourceConfiguration();
configuration.ConfigureDialects = registry =>
    registry.RegisterResolver("Demo", "demo", new MyResolver());
options.NitraSources = configuration;
```

Or register it from native mapping code using
`context.RegisterResolver(resolver)`. A forward dial initializes
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

`tests/check-native-source.py --checks NitraDialectChecks.cs` exercises calls,
method-group callbacks, CLR calls/type errors, automatic signatures, scope
updates, custom types, contextual mappings, mapping-provided resolvers, file
ownership, multiple grammars/files, diagnostics, and failure recovery.

`tests/check-continuation.py` (stage P) checks scopes stored in a library's
continuation section (scope subsection, `doc/CONTINUATION.md`), plugin scripts
that use a host's grammar, scopes and dials with no grammar of their own, the
plain space's cross-grammar lookup, and the top-level rule.

## Space modes

- `space G { ... }` uses grammar `G`; `space (A, B) { ... }` mixes `A` and `B`.
- `space { ... }` is the plain space, over full Nitra and across grammars: its
  file's grammars, or, when those do not give exactly one start rule, every
  visible grammar (other files and continued binaries).

## Boundaries

Scope bindings with expression values are stored in output assemblies as
expression text; bindings holding dial references are not stored. Scopes are not
a runtime scripting session, and alternate
`runtime`/`compile`/form/semantic-kind notation remains inactive. Native shorthand
for list/optional PExpr output containers remains a separate unfinished feature.
