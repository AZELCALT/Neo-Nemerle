#!/bin/sh
# Installs Nemerle for the current user: the compiler (ncc), scripting (nscript), Nitra, and the language server
# (nemerle-lsp), plus optionally the VS Code / VSCodium extension. Run it from a clone of the repository.
#
#   install/install.sh [--prefix DIR] [--bin DIR] [--build] [--no-lsp] [--editor auto|code|codium|none] [--uninstall]
#
# Needs only the .NET 10 runtime (https://dotnet.microsoft.com/download/dotnet/10.0). The editor extension also needs npm.
set -eu

repo=$(cd "$(dirname "$0")/.." && pwd)
prefix="${XDG_DATA_HOME:-$HOME/.local/share}/nemerle"
bin="$HOME/.local/bin"
build=0
lsp=1
editor=auto
uninstall=0

say() { printf '%s\n' "$*"; }
fail() { printf 'install: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) [ $# -ge 2 ] || fail "--prefix needs a directory"; prefix=$2; shift 2 ;;
    --bin) [ $# -ge 2 ] || fail "--bin needs a directory"; bin=$2; shift 2 ;;
    --build) build=1; shift ;;
    --no-lsp) lsp=0; shift ;;
    --editor) [ $# -ge 2 ] || fail "--editor needs auto, code, codium or none"; editor=$2; shift 2 ;;
    --uninstall) uninstall=1; shift ;;
    -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) fail "unknown option $1 (see --help)" ;;
  esac
done

# the extension's folder (and the one of its first version, removed on install and uninstall)
extension=neo-nemerle.nemerle-0.2.0
extension_dirs() {
  for root in "$HOME/.vscode/extensions" "$HOME/.vscode-oss/extensions"; do
    printf '%s\n' "$root/$extension" "$root/nemerle.nemerle-nitra-0.1.0"
  done
}

if [ $uninstall = 1 ]; then
  rm -rf "$prefix"
  for tool in ncc nscript nemerle-lsp; do rm -f "$bin/$tool"; done
  extension_dirs | while read -r dir; do rm -rf "$dir"; done
  say "Nemerle removed from $prefix and $bin."
  exit 0
fi

# --- the .NET 10 runtime ---
command -v dotnet >/dev/null 2>&1 || fail "dotnet not found. Install the .NET 10 runtime: https://dotnet.microsoft.com/download/dotnet/10.0"
dotnet --list-runtimes | grep -q '^Microsoft.NETCore.App 10\.' ||
  fail "the .NET 10 runtime is missing (found: $(dotnet --list-runtimes | sed -n 's/^Microsoft.NETCore.App \([^ ]*\).*/\1/p' | tr '\n' ' ')). Install it: https://dotnet.microsoft.com/download/dotnet/10.0"

# --- which toolchain ---
source="$repo/boot/coreclr"
if [ $build = 1 ]; then
  say "Building from source (./bootstrap --quick); this takes a few minutes..."
  "$repo/bootstrap" --quick || fail "the build failed; see $repo/out/bootstrap/logs"
  source="$repo/out/bootstrap/toolchain"
fi
[ -f "$source/ncc.exe" ] || fail "no toolchain in $source"

say "Installing the toolchain from $source to $prefix"
mkdir -p "$prefix" "$bin"
rm -rf "$prefix/toolchain"
cp -R "$source" "$prefix/toolchain"
tc="$prefix/toolchain"

# --- the language server, compiled from source with the installed compiler ---
if [ $lsp = 1 ]; then
  say "Building the language server"
  set --   # the server's sources, kept whole even when the path has spaces
  for source_file in "$repo"/tools/language-server/*.n; do set -- "$@" "$source_file"; done
  dotnet "$tc/ncc.exe" -source-root:"$repo/tools/language-server" "$@" \
    -target:exe -out:"$tc/nemerle-lsp.exe" -target-references:"$tc/references" -no-color \
    -r:"$tc/Nemerle.Compiler.dll" -r:"$tc/Integrated.Nitra.Runtime.dll" -r:"$tc/Integrated.Nitra.Grammar.dll" \
    -r:"$tc/Integrated.Nitra.Compiler.dll" -r:"$tc/Integrated.DotNetLang.dll" >"$prefix/lsp-build.log" 2>&1 ||
    fail "building the language server failed; see $prefix/lsp-build.log"
  cp "$tc/ncc.runtimeconfig.json" "$tc/nemerle-lsp.runtimeconfig.json"
fi

# --- launchers on PATH ---
launcher() {
  printf '#!/bin/sh\nexec dotnet "%s" %s"$@"\n' "$tc/$2" "$3" >"$bin/$1"
  chmod 755 "$bin/$1"
}
launcher ncc ncc.exe "-target-references:\"$tc/references\" "
launcher nscript nscript.exe ""
[ $lsp = 1 ] && launcher nemerle-lsp nemerle-lsp.exe ""

# --- the editor extension ---
install_extension() {  # $1 = editor command, $2 = its extensions directory
  command -v npm >/dev/null 2>&1 || { say "Skipping the $1 extension: npm is needed to install its one dependency."; return; }
  dir="$2/$extension"
  rm -rf "$dir" "$2/nemerle.nemerle-nitra-0.1.0"
  mkdir -p "$dir"
  cp "$repo/tools/language-server/vscode/package.json" "$repo/tools/language-server/vscode/extension.js" \
     "$repo/tools/language-server/vscode/language-configuration.json" "$repo/tools/language-server/vscode/README.md" "$dir/"
  cp -R "$repo/tools/language-server/vscode/syntaxes" "$dir/"
  (cd "$dir" && npm install --omit=dev --no-audit --no-fund --silent >/dev/null 2>&1) ||
    { rm -rf "$dir"; say "Skipping the $1 extension: npm install failed."; return; }
  say "Installed the $1 extension in $dir"
}
if [ $lsp = 1 ]; then
  case "$editor" in
    auto)
      command -v code >/dev/null 2>&1 && install_extension code "$HOME/.vscode/extensions"
      command -v codium >/dev/null 2>&1 && install_extension codium "$HOME/.vscode-oss/extensions"
      true ;;
    code) install_extension code "$HOME/.vscode/extensions" ;;
    codium) install_extension codium "$HOME/.vscode-oss/extensions" ;;
    none) ;;
    *) fail "unknown editor $editor" ;;
  esac
fi

# --- check it works ---
check=$(mktemp -d)
printf 'System.Console.WriteLine("Nemerle is installed")\n' >"$check/hello.n"
output=$("$bin/nscript" run "$check/hello.n" --no-cache 2>&1) || fail "the installed nscript does not run: $output"
rm -rf "$check"
say "$output"

case ":$PATH:" in
  *":$bin:"*) ;;
  *) say ""; say "Add $bin to your PATH, for example in ~/.profile:"; say "  export PATH=\"$bin:\$PATH\"" ;;
esac
say ""
say "ncc, nscript$([ $lsp = 1 ] && printf ' and nemerle-lsp') are in $bin. Next: doc/book/src/SUMMARY.md"
