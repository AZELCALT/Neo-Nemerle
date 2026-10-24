#!/bin/sh
# Linux file-manager icons. No editor or compiler installation is required.
# Usage: sh install/install-file-icons.sh [--data-dir DIR] [--uninstall]
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd)
data_dir=${XDG_DATA_HOME:-$HOME/.local/share}
uninstall=0
while [ $# -gt 0 ]; do
  case "$1" in
    --data-dir) [ $# -ge 2 ] || { echo '--data-dir needs a directory' >&2; exit 1; }; data_dir=$2; shift 2 ;;
    --uninstall) uninstall=1; shift ;;
    -h|--help) sed -n '2,3p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done
command -v update-mime-database >/dev/null 2>&1 || {
  echo 'File icons need update-mime-database (the shared-mime-info package).' >&2; exit 1;
}
mime_dir="$data_dir/mime"
icons="$data_dir/icons/hicolor/scalable/mimetypes"
if [ "$uninstall" = 1 ]; then
  rm -f "$mime_dir/packages/neo-nemerle.xml"
  for icon in text-x-nemerle text-x-nemerle-script application-x-nemerle-project; do
    rm -f "$icons/$icon.svg"
  done
else
  mkdir -p "$mime_dir/packages" "$icons"
  cp "$repo/install/nemerle-mime.xml" "$mime_dir/packages/neo-nemerle.xml"
  cp "$repo/doc/assets/logo/nemerle.svg" "$icons/text-x-nemerle.svg"
  cp "$repo/doc/assets/logo/nemerle-script.svg" "$icons/text-x-nemerle-script.svg"
  cp "$repo/doc/assets/logo/nemerle-project.svg" "$icons/application-x-nemerle-project.svg"
fi
if [ -d "$mime_dir/packages" ]; then update-mime-database "$mime_dir"; fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "$data_dir/icons/hicolor" >/dev/null 2>&1 || true
fi
if [ "$uninstall" = 1 ]; then
  echo "Nemerle file icons removed from $data_dir."
else
  echo "Nemerle file icons installed in $data_dir. Refresh or reopen the file manager."
fi
