# Scripts

A script is a Nemerle file run directly, without a build step: `nscript run file.ns`. The design follows Kotlin's
scripting, and so does the name: as Kotlin scripts are `.kts` files next to `.kt` ones, Nemerle scripts are `.ns` files
next to `.n` ones. Scripts are ordinary Nemerle, they can declare what they depend on, and libraries can define kinds
of script with their own base class and imports.

The extension keeps the two apart: a project compiles its `.n` files and leaves `.ns` files alone, and the editor
shows a script with the yellow logo and checks it as `nscript` compiles it (its kind, its `DependsOn`): its errors show
while it is edited, with hover, go-to-definition and typed completion as in any other file. `nscript` runs a plain `.n` file too, the same way: that is for running ordinary
Nemerle directly, wherever that is needed. A `.ns` file is the same job in its own format, a file that is a script and
nothing else.

## Running scripts

```nemerle,script
def names = ["ada", "alan", "grace"];
foreach (name in names)
  System.Console.WriteLine($"hello, $name")
```

```text
hello, ada
hello, alan
hello, grace
```

| Command | What it does |
|---|---|
| `nscript run file.ns` | compile (cached) and run |
| `nscript compile file.ns out.dll` | compile to an artifact |
| `nscript run-compiled out.dll` | run an artifact without the compiler |
| `nscript repl` | an interactive session |

Arguments after `--` reach the script as `args`.

A script is a file like any other: it can declare functions, classes, `grammar`s and `space`s. Its top-level code,
spaces included, is what runs. `nscript` compiles it with the compiler itself (it is the same compiler, in the
process), so a script is Nemerle as a compiled file is, `await` in its top-level code included: the script's code
then runs as an async function, and the script ends when it does. Its values follow a file's rules (chapter 7): a
`mutable` may change type, and the script's functions check a value of several types before they use it.

```nemerle,script
using System.Threading.Tasks;

def answer = await Task.Run(() => 41);
System.Console.WriteLine(answer + 1)
```

```text
42
```

## Declaring dependencies

A script lists what it needs at its top, as Kotlin's `@file:` annotations do:

```nemerle,ignore
[assembly: DependsOn("tools.dll")]                 // a local library, relative to the script
[assembly: DependsOn("Example.Package", "1.2.3")]  // a NuGet package at an exact version
[assembly: Repository("https://api.nuget.org/v3/index.json")]
[assembly: Import("helpers.ns")]                   // another script, as a typed child
[assembly: CompilerOptions("-define:FAST")]
```

A library a script depends on brings everything stored in its continuation section: its grammars, its macros, and the
helpers those macros use:

```nemerle,lib=tools
// ncc: -r:{toolchain}/Nemerle.Compiler.dll
// file: tools.n
using Nemerle.Compiler;

macro twice(e)
{
  <[ $e * 2 ]>
}

grammar Words
{
  using Nemerle.Compiler.Parsetree;
  syntax module W
  {
    using Nitra.Core;
    [StartRule] syntax Start = "answer" { map PExpr = <[ System.Console.WriteLine(42) ]>; }
  }
}
```

```nemerle,script
[assembly: DependsOn("tools.dll")]
using tools;
System.Console.WriteLine(twice(20));
space Words { answer }
```

```text
40
42
```

## Scripts as plugins

An application that runs scripts can give them its own languages. Its grammars, its scopes and its spaces are stored in
its section, so a script it runs gets them with no grammar or `scope` declaration of its own. Scope storage belongs
to the process, so the application and its scripts share the values: the script reads what the application wrote,
and the application sees what the script writes. A script can also dial into the application's spaces. A file that
uses only scopes or dials, with no space at all, is looked up the same way.

The dial's resolver is a library of its own, as in [Grammars and spaces](10-grammars.md):

```nemerle,lib=appres
// ncc: -r:{toolchain}/Nemerle.Compiler.dll
// file: appres.n
using System;
using Nemerle.Compiler.NitraDialectServices;
using Nemerle.Compiler.Parsetree;

public class Resolver : INitraDialectResolver
{
  public ResolveType(name : string, _context : NitraDialectContext) : NitraDialectType
  {
    if (name == "number") NitraDialectType(name, "int") else null
  }
  public Resolve(request : NitraDialectRequest) : NitraDialectResolution
  {
    if (request.Name != "twice") null
    else
    {
      def answer = NitraDialectResolution();
      answer.Signatures.Add(NitraDialectSignature("twice", NitraDialectType("number"), array[NitraDialectType("number")]));
      answer.Lower = Func(r => <[ $(r.Arguments[0]) * 2 ]>);
      answer
    }
  }
}

public Create() : INitraDialectResolver { Resolver() }
```

The application defines the grammar and the scope, then runs a plugin in its own process with the scripting API
(see below):

