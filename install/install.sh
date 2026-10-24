#!/bin/sh
# Installs Nemerle for the current user: the compiler (ncc), scripting (nscript), Nitra, and the language server
# (nemerle-lsp), and the VS Code / VSCodium extension as a .vsix next to this script (install/nemerle-<version>.vsix),
# which it also installs in VS Code or VSCodium (--editor none: only the .vsix). Run it from a clone of the repository.
#
#   install/install.sh [--prefix DIR] [--bin DIR] [--build] [--no-lsp] [--no-debugger] [--editor auto|code|codium|none] [--uninstall]
#
# Needs only the .NET 10 runtime (https://dotnet.microsoft.com/download/dotnet/10.0). The editor extension's JavaScript
# dependencies are downloaded from the npm registry as package-lock.json pins them (checked against its hashes); npm
# itself is used only when that cannot be done.
set -eu

repo=$(cd "$(dirname "$0")/.." && pwd)
prefix="${XDG_DATA_HOME:-$HOME/.local/share}/nemerle"
bin="$HOME/.local/bin"
build=0
lsp=1
debugger=1
editor=auto
uninstall=0

say() { printf '%s\n' "$*"; }
# what was installed and what was skipped (and why), printed at the end; a file, as some steps run in a subshell
notes=$(mktemp)
trap 'rm -f "$notes"' EXIT
note() { printf '  %-10s %s\n' "$1" "$2" >>"$notes"; }
fail() { printf 'install: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) [ $# -ge 2 ] || fail "--prefix needs a directory"; prefix=$2; shift 2 ;;
    --bin) [ $# -ge 2 ] || fail "--bin needs a directory"; bin=$2; shift 2 ;;
    --build) build=1; shift ;;
    --no-lsp) lsp=0; shift ;;
    --no-debugger) debugger=0; shift ;;
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
  if [ "$(uname -s)" = Linux ]; then
    sh "$repo/install/install-file-icons.sh" --uninstall || true
  fi
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
note installed "the toolchain (ncc, nscript, Nitra) in $tc"

