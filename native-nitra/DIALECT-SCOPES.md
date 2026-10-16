# Dials and shared scopes

Active whenever a compilation contains `grammar`/`space` blocks, or continues from a binary that stores grammars or
scopes. Nitra notation stays inside `grammar`; custom input stays inside `space`. These services belong to one
compiler session, not to a runtime dictionary.

A space is a logical file in a grammar's language inside a Nemerle file. It is always at the top level of its file:
a space inside a function or a type, or used as an expression, is an error. The program and its spaces communicate
two ways: **scopes**, a shared memory zone of bindings that both sides read and write, and **dials**, direct calls
into a space (`dial:.file.G::member(...)`). A dial names the file because each file has its own spaces.

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
        shared.Write("doubled", <[ $(shared.Read("answer")) * 2 ]>)
      };
    }
  }
}

scope.A.registery("answer", type("int"));
scope.A.registery("doubled", type("int"));
scope.A.answer = 21;
space Demo [A] { answer }
System.Console.WriteLine(scope.A.doubled);   // 42
```

The space's mapped code takes its place among the file's top-level statements, and its own value is discarded.
Results come back through a scope slot (as `doubled` above) or a dial. An embedding host that tests a mapping can
collect the value instead with `NitraSourceConfiguration.SpaceValueTarget`, an assignable expression such as a static
field.

A scope is a dedicated global storage that the program and its spaces share.
`scope A;` (or `scope A {}`) declares it at the top level of a file; the first
`registery` can also create it. `scope.A.registery("x", type("t"))` appends a slot,
`scope.A.x = e` writes it and `scope.A.x` reads it, anywhere and when the program
runs. The values live in `Nemerle.Scopes.Scope` (the language runtime), which the
whole process shares, so a host application and the plugin scripts it runs see
the same storage. Anything fits a slot: its Nemerle type is the grammar's
(`NitraDialectType.Clr` from the resolver of a space that attaches the scope), or
the token itself when it names a Nemerle type, or `object`; the code that uses the
slot is type-checked as usual. A slot starts with its type's default. Registering
a slot twice in one compilation, and using a slot or scope that does not exist,
are errors. Registrations with literal arguments join the layout when the
sources are read, so every use sees the slot whatever order code is typed in.

`[A]` attaches a shared scope to a space. It does not import
surrounding globals or publish the space's internal declarations. Mappings and
resolvers access attached scopes through `context.Scope("A")`: `Read("x")`,
`Write("x", value)` and `RegisterCode("x")` give the code that reads, writes and
appends a slot, for the space's own output (`Get("x").Value` is the read code too).
A slot can also hold a dial member (`scope.A.registery("f", dial:.file.G::m)`):
the storage keeps its value, so code elsewhere (a plugin) calls `scope.A.f(...)` as
a function value, while calls in the same compilation resolve through the dial.

## Dials: addressing a space

A dial is `dial:.path::member`, where the path is where the space stands:

```nemerle
space Demo [A] { answer }
dial:.demo.Demo::answer()
dial:.demo.Demo::answer             // reference; no invocation yet
scope.A.registery("f", dial:.demo.Demo::answer);
scope.A.f()

space (Demo, Extra) { answer }
dial:.demo.(Demo, Extra)::answer()
dial:.demo.(Extra, Demo)::answer()  // the same space: order does not matter

space { answer }                    // the plain space
dial:.demo::answer()
```

`demo` is the file module that owns the space, relative to the source root
(with `-file-name-namespaces`, the file name). Qualified grammar names and
nested file modules are supported (`dial:.a.b.Q.G::m`); a file cannot sit beside
a directory of its name, so the path is never ambiguous.

Each file has one space per grammar, one per mix of grammars (in any order), and
one plain space. `space Demo as Query` gives a space a second name,
`dial:.demo.Query::`; it does not create another space. Host configuration
registers resolvers by the same paths (`registry.RegisterResolver("demo.Demo",
resolver)`, or `"demo.(Demo, Extra)"`, or `"demo"`).

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
    registry.RegisterResolver("demo.Demo", new MyResolver());
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

A scope travels in output assemblies as its layout (slot names, type tokens and
types) with the binary's spaces; the values stay in the running program's storage.
A slot holding a dial member stores the member's value (a function value when its
one signature's types are given by the grammar). Custom form and semantic-kind
notation inside a grammar remains inactive. Native shorthand
for list/optional PExpr output containers remains a separate unfinished feature.