```nemerle,app
// ncc: -r:{chapter}/appres.dll -r:{toolchain}/Nemerle.Compiler.dll -r:{toolchain}/Nemerle.Scripting.dll
// file: main.n
scope A;
grammar G
{
  using Nemerle.Compiler.NitraDialectServices;
  using Nemerle.Compiler.Parsetree;
  syntax module M
  {
    using Nitra.Core;
    [StartRule] syntax Start = "go"
    {
      map PExpr = {
        def c = NitraDialectContext.Current;
        when (c.Space.Resolver == null) c.RegisterResolver(appres.Create());
        <[ () ]>
      };
    }
  }
}

scope.A.registery("value", type("number"));
scope.A.value = 21;

def host = Nemerle.Scripting.host.ScriptHost();
def definition = Nemerle.Scripting.contracts.ScriptDefinition();
definition.TargetReferenceDirectory = System.IO.Path.Combine(System.AppContext.BaseDirectory, "references");
definition.References.Add(System.Reflection.Assembly.GetEntryAssembly().Location);
definition.References.Add(System.IO.Path.Combine(System.AppContext.BaseDirectory, "appres.dll"));
def plugin = host.Compile(Nemerle.Scripting.contracts.ScriptSource(System.IO.File.ReadAllText("plugin.txt"), "plugin.ns"), definition);
if (plugin.Success) _ = host.Evaluate(plugin.Script, Nemerle.Scripting.contracts.ScriptInputs());
else foreach (d in plugin.Diagnostics) System.Console.WriteLine(d.Message);
System.Console.WriteLine($"the application sees $(scope.A.value)");
// file: plugin.txt
using main;
space G [A] { go }
System.Console.WriteLine(scope.A.value);
System.Console.WriteLine(dial:.plugin.G::twice(scope.A.value));
scope.A.value = 50;
```

```text
21
42
the application sees 50
```

The plugin is `plugin.ns` to the compiler, so its space is `dial:.plugin.G`. `using main;` imports the application's
file, which is what makes its scope `A` (`main.A`) the plugin's `scope.A`.

A slot can hold a value of the application's own types too, and it is one value: every reader gets the same object,
and a write through it is seen by all. To .NET a type is a copy of an assembly and a name, so a type compiled twice is
two types, and an object is of one of them. A plugin compiled against the application (a script always is) makes no
copy of the types the application's slots reach:

- the same file module (the plugin compiles the same `shapes.n`) is the application's module, so `shapes.Point` there
  is the application's type;
- a type with the same code under another name (the same fields and members, its behaviour) is an alias of the
  application's type;
- a file module the application has with other code is an error: a module is one in the program.

The application records those types, with their code, in its continuation section, and only those: a type no slot
reaches records nothing. A copy compiled apart, without the application, is another .NET type, and reading or writing
the slot with it is an error that says it is the same code compiled apart, or what differs. A slot of no fixed type
holds a `Content` instead, any value with its type, which the reader asks for as the type it expects.

## Script kinds

A library can declare a **kind of script**, as Kotlin's `@KotlinScript` does. A class marked `[ScriptDefinition(ext)]`
becomes the base class of every script whose file name ends in `ext`. The extension is written in its `.n` form and
covers both: `.build.n` is the kind of `deploy.build.ns` and of `deploy.build.n`. Those scripts need no
setup lines at all:

```nemerle,lib=buildkind
// ncc: -r:{toolchain}/Nemerle.Scripting.dll
// file: buildkind.n
using Nemerle.Scripting.kinds;

[ScriptDefinition(".build.n", DisplayName = "Build script", Imports = array["System.Console"])]
public class BuildScript
{
  public Target : string { get { "release" } }
  public Log(message : string) : void { System.Console.WriteLine("[build] " + message) }
}
```

```nemerle,script
// file: deploy.build.ns
Log("building " + Target);
WriteLine("done")
```

```text
[build] building release
done
```

- **Base class:** the script's code runs as a member of the class, so `Log` and `Target` are its own members.
- **Imports:** the listed modules and namespaces are opened.
- **Reference:** the library is referenced, so its grammars and macros come with it.
- **Configure:** a `public static Configure(definition : ScriptDefinition) : void` on the class can set anything else:
  receivers, properties, packages, compiler options.

`nscript` looks for kinds in the dlls next to itself, in the directories of `NEMERLE_SCRIPT_PATH`, and next to the
script. It reads only their metadata, until a script of the kind runs.

## Embedding scripts in an application

`Nemerle.Scripting.dll` is the host API used by `nscript` itself. An application creates a `ScriptHost`, a
`ScriptDefinition` (base class, receivers, provided properties, imports, dependencies), and compiles and evaluates
`ScriptSource`s. Sessions keep state across submissions, as a REPL does. `scripting/README.md` documents the API, and
`scripting/KOTLIN-FACILITIES.md` maps it to Kotlin's.