# --- the language server, compiled from source with the installed compiler ---
if [ $lsp = 1 ]; then
  say "Building the language server"
  set --   # the server's sources, kept whole even when the path has spaces
  for source_file in "$repo"/tools/language-server/*.n; do set -- "$@" "$source_file"; done
  dotnet "$tc/ncc.exe" -source-root:"$repo/tools/language-server" "$@" \
    -target:exe -out:"$tc/nemerle-lsp.exe" -target-references:"$tc/references" -no-color \
    -r:"$tc/Nemerle.Compiler.dll" -r:"$tc/Integrated.Nitra.Runtime.dll" -r:"$tc/Integrated.Nitra.Grammar.dll" \
    -r:"$tc/Integrated.Nitra.Compiler.dll" -r:"$tc/Integrated.DotNetLang.dll" -r:"$tc/Nemerle.Scripting.dll" >"$prefix/lsp-build.log" 2>&1 ||
    fail "building the language server failed; see $prefix/lsp-build.log"
  cp "$tc/ncc.runtimeconfig.json" "$tc/nemerle-lsp.runtimeconfig.json"
  note installed "the language server (nemerle-lsp)"
else
  note skipped "the language server, the debugger and the editor extension: --no-lsp"
fi

# --- launchers on PATH ---
launcher() {
  printf '#!/bin/sh\nexec dotnet "%s" %s"$@"\n' "$tc/$2" "$3" >"$bin/$1"
  chmod 755 "$bin/$1"
}
launcher ncc ncc.exe "-target-references:\"$tc/references\" "
launcher nscript nscript.exe ""
[ $lsp = 1 ] && launcher nemerle-lsp nemerle-lsp.exe ""
note installed "the commands in $bin"

if [ "$(uname -s)" = Linux ]; then
  if sh "$repo/install/install-file-icons.sh"; then
    note installed "file-manager icons for .n, .ns and .nproj"
  else
    note skipped "file-manager icons (install shared-mime-info and run install/install-file-icons.sh)"
  fi
fi

# --- the debugger: netcoredbg (MIT), which the extension debugs with; it looks in $prefix/tools/netcoredbg ---
if [ $lsp = 1 ] && [ $debugger = 1 ]; then
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) asset=netcoredbg-linux-amd64.tar.gz ;;
    Linux-aarch64|Linux-arm64) asset=netcoredbg-linux-arm64.tar.gz ;;
    Darwin-*) asset=netcoredbg-osx-amd64.tar.gz ;;
    *) asset="" ;;
  esac
  url="https://github.com/Samsung/netcoredbg/releases/latest/download/$asset"
  dbg="$prefix/tools/netcoredbg"
  if [ -z "$asset" ]; then say "Skipping the debugger: netcoredbg has no build for $(uname -s) $(uname -m)."
    note skipped "the debugger: netcoredbg has no build for $(uname -s) $(uname -m)"
  else
    rm -rf "$dbg"; mkdir -p "$dbg"
    if { command -v curl >/dev/null 2>&1 && curl -fsSL "$url" -o "$dbg/netcoredbg.tar.gz"; } ||
       { command -v wget >/dev/null 2>&1 && wget -q "$url" -O "$dbg/netcoredbg.tar.gz"; }; then
      tar -xzf "$dbg/netcoredbg.tar.gz" -C "$dbg" && rm -f "$dbg/netcoredbg.tar.gz"
      say "The debugger: $dbg/netcoredbg/netcoredbg"
      note installed "the debugger (netcoredbg) in $dbg"
    else
      rm -rf "$dbg"; say "Skipping the debugger: netcoredbg could not be downloaded from $url (debug later with netcoredbg on PATH)."
      note skipped "the debugger: netcoredbg could not be downloaded (debug later with netcoredbg on PATH)"
    fi
  fi
elif [ $lsp = 1 ]; then
  note skipped "the debugger: --no-debugger"
fi

# --- the editor extension's JavaScript dependencies, as package-lock.json pins them ---
download() {  # $1 = URL, $2 = file
  { command -v curl >/dev/null 2>&1 && curl -fsSL "$1" -o "$2"; } || { command -v wget >/dev/null 2>&1 && wget -q "$1" -O "$2"; }
}
sha512_hex() {  # a file's SHA-512, in hex
  if command -v sha512sum >/dev/null 2>&1; then sha512sum "$1" | cut -d ' ' -f 1
  elif command -v shasum >/dev/null 2>&1; then shasum -a 512 "$1" | cut -d ' ' -f 1
  elif command -v openssl >/dev/null 2>&1; then openssl dgst -sha512 -r "$1" | cut -d ' ' -f 1
  else return 1; fi
}
node_modules() {  # $1 = package-lock.json, $2 = the folder to put node_modules in; says why on stderr when it cannot
  # each package: its folder, the registry tarball and the tarball's SHA-512 (npm's "sha512-<base64>")
  entries=$(awk '
    /^    "node_modules\// { sub(/^    "/, ""); sub(/": \{.*/, ""); path = $0; url = ""; next }
    path != "" && /"resolved":/ { sub(/.*"resolved": "/, ""); sub(/".*/, ""); url = $0; next }
    path != "" && /"integrity":/ { sub(/.*"integrity": "/, ""); sub(/".*/, ""); print path, url, $0; path = ""; next }
    /^    }/ { path = "" }' "$1")
  [ -n "$entries" ] || { say "no packages in $1" >&2; return 1; }
  scratch=$(mktemp -d)
  printf '%s\n' "$entries" | while read -r path url integrity; do
    case "$integrity" in sha512-*) ;; *) say "$path has no sha512 hash in the lock file" >&2; exit 1 ;; esac
    download "$url" "$scratch/package.tgz" || { say "$url could not be downloaded" >&2; exit 1; }
    want=$(printf '%s' "${integrity#sha512-}" | base64 -d 2>/dev/null | od -An -v -tx1 | tr -d ' \n')
    have=$(sha512_hex "$scratch/package.tgz") || { say "no sha512sum, shasum or openssl to check the download" >&2; exit 1; }
    [ -n "$want" ] && [ "$want" = "$have" ] || { say "$url does not match its hash in the lock file" >&2; exit 1; }
    mkdir -p "$2/$path"
    tar -xzf "$scratch/package.tgz" -C "$2/$path" --strip-components=1 || { say "$url could not be unpacked" >&2; exit 1; }
  done
  status=$?
  rm -rf "$scratch"
  return $status
}

