# Scripts

A script is ordinary Nemerle run with `nscript`, using the same CLR compiler as `ncc`. You do not need a `.nproj`
or a separate build command. This chapter starts with running files, sharing helpers and saving compiled scripts;
the later sections cover application-defined script kinds and embedding.

Use `.ns` for files you intend to run as scripts. A project includes its `.n` sources and leaves `.ns` files alone.
`nscript` can run a plain `.n` file too. In the editor, scripts have a yellow icon and receive diagnostics, hover and
completion for their dependencies and script kind.

Install the toolchain as described in [Getting started](01-getting-started.md). The commands below assume `nscript`
is on PATH. From a clone, you can also use `boot/coreclr/nscript` on Linux/macOS, or
`dotnet boot\coreclr\nscript.exe` on Windows. Running scripts needs .NET 10, not the .NET SDK.

## Running scripts

Save this as `hello.ns`:

```nemerle,script
// file: hello.ns
def names = ["ada", "alan", "grace"];
foreach (name in names)
  System.Console.WriteLine($"hello, $name")
```

```text
hello, ada
hello, alan
hello, grace
```

Run it from a terminal with `nscript run hello.ns`. The work goes at the top level, in source order; a `Main` method
is not required. Functions, classes, masks, macros and grammars remain available as in other Nemerle files.

| Command | What it does |
|---|---|
| `nscript run file.ns` | compile (cached) and run |
| `nscript compile file.ns out.dll` | compile to an artifact |
| `nscript run-compiled out.dll` | run an artifact without the compiler |
| `nscript repl` | an interactive session |

### Arguments and results

Arguments after `--` reach the script as `args : array[string]`. Always use that separator for script arguments,
particularly ones beginning with `-`. Quote an argument containing spaces in your shell:

```nemerle,script
// file: greet.ns
def name = if (args.Length == 0) "world" else args[0];
System.Console.WriteLine($"Hello, $name!")
```

```text
Hello, world!
```

```sh
nscript run greet.ns -- "Grace Hopper"
```

```text
Hello, Grace Hopper!
```

`nscript` also prints the script's final expression when it produces a non-null value. This script prints `42`
without an explicit `WriteLine`:

```nemerle,script
// file: answer.ns
def total = 6 * 7;
(total : int)
```

```text
42
```

A final `WriteLine` returns `void`, so it adds no second result. Use `_ = expression` when you want to discard a
value. An integer result is printed as a value; it does not become the process exit code. Successful execution
returns exit code zero. Compilation errors and uncaught exceptions return a nonzero code and diagnostics on stderr.
In PowerShell inspect `$LASTEXITCODE`; in a POSIX shell inspect `$?`.

The parentheses in `(total : int)` matter: at the top level, bare `total : int` declares a field rather than annotating
an expression. When returning an already typed value, plain `total` is enough.

### Functions, masks and state

Declare reusable functions as members and call them from the top-level code. A typed `mutable` field is useful for
state those functions update. A mask groups functions; when qualifying a masked function, include the file owner:

```nemerle,script
// file: tally.ns
mutable calls : int = 0;
mask math
{
  public Twice(n : int) : int { calls++; n * 2 }
}
System.Console.WriteLine(tally.math.Twice(21));
System.Console.WriteLine(calls)
```

```text
42
1
```

