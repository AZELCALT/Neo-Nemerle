# How this is built

The revived Nemerle is designed by azelcalt and built with an AI assistant (Claude, by Anthropic, through Claude
Code). This page says plainly who does what, how changes are checked, and what is supported, so nobody has to guess.

## Who does what

**The design is the maintainer's.** What the language means, how its features work together, the architecture of
the compiler and its tools, what is in and out of scope, names, priorities, licensing and the logo: these are decided
by azelcalt. The AI's suggestions are often rejected or corrected. Examples from the history of this repository:

- the `dial:.file.space::member` syntax, rewritten several times until it matched the intended design;
- scopes as shared storage keyed by file, after the AI first built them otherwise;
- two global (`export`) types with the same name are an error, not "the more specific one wins" as the AI proposed;
- rebinding a top-level value to another type is checked against everything that depends on it, not merely warned;
- threads in a file's top-level code are judged by the calls they make (and proven across files), not by names;
- projects (`.nproj`) read both the declarative format and upstream's MSBuild files, and fetch target reference
  assemblies at build time rather than vendoring them;
- the positioning: a complete language for the .NET ecosystem, not a companion to C#.

**The AI implements.** It writes code, tests and documentation, runs the builds, finds and fixes bugs, measures, and
lays out options with their trade-offs when there is a decision to make.

## The working pattern

1. The maintainer states the intent: what a feature is for and how it must behave.
2. The AI implements it, with tests.
3. The maintainer looks at how it behaves and corrects it where the result does not match the intent. Design surfaces
   this way: an intent is only fully visible once something is built against it.
4. The corrected rule is written down: in the book (`doc/book`), in the commit message, and in `doc/GAPS.md` if an edge
   is left open.

## How every change is checked

Nothing lands without `./bootstrap` passing. It rebuilds the toolchain from the pinned compiler, checks that the new
compiler rebuilds itself, and runs every suite under `tests/`: file modules and top-level state, projects and
packages, target frameworks (run on Mono), the debugger, the installers, the language server, the editor extension,
scripting, the Nitra suites with a differential against the reference implementation, and every example in the book
compiled and run. A bug found while building something else gets its own fix and its own test.

Commits made with the AI carry a `Co-Authored-By` trailer, so the history shows which ones they are.

## What is supported

**Supported is what is declared:** the language and tools as the book (`doc/book`), the READMEs and the tools' own
help describe them.

**Everything else may change or break without notice.** That includes:

- the open edges listed in [GAPS.md](GAPS.md): they are known and tracked, and will be closed, which can change what
  happens there today;
- behaviour no document describes, even when it happens to work;
- the compiler's internals: generated names (`_N_...`), the internal macros (`__state_*`, `__module_init`, `__g`), the
  layout of the continuation section, and the language server's and checker's private protocols.

If code relies on a gap or on undocumented behaviour, expect it to stop working in a later version. Code that relies
on what is declared is what releases keep working.