# --- the editor extension: a .vsix (next to this script) that carries the server, installed by the editor ---
make_vsix() {  # prints the .vsix's path; nothing (and a reason on stderr) when it cannot be made
  src="$repo/tools/language-server/vscode"
  field() { sed -n "s/^  \"$1\": \"\([^\"]*\)\".*/\1/p" "$src/package.json" | head -n 1; }
  name=$(field name); version=$(field version); publisher=$(field publisher)
  vsix="$repo/install/$name-$version.vsix"
  work=$(mktemp -d); ext="$work/extension"; mkdir -p "$ext"
  cp "$src/package.json" "$src/extension.js" "$src/language-configuration.json" "$src/README.md" "$ext/"
  cp -R "$src/syntaxes" "$src/images" "$ext/"
  cp "$repo/LICENSES/GPL-2.0-or-later.txt" "$ext/LICENSE.txt"
  # the client library, the extension's one production dependency, and what it uses: from the npm registry as the lock
  # file pins them; npm only when that fails
  if ! why=$(node_modules "$src/package-lock.json" "$ext" 2>&1); then
    rm -rf "$ext/node_modules"
    if command -v npm >/dev/null 2>&1; then
      say "The extension's dependencies could not be fetched directly ($why); using npm" >&2
      cp "$src/package-lock.json" "$ext/"
      (cd "$ext" && npm ci --omit=dev --no-audit --no-fund --silent >/dev/null 2>&1) ||
        { rm -rf "$work"; say "Skipping the editor extension: its dependencies could not be fetched ($why), and npm ci failed." >&2
          note skipped "the editor extension: its dependencies could not be fetched ($why), nor by npm"; return 1; }
      rm -f "$ext/package-lock.json"
    else
      rm -rf "$work"; say "Skipping the editor extension: its dependencies could not be fetched ($why)." >&2
      note skipped "the editor extension: its dependencies could not be fetched ($why)"; return 1
    fi
  fi
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
    rm -rf "$work"; say "Skipping the editor extension: python3 or zip is needed to write the .vsix." >&2
    note skipped "the editor extension: python3 or zip is needed to write the .vsix"; return 1
  fi
  rm -rf "$work"
  say "The editor extension: $vsix (install it by hand with Extensions > ... > Install from VSIX)" >&2
  note installed "the editor extension package: $vsix"
  printf '%s\n' "$vsix"
}
install_vsix() {  # $1 = the editor's command, $2 = its extensions directory, $3 = the .vsix
  # the old copied-in folders go first; the editor's own command installs the package (with a time limit: a
  # command that is the editor's GUI rather than its CLI does not return)
  rm -rf "$2/$extension" "$2/nemerle.nemerle-nitra-0.1.0"
  limit=""; command -v timeout >/dev/null 2>&1 && limit="timeout 180"
  if $limit "$1" --install-extension "$3" --force >/dev/null 2>&1; then say "Installed the extension in $1"; note installed "the extension in $1"
  else say "$1 could not install $3; install it by hand from the Extensions view."; note skipped "the extension in $1: $1 --install-extension failed (install the .vsix by hand)"; fi
}
if [ $lsp = 1 ]; then
  if vsix=$(make_vsix); then
    case "$editor" in
      auto)
        command -v code >/dev/null 2>&1 && install_vsix code "$HOME/.vscode/extensions" "$vsix"
        command -v codium >/dev/null 2>&1 && install_vsix codium "$HOME/.vscode-oss/extensions" "$vsix"
        command -v code >/dev/null 2>&1 || command -v codium >/dev/null 2>&1 ||
          note skipped "installing the extension in an editor: no code or codium on PATH"
        true ;;
      code) install_vsix code "$HOME/.vscode/extensions" "$vsix" ;;
      codium) install_vsix codium "$HOME/.vscode-oss/extensions" "$vsix" ;;
      none) note skipped "installing the extension in an editor: --editor none" ;;
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
say "Summary:"
cat "$notes"
say ""
say "ncc, nscript$([ $lsp = 1 ] && printf ' and nemerle-lsp') are in $bin. Next: doc/book/src/SUMMARY.md"