The call and the top-level code share `calls`. A second `nscript run tally.ns` starts it at zero again. The usual
binding, type and visibility rules apply; [Files are modules](07-files-and-modules.md) explains values that change
type. Persistent interactive state is covered in the [REPL section](#interactive-use-the-repl).

### Async work

Top-level `await` works without adding an async entry point. Await the operation whose result you want before the
script finishes:

```nemerle,script
using System.Threading.Tasks;

def answer = await Task.Run(() => 41);
System.Console.WriteLine(answer + 1)
```

```text
42
```

## Local source files

An ordinary `using` can discover a neighboring `.n` file. No `.nproj` or project warning is involved:

```nemerle,script
// file: hello.ns
using helpers;
System.Console.WriteLine(Greeting("Ada"))

// file: helpers.n
public Greeting(name : string) : string { $"Hello, $name!" }
```

```text
Hello, Ada!
```

Resolution starts beside each importing file and also checks the source root, so dependencies can import their own
neighbors. `using util;` makes the immediate files under `util/` available by file name, such as `text.Shout(...)`.
A registered file uses its logical path: `register library.words;` in `text.n` is opened with
`using library.words.text;`, or reached as `text` after `using library.words;`.

These `.n` helpers compile into the script's artifact. Their contents participate in its cache key, so editing a
helper, including one imported through another helper, rebuilds the script. An imported helper may also have async
top-level code; it finishes before the script uses it. `using` resolves CLR namespaces and referenced libraries too;
it does not download DLLs or packages. `import other;` below composes another
script as a typed child, with its own script context.

### Importing another script

Use `import file;` when the dependency is `file.ns`, a script with initialization and state of its own.
Put imports at the start of the script, alongside `using` and dependency attributes. An import loads the child and
opens its public declarations, so both `Next()` and `counter.Next()` work. `using` continues to discover `.n` helpers
and CLR names; it does not load a `.ns` file:

```nemerle,script
// file: use_counter.ns
import counter;
System.Console.WriteLine(Next());
System.Console.WriteLine(counter.Next())

// file: counter.ns
mutable count : int = 0;
System.Console.WriteLine("counter ready");
public Next() : int { count++; count }
```

```text
counter ready
1
2
```

Run `nscript run use_counter.ns`. The child initializes before its importer and keeps the same state for both calls.
Running the root script again starts fresh state. Qualify names with the child's filename when needed.
Private declarations stay private. Cyclic imports, duplicate direct
imports and two children with the same file owner are errors.

`import util.counter;` resolves `util/counter.ns` relative to the importing script. For an explicit path, use
`import "../shared/counter.ns";`. Quoted paths must name `.ns` files. In `#pragma indent` mode, an import can end at
the newline; otherwise finish it with `;`. Imported scripts can import their own neighbors the same way. These are
script-host directives, available when running `.ns` or `.n` through `nscript`, not namespace imports for `ncc`.

`[assembly: Import("counter.ns")]` remains supported for compatibility and for metadata-driven hosts. That older
form acquires the child without automatically opening its names. DLL and package dependencies keep using
`DependsOn`; script imports do not load assemblies or restore packages.

| You want to use | Write |
|---|---|
| A neighboring ordinary source file | `using helpers;` for `helpers.n` |
| File names under a physical or logical folder | `using util;`, then `text.Member(...)` |
| A registered file module | `using library.words.text;` |
| Another script and its state | `import helpers;`, then `Member(...)` or `helpers.Member(...)` |
| A CLR namespace or type already referenced | `using System;` or `using System.Console;` |
| An external assembly | `[assembly: DependsOn("tools.dll")]`, then its normal `using` |

### Which directory a path uses

| Path | Relative to |
|---|---|
| `using helpers;` for a local source | the importing file's directory, then the source root |
| `DependsOn("tools.dll")`, `import child;`, `import "child.ns";` | the declaring script's directory |
| A relative feed in `Repository(...)` or `--repository` | the process's current working directory |
| `File.ReadAllText("input.txt")` and other ordinary .NET file operations | the process's current working directory |
| Command-line source/output paths, `--cache-dir`, `--history` | the terminal's current directory |

Running `nscript run scripts/report.ns` does not change the current working directory to `scripts/`. Pass data paths
through `args` or use explicit paths when invoking the same script from different directories. Keep ordinary script
filenames valid identifiers, such as `daily_report.ns`; a compound suffix such as `deploy.build.ns` needs the script
kind described [below](#script-kinds).

## Declaring dependencies

### What resolves a dependency

Nemerle's scripting library provides compilation, evaluation, script imports, typed host inputs and compiled-code
caching. Package management is supplied by a separate resolver configured by the host. The compiler consumes the
resolved assembly references; it does not choose package versions, contact package feeds or install packages.

| Dependency | How it becomes available |
|---|---|
| A local `.n` helper | ordinary `using` source discovery |
| Another `.ns` script | `import other;`, handled by the script host |
| A local DLL | `[assembly: DependsOn("tools.dll")]`, resolved relative to the script |
| A package ID and version | a configured package resolver, such as the optional NuGet adapter |

An embedded `ScriptHost` starts without a package resolver. The application supplies one through
`ScriptHostOptions.Resolver`; scripts that do not request packages can run without one. Requesting a package without
a resolver produces `No script dependency resolver configured`.

The supplied `nscript` CLI automatically configures the NuGet adapter when `Nemerle.Scripting.NuGet.dll` and its
supporting libraries are installed beside the runner. The bundled `boot/coreclr` toolchain includes that adapter.
This is a CLI distribution choice, not a built-in package manager in the scripting library. A minimal/custom build
may omit it while retaining the scripting features above.

An application can implement `IScriptDependencyResolver` to use another package source or resolution policy. It
returns compatible CLR compilation/runtime references, any native library paths, and a dependency fingerprint for
caching. The current CLI specifically discovers the NuGet adapter; it does not automatically discover arbitrary
resolver plugins. A different CLI resolver needs explicit runner wiring, while an embedded host can assign one
directly. Neither the scripting library nor the NuGet adapter requires the .NET SDK or MSBuild at runtime.

### Local assemblies

A script declares external dependencies and configuration with assembly attributes at its top. A local DLL is the
smallest example. Save `arithmetic.n` and build it with
`ncc arithmetic.n -target:library -out:arithmetic.dll`:

```nemerle,lib=arithmetic
// file: arithmetic.n
public Double(n : int) : int { n * 2 }
```

Put this script beside `arithmetic.dll` and run `nscript run use_arithmetic.ns`:

```nemerle,script
// file: use_arithmetic.ns
[assembly: DependsOn("arithmetic.dll")]
using arithmetic;
System.Console.WriteLine(Double(21))
```

```text
42
```

The attribute adds the reference; `using` opens names from it. More than one dependency attribute is allowed.

### NuGet packages

Package requests use an ID and an exact version. For example, save this as `json.ns`:

```nemerle,ignore
[assembly: DependsOn("Newtonsoft.Json", "13.0.3")]
using Newtonsoft.Json;
System.Console.WriteLine(JsonConvert.SerializeObject(array[1, 2, 3]))
```

```text
[1,2,3]
```

Run `nscript run json.ns`. The first run needs the package in the cache, a local feed, or access to the configured
feed. This network-dependent example is not part of the offline book checks. This example uses the optional NuGet
adapter described above, including its supporting libraries. If that adapter is absent, the CLI reports that no
package resolver is configured; ordinary script execution and local DLL references remain available.

The NuGet adapter's default package feed is nuget.org. Add another with `[assembly: Repository("https://my.feed/v3/index.json")]`
or a local feed with `[assembly: Repository("packages")]`. Versions such as `"13.*"` are not exact requests.

These command-line options are also available before the `--` separator:

| Option | Use |
|---|---|
| `--package ID VERSION` | add a package without putting `DependsOn` in the script |
| `--repository FEED` | add a package feed URL or local folder |
| `--offline` | resolve packages using available cache/local-feed contents |
| `--update-lock` | explicitly resolve and record the dependency graph again |
| `--target-framework TFM` | select package assets for a framework, default `net10.0` |
| `--runtime RID` | select package/native assets for a runtime, such as `win-x64` |

The resolver records dependency versions and content hashes under the selected cache directory. After an online
run succeeds, try `nscript run json.ns --offline` to check that the dependencies you need are available locally.
`--offline` does not install missing packages or restrict network operations performed by your own code. The package
asset selectors do not change the script engine's requirement for .NET 10. Package build targets are not run, so a
package that depends on MSBuild steps may need to be used through a normally built .NET library instead.

### Other dependency attributes

For reference, these forms can appear together at the start of a script:

```nemerle,ignore
[assembly: DependsOn("tools.dll")]                 // a local library, relative to the script
[assembly: DependsOn("Example.Package", "1.2.3")]  // a NuGet package at an exact version
[assembly: Repository("https://api.nuget.org/v3/index.json")]
[assembly: Import("helpers.ns")]                   // legacy script-import metadata
[assembly: CompilerOptions("-define:FAST")]
```

`CompilerOptions` accepts the supported define, warning, optimization and checked-arithmetic switches; it is not an
unrestricted `ncc` command line. Use dependency attributes for references and the CLI's `compile` command for output.

A referenced Nemerle library can also supply grammars, macros and the helpers they use:

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

## Cache and repeated runs

`nscript run` normally caches compiled code automatically; no extra command or flag is needed.
A cache hit still executes the script; it does not reuse the previous
result or its live instance. Code changes, local `.n` helpers, imported scripts and resolved dependency changes
participate in cache identity. Data read by ordinary runtime code is read again on each execution.

```sh
nscript run hello.ns --no-cache
nscript run hello.ns --cache-dir .script-cache
```

`--no-cache` recompiles and runs instead of using the compiled-code cache. It is useful when diagnosing compile-time
macro behavior that depends on external state. It does not disable the package cache. `--cache-dir` chooses the base
directory used for compiled artifacts, packages and the default REPL history. Without it, the CLI uses
`Nemerle/scripting` under the OS's local application-data directory; on Windows that is normally
`%LOCALAPPDATA%\Nemerle\scripting`.

## Compiling once and running the artifact

Use `compile` when you want to distribute a script without compiling source on the destination machine:

```sh
nscript compile greet.ns greet.dll
nscript run-compiled greet.dll -- Ada
```

The compile command saves the program without running its top-level code. `run-compiled` runs the saved code; editing
`greet.ns` afterward does not change that artifact until you compile it again.

Keep these outputs together when copying an artifact:

| Output | Keep it for |
|---|---|
| `greet.dll` | the compiled script |
| `greet.dll.script` | the metadata `run-compiled` needs to load it |
| `greet.dll.dependencies/`, when produced | bundled libraries and imported scripts |
| `greet.pdb`, when produced | original source locations in exception stacks |

Keep the base name unchanged when moving the set; the companion paths are recorded relative to it. The destination
needs .NET 10 and the `nscript` runtime files (`Nemerle.dll`, `Nemerle.Platform.dll`, `Nemerle.Scripting.dll` and the
runner/configuration files). An installed `nscript` supplies those. Running an artifact does not need the compiler,
macros, reference assemblies, original sources or the .NET SDK. It does not turn the DLL into a standalone native
executable. For an artifact of a custom script kind, keep that kind's library discoverable as described below.

## Interactive use: the REPL

Start `nscript repl`. Each successful submission can use previous declarations and results:

```text
>>> 40 : int
40
>>> res0 + 2
42
>>> :begin
... Twice(n : int) : int
... {
...   n * 2
... }
... :end
>>> Twice(21)
42
>>> :quit
```

`resN` refers to the value from successful submission `N`, starting at zero. Submission numbers include declarations;
not every submission produces a result. Unfinished expressions and brackets normally continue automatically. Use
`:begin` and `:end` when you want to collect a whole submission explicitly.

| Command | Meaning |
|---|---|
| `:begin`, `:end` | collect and submit a multiline block |
| `:history` | list the remembered source entries and their numbers |
| `:recall N` | display entry `N` without executing it |
| `:replay` | reset the live session and explicitly execute saved history |
| `:reset` | clear live declarations and results |
| `:quit` | leave the REPL |

Choose a history file with `nscript repl --history experiments.history`. Opening it reads the saved source, but does
not replay it or recreate its values. Use `:history` or `:recall` to inspect it, and `:replay` before adding new
submissions if you want to continue that saved session. Successful submissions save the current session's source
chain. History is not a snapshot of CLR objects; replay executes code again, including file writes and other effects.

Earlier statements do not rerun on every submission. New declarations can shadow old ones, while existing functions
and closures keep their earlier bindings. A compile error adds no declarations. A runtime failure also adds no
successful history entry, but effects that already happened are not undone. If an imported script changes during a
session, reset before replacing it; use a new REPL session when changing dependency versions.

## Script kinds

A library can declare a **kind of script**. A class marked `[ScriptDefinition(ext)]`
becomes the base class of every script whose file name ends in `ext`. The extension is written in its `.n` form and
covers both: `.build.n` is the kind of `deploy.build.ns` and of `deploy.build.n`. Those scripts need no
setup lines at all. This is useful for a family of build, migration or application scripts that should receive the
same helper methods and imports. Save this as `buildkind.n`:

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

Compile it to `buildkind.dll`, referencing `Nemerle.Scripting.dll` from your toolchain:

```sh
ncc buildkind.n -target:library -r:"path/to/toolchain/Nemerle.Scripting.dll" -out:buildkind.dll
```

Replace `path/to/toolchain` with your installed toolchain directory. Put `buildkind.dll` beside the following file,
save it as `deploy.build.ns`, and run `nscript run deploy.build.ns`:

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
script. To share a kind between directories, set that environment variable to the directories containing its
libraries: separate entries with `;` on Windows and `:` on Linux/macOS. For example, in PowerShell:

```powershell
$env:NEMERLE_SCRIPT_PATH = 'C:\MyTools\script-kinds'
nscript run deploy.build.ns
```

The longest matching suffix wins. A plain `deploy.ns` uses the ordinary script definition; `deploy.build.ns` requires
a discoverable `.build.n` kind. If the CLI reports that no kind declares a compound suffix, check the filename,
the kind library and the directories it lists. Merely putting the attribute in an uncompiled `.n` file is not enough.

## Embedding scripts in an application

Use the scripting API when an application needs to supply inputs, inspect diagnostics, read a result or call a
script's functions. Reference `Nemerle.Scripting.dll` and deploy the compiler/host toolchain files and `references/`
beside your application. Save this example as `embedding.n`; it looks for that reference folder beside its executable:

```nemerle,app
// ncc: -r:{toolchain}/Nemerle.Scripting.dll
// file: embedding.n
using System;
using System.IO;
using Nemerle.Scripting.contracts;
using Nemerle.Scripting.host;

def definition = ScriptDefinition();
definition.TargetReferenceDirectory = Path.Combine(AppContext.BaseDirectory, "references");
definition.Properties.Add("name", typeof(string));

def source = ScriptSource(
  "public Greet(who : string) : string { \"Hello, \" + who + \"!\" }\n"
  + "Greet(name)\n", "greeting.ns");
def host = ScriptHost();
def compilation = host.Compile(source, definition);
unless (compilation.Success)
{
  foreach (d in compilation.Diagnostics)
    Console.Error.WriteLine($"$(d.File):$(d.Line):$(d.Column): $(d.Message)");
  throw InvalidOperationException("Script did not compile")
}

def inputs = ScriptInputs();
inputs.Properties.Add("name", "Ada");
def result = host.Evaluate(compilation.Script, inputs);
when (result.Kind == ScriptResultKind.Error) throw result.Error;
when (result.Kind == ScriptResultKind.Value) Console.WriteLine(result.Value);

def greet = result.GetFunction("greeting.Greet", typeof(Func[string, string])) :> Func[string, string];
Console.WriteLine(greet("Grace"))
```

```text
Hello, Ada!
Hello, Grace!
```

For a first experiment, put the executable in your toolchain directory so its runtime dependencies and `references/`
are beside it. Replace `path/to/toolchain` in these commands:

```sh
ncc embedding.n -r:"path/to/toolchain/Nemerle.Scripting.dll" -out:"path/to/toolchain/embedding.dll" -launcher-
dotnet "path/to/toolchain/embedding.dll"
```

There are three separate jobs:

1. `ScriptDefinition` declares the names and types the script may use. The example supplies a `name : string` input.
2. `Compile` checks the script and returns diagnostics. A failed compilation has no usable script to evaluate.
3. `ScriptInputs` supplies actual values to `Evaluate`. Check `Kind` for `Value`, `Void` or `Error`; a successful value
   may be null. `GetFunction` binds a public function on that evaluation's script instance to a typed delegate.

Diagnostics can contain warnings even when compilation succeeds; an application can surface those as well.

The source filename supplies the owner in `greeting.Greet`. Missing, extra or wrongly typed inputs are host
configuration errors. Unlike the CLI, an embedded host does not automatically supply `args`; add an
`array[string]` property with that name and a matching input if your script uses it.

You can compile once and evaluate several times with different inputs. Each evaluation gets fresh script state;
objects supplied as inputs remain the host's actual objects, so mutations to them remain visible. A bound function
keeps the state of the evaluation it came from. For state carried between submissions, use `ScriptSession`, the same
API behind the REPL. Code runs with the application's ordinary process access.

`host.Save(compilation.Script, "greeting.dll")` saves a compiled artifact. `host.Load("greeting.dll", definition)`
loads it with a compatible definition, after which you supply inputs and evaluate it in the same way. Keep the
companion files described [above](#compiling-once-and-running-the-artifact).

For base classes, receiver objects, typed result contracts and host-controlled configuration, see the
scripting API guide in `scripting/README.md`.

### A script that extends the application's types

A script can add to an exported type of the application with `extend` (chapter 7): its fields, properties and
methods live in the object's extension slot, so the application's own objects have them, made before the script was
compiled as well as after:

```nemerle,app
// ncc: -r:{toolchain}/Nemerle.Scripting.dll
// file: extending.n
using System;
using System.IO;
using Nemerle.Scripting.contracts;
using Nemerle.Scripting.host;

export class Pen
{
  public mutable Width : int = 3;
}

def pen = Pen();
def definition = ScriptDefinition();
definition.TargetReferenceDirectory = Path.Combine(AppContext.BaseDirectory, "references");
definition.Properties.Add("pen", typeof(Pen));

def source = ScriptSource(
  "extend Pen { public mutable Style : string = \"plain\"; public Describe() : string { $\"$Style, $Width wide\" } }\n"
  + "pen.Style = \"bold\";\n"
  + "pen.Describe()\n", "styles.ns");
def host = ScriptHost();
def compilation = host.Compile(source, definition);
unless (compilation.Success)
{
  foreach (d in compilation.Diagnostics) Console.Error.WriteLine($"$(d.Line):$(d.Column): $(d.Message)");
  throw InvalidOperationException("Script did not compile")
}
def inputs = ScriptInputs();
inputs.Properties.Add("pen", pen);
def result = host.Evaluate(compilation.Script, inputs);
when (result.Kind == ScriptResultKind.Error) throw result.Error;
Console.WriteLine(result.Value)
```

```text
bold, 3 wide
```

## Common problems

| Symptom | Check |
|---|---|
| `nscript` is not found | run the installer, reopen your terminal, or invoke `dotnet path/to/nscript.exe` directly |
| The runner cannot find .NET 10 | use the installer to repair prerequisites; a different major runtime alone is not enough |
| A helper name is unknown | distinguish a `.n` module (`using`) from a `.ns` child (`import`), and check its registered path and visibility |
| A dependency DLL cannot be opened | check the `DependsOn` path relative to the script and keep the library's runtime dependencies available |
| No package resolver is configured | for `nscript`, install the NuGet adapter and its supporting libraries; for embedding, set `ScriptHostOptions.Resolver` |
| An offline package is unavailable | populate the selected cache/feed first; use the same `--cache-dir` for both runs |
| A compound filename has no matching kind | put its compiled kind library beside it or on `NEMERLE_SCRIPT_PATH` |
| A compiled script will not load | keep its `.dll.script` and `.dll.dependencies/` together with the DLL; recompile to rename the artifact |
| A REPL import changed or a dependency version conflicts | start a fresh session, or reset before replacing an imported script |

Diagnostics include the source file and location. Fix compile errors before looking for runtime failures; a failed
compile does not execute the script. For failures during execution, the original exception is reported, and keeping
the PDB with a saved artifact preserves useful source locations.

## Advanced: application languages in scripts

An application can expose its own languages to scripts by referencing the application's assembly. The script can use
the application's grammars and scopes without declaring copies of them. The application and its scripts share scope
values: the script reads what the application wrote, and the application sees what the script writes. A script can
also dial into the application's spaces.

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
definition.References.Add((System.Reflection.Assembly.GetEntryAssembly() :> System.Reflection.Assembly).Location);
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

Plugins can share the application's objects and scopes: writes made by the plugin are visible to the application.
Reference the application's actual assembly when compiling its plugins, rather than recompiling a separate copy of
its types. For the grammar, scope and dial APIs used here, see [Grammars and spaces](10-grammars.md).
