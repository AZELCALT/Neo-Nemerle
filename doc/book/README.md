# The Nemerle Book

The language guide for this fork. Start at [src/SUMMARY.md](src/SUMMARY.md), or build the HTML book from the
repository root. The build needs Python 3; Rust, Cargo, Node and the .NET SDK are not needed to render the book.

On Windows, in PowerShell or Command Prompt:

```powershell
py -3 build/build-book.py
```

On Linux or macOS:

```sh
python3 build/build-book.py
```

Open `doc/book/book/index.html` in a browser. To serve it locally, run `py -3 -m http.server 8000 --directory doc/book/book`
on Windows, or the same command with `python3` elsewhere, then visit `http://localhost:8000`.

The build downloads the official **mdBook 0.5.4 prebuilt executable**, verifies its pinned SHA-256 digest, and caches
it under `out/book-tools/`. Later builds reuse that archive; `--offline` requires an existing cache and never
downloads. Prebuilt targets cover Windows x64, Linux x64/ARM64, and macOS Intel/Apple silicon. Windows builds use
`mdbook.exe` directly; no Rust compilation or C/C++ build tools are involved. Other platforms can provide a compatible
executable with `--mdbook PATH`.

You can also extract a binary from the [official releases](https://github.com/rust-lang/mdBook/releases/tag/v0.5.4)
yourself and run:

```powershell
py -3 build/build-book.py --mdbook "C:\Tools\mdbook\mdbook.exe"
```

An installed mdBook still works with `mdbook build doc/book`. We keep the existing Markdown, `SUMMARY.md`, and
`book.toml`; Cargo is only needed if you choose to compile mdBook itself from source, as described in the
[mdBook installation guide](https://rust-lang.github.io/mdBook/guide/installation.html).

Rendering the HTML and checking the language examples are separate steps. Runnable `nemerle` code blocks are tests:
`tests/check-book.py` compiles and runs them and compares the output with the `text` block that follows. That step
needs the Nemerle toolchain and .NET; `./bootstrap` runs it. To check examples with a toolchain you already built:

```sh
python3 tests/check-book.py --toolchain out/bootstrap/toolchain --references boot/coreclr/references
```

On Windows use `py -3` instead of `python3`. The block tags, including examples deliberately marked `ignore`, are
documented at the top of the test script.

`python3 tests/check-script-book-usage.py --toolchain out/bootstrap/toolchain` also checks the scripting chapter's
terminal workflows: arguments, relocated artifacts, child imports, the printed REPL transcript, history and errors.
