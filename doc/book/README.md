# The Nemerle Book

The language guide for this fork, in the style of *The Rust Programming Language*. Start at
[src/SUMMARY.md](src/SUMMARY.md), or build HTML with [mdBook](https://rust-lang.github.io/mdBook/):

```sh
mdbook build doc/book        # output in doc/book/book/
```

Every `nemerle` code block is a test. `tests/check-book.py` compiles and runs it and compares the output with the
`text` block that follows; `./bootstrap` runs it. The block tags are documented at the top of that script.
