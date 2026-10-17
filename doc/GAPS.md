# Known gaps

Open edges of the current design, each with what happens today. None of them lets an invalid program through silently
unless it says so.

## Top-level code and state

- **Threads: indirect use is not proven.** In an imported file's top-level code, work started through `Thread`, `Task`,
  `Parallel`, `ThreadPool` or `Timer` is an error only when it refers to the file's own members (in its lambda too)
  and the top-level code waits. Work that reaches the file only through another file's function gets the warning, not
  the error, though it can deadlock the same way.
- **Threads: any wait counts.** A `Wait`, `Join`, `.Result` or `GetResult` anywhere in the top-level code counts as
  waiting for every task started there, not only for the task it is called on.
- **Type changes: an open use type passes.** When a top-level value changes type, a read in a function takes the type
  its use needs. A use that leaves the type open (it accepts anything) reads as `object` and is not reported.
- **Type changes: names are matched by spelling.** A function parameter with the value's name hides it, but a lambda
  parameter or a local of the same name inside a function is still read as the top-level value.
- **The inference pass expands macros twice.** It types a copy of the top-level code, so macros used there expand once
  for it and once for the real code. The compiler's own macros (spaces, scopes, dials) are safe to repeat; a user
  macro with side effects sees both expansions. When the pass fails, a value's type falls back to its first
  initializer, as before the pass existed.
- **Tuple destructuring stays local.** `def (a, b) = ...` at the top level binds locals, not state; `def pair = (a, b)`
  is the form functions can reach. A nicer way to reference tuple parts is not designed yet.

## Scopes and spaces

- **Scope storage is per runtime copy of `Nemerle.dll`.** Scripts share the host's storage because the script loader
  takes `Nemerle.dll` from the host. A plugin loaded by other means with its own copy of `Nemerle.dll` gets its own,
  empty storage.
- **The top-level rule for spaces is token-level.** A space must stand at the top level of its file; the check looks
  at the tokens before it, not at the parsed tree.

## Tooling

- **Windows installer:** `install.ps1` and `install.cmd` were run on Windows once; a .NET assembly version mismatch
  there still needs a small fix. The VS Code extension's Windows launch (`shell: true`) is untested.
