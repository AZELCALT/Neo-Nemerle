#!/bin/sh
# Installs Nemerle for the current user: the compiler (ncc), scripting (nscript), Nitra, and the language server
# (nemerle-lsp), and the VS Code / VSCodium extension as a .vsix next to this script (install/nemerle-<version>.vsix),
# which it also installs in VS Code or VSCodium (--editor none: only the .vsix). Run it from a clone of the repository.
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
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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

# --- the editor extension: a .vsix (next to this script) that carries the server, installed by the editor ---
make_vsix() {  # prints the .vsix's path; nothing (and a reason on stderr) when it cannot be made
  command -v npm >/dev/null 2>&1 || { say "Skipping the editor extension: npm is needed to fetch its one dependency." >&2; return 1; }
  src="$repo/tools/language-server/vscode"
  field() { sed -n "s/^  \"$1\": \"\([^\"]*\)\".*/\1/p" "$src/package.json" | head -n 1; }
  name=$(field name); version=$(field version); publisher=$(field publisher)
  vsix="$repo/install/$name-$version.vsix"
  work=$(mktemp -d); ext="$work/extension"; mkdir -p "$ext"
  cp "$src/package.json" "$src/extension.js" "$src/language-configuration.json" "$src/README.md" "$ext/"
  cp -R "$src/syntaxes" "$src/images" "$ext/"
  cp "$repo/LICENSES/GPL-2.0-or-later.txt" "$ext/LICENSE.txt"
  # the client library, the extension's one production dependency
  (cd "$ext" && npm install --omit=dev --no-audit --no-fund --silent >/dev/null 2>&1) ||
    { rm -rf "$work"; say "Skipping the editor extension: npm install failed." >&2; return 1; }
  rm -f "$ext/package-lock.json"
  # the server: the installed toolchain with nemerle-lsp.exe and its reference assemblies
  cp -R "$tc" "$ext/server"
  engine=$(sed -n 's/^ *"vscode": "\([^"]*\)".*/\1/p' "$src/package.json" | head -n 1)
  cat >"$work/extension.vsixmanifest" <<MANIFEST
<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="$name" Version="$version" Publisher="$publisher" />
    <DisplayName>Nemerle</DisplayName>
    <Description xml:space="preserve">$(field description)</Description>
    <Categories>Programming Languages</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Icon>extension/images/icon.png</Icon>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="$engine" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace" />
      <Property Id="Microsoft.VisualStudio.Code.LocalizedLanguages" Value="" />
    </Properties>
    <License>extension/LICENSE.txt</License>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code" /></Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE.txt" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Icons.Default" Path="extension/images/icon.png" Addressable="true" />
  </Assets>
</PackageManifest>
MANIFEST
  types=$(find "$work" -type f -name '*.*' | sed 's/.*\.//' | tr 'A-Z' 'a-z' | sort -u | while read -r e; do
    case "$e" in
      json) k=application/json ;; js) k=application/javascript ;; md) k=text/markdown ;; txt) k=text/plain ;;
      png) k=image/png ;; svg) k=image/svg+xml ;; vsixmanifest|xml) k=text/xml ;; *) k=application/octet-stream ;;
    esac
    printf '<Default Extension=".%s" ContentType="%s" />' "$e" "$k"
  done)
  printf '<?xml version="1.0" encoding="utf-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">%s</Types>\n' "$types" >"$work/[Content_Types].xml"
  rm -f "$vsix"
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$work" "$vsix" <<'ZIP'
import os, sys, zipfile
work, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for top, _, files in os.walk(work):
        for f in sorted(files):
            path = os.path.join(top, f)
            z.write(path, os.path.relpath(path, work).replace(os.sep, '/'))
ZIP
  elif command -v zip >/dev/null 2>&1; then
    (cd "$work" && zip -qr "$vsix" .)
  else
    rm -rf "$work"; say "Skipping the editor extension: python3 or zip is needed to write the .vsix." >&2; return 1
  fi
  rm -rf "$work"
  say "The editor extension: $vsix (install it by hand with Extensions > ... > Install from VSIX)" >&2
  printf '%s\n' "$vsix"
}
install_vsix() {  # $1 = the editor's command, $2 = its extensions directory, $3 = the .vsix
  # the old copied-in folders go first; the editor's own command installs the package (with a time limit: a
  # command that is the editor's GUI rather than its CLI does not return)
  rm -rf "$2/$extension" "$2/nemerle.nemerle-nitra-0.1.0"
  limit=""; command -v timeout >/dev/null 2>&1 && limit="timeout 180"
  if $limit "$1" --install-extension "$3" --force >/dev/null 2>&1; then say "Installed the extension in $1"
  else say "$1 could not install $3; install it by hand from the Extensions view."; fi
}
if [ $lsp = 1 ]; then
  if vsix=$(make_vsix); then
    case "$editor" in
      auto)
        command -v code >/dev/null 2>&1 && install_vsix code "$HOME/.vscode/extensions" "$vsix"
        command -v codium >/dev/null 2>&1 && install_vsix codium "$HOME/.vscode-oss/extensions" "$vsix"
        true ;;
      code) install_vsix code "$HOME/.vscode/extensions" "$vsix" ;;
      codium) install_vsix codium "$HOME/.vscode-oss/extensions" "$vsix" ;;
      none) ;;
      *) fail "unknown editor $editor" ;;
    esac
  fi
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
