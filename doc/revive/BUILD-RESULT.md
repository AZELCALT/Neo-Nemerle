# Baseline result

This report preserves the original baseline. For the subsequent implementation and rebuilt-compiler checks, see `PLATFORM-REFACTOR-RESULT.md`.

Date: 2026-10-08. Artix x86-64, Mono 6.12.0, xbuild 14.0, .NET SDK 10.0.112.
Upstream commit: b5f3b410cce63ab08da44ea42b58bbd4822a7ce8.

## Successful check

Run `bash baseline/run-in-memory.sh` from the workspace root.

This builds a C# host with Mono's C# compiler, embeds the checked-in Nemerle bootstrap compiler, compiles hello.n into a dynamic assembly and invokes its generated entry point. It prints `Nemerle executed inside a C# host`.

This establishes basic in-memory compilation and C# hosting on Mono. It does not validate the rebuilt compiler, modern CoreCLR support, persistent sessions, unloading, or native engine integration.

## Full build attempt

From nemerle/:

```sh
xbuild NemerleAll.nproj /p:TargetFrameworkVersion=v4.5 /p:Configuration=Release /t:Stage4 /tv:4.0 /verbosity:minimal
```

Two compatibility fixes were made:

- Nemerle.XBuild.Tasks.csproj: replace unavailable version-2 build assembly references with available Engine/Framework and version-4 Tasks/Utilities references.
- tools/msbuild-task/ncc-mono: quote the argument passed to dirname so the workspace path containing spaces works.

After these fixes, the build reaches the bootstrap compiler, but Mono aborts while finalizing emitted runtime types (`custom-attrs.c:718`, `ctor_method`). Later errors about missing NemerleAttribute follow the failed runtime build and are not evidence of a separate initial cause.

A separate standalone Hello World reaches assembly saving but aborts in Mono metadata emission (`sre-encode.c:290`, `count > 0`). Both boot/ and boot-4.0/ fail to save this example. Using `-use-loaded-corlib` did not resolve the boot-4.0 saving failure.

Follow-up investigation established two independent causes: empty return custom-modifier arrays crash Mono's persisted method emission, and finalizing a type before its dynamically generated attribute type crashes custom-attribute processing. See `investigation/README.md` for reproductions and the actual self-build trace.

The modifier getters are fixed in source. A temporary patched copy of the bootstrap compiler now saves and executes Hello World; original bootstrap binaries remain unchanged. Full self-building still fails on attribute finalization order, whose compiler scheduling fix is pending.

Detailed logs are preserved beside this report. Original temporary logs were /tmp/nemerle-baseline-build.log, /tmp/nemerle-alternate-build.log and /tmp/nemerle-smoke/loaded-corlib.log.

Next implementation: dependency-aware attribute finalization. File-module changes should wait for a reliable self-build.
