# Introduction

Nemerle is a statically typed language for .NET. It mixes functional, object-oriented and imperative styles, infers
types for you, and has a macro system strong enough to add new syntax to the language. This book teaches the language
as it is in this revival: .NET 10, a file is its namespace, Nitra grammars built in, and scripting.

## Who this book is for

You should know at least one programming language. You don't need to know C# or .NET. Where .NET details matter, the
book explains them.

## How to read it

The chapters build on each other. Chapters 1–8 cover the everyday language: values, functions, data, pattern matching,
classes, files and errors. Chapters 9–11 cover what makes Nemerle different: macros, grammars that extend the language,
and scripts. Chapter 12 is about using .NET libraries and being used from C#.

Every example in this book is compiled and run by `tests/check-book.py`, and its output is compared with what the book
shows. If an example is here, it works on the current compiler.

## Conventions

Code looks like this:

```nemerle
System.Console.WriteLine("Hello from the book")
```

and its output like this:

```text
Hello from the book
```

When a file name matters, the example starts with a comment such as `// file: util/text.n`.
