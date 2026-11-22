#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR=/opt/browseros
BIN_LINK=/usr/local/bin/browseros-app
INSTALLER_DIR=/tmp/installer
mkdir -p "$INSTALL_DIR" "$INSTALLER_DIR"

# Default: BrowserOS Neo Linux x64 .deb (preferred in this container).
BROWSEROS_INSTALLER_URL="${BROWSEROS_INSTALLER_URL:-https://cdn.browseros.com/download/BrowserOS_neo.deb}"
BROWSEROS_APPIMAGE_URL="${BROWSEROS_APPIMAGE_URL:-https://cdn.browseros.com/download/BrowserOS_neo.AppImage}"

download_installer() {
  local url="$1"
  local out="$INSTALLER_DIR/$(basename "${url%%\?*}")"
  echo "No local supported installer found; downloading: $url" >&2
  curl -fsSL --retry 3 --retry-delay 2 -o "$out" "$url"
  echo "$out"
}

shopt -s nullglob
files=("$INSTALLER_DIR"/*)
shopt -u nullglob

# Prefer local .deb on Debian; fall back to local .AppImage. Ignore Windows installers.
deb_installer=""
appimage_installer=""
for f in "${files[@]}"; do
  case "${f,,}" in
    *.deb) [ -z "$deb_installer" ] && deb_installer="$f" ;;
    *.appimage) [ -z "$appimage_installer" ] && appimage_installer="$f" ;;
    *.exe) echo "Skipping Windows installer (not supported in Linux container): $f" ;;
  esac
done

installer="${deb_installer:-$appimage_installer}"

if [ -z "$installer" ]; then
  if [ -n "$BROWSEROS_INSTALLER_URL" ]; then
    installer="$(download_installer "$BROWSEROS_INSTALLER_URL")"
  elif [ -n "$BROWSEROS_APPIMAGE_URL" ]; then
    installer="$(download_installer "$BROWSEROS_APPIMAGE_URL")"
  else
    echo "ERROR: No supported Linux installer found and no BROWSEROS_INSTALLER_URL set."
    echo "Supported: .deb, .AppImage. Windows .exe is not supported."
    exit 1
  fi
fi

echo "Installing BrowserOS from: $installer"
case "${installer,,}" in
  *.deb)
    apt-get update
    apt-get install -y --no-install-recommends "$installer"
    rm -rf /var/lib/apt/lists/*
    ;;
  *.appimage)
    chmod +x "$installer"
    # Extract AppImage to avoid FUSE requirement in containers.
    cd /tmp
    "$installer" --appimage-extract >/tmp/appimage-extract.log 2>&1 || {
      echo "AppImage extraction failed; trying to run as-is."
      cp "$installer" "$BIN_LINK"
      chmod +x "$BIN_LINK"
      exit 0
    }
    rm -rf "$INSTALL_DIR"
    mv /tmp/squashfs-root "$INSTALL_DIR"
    # Common AppRun/desktop entry names
    if [ -x "$INSTALL_DIR/AppRun" ]; then
      ln -sf "$INSTALL_DIR/AppRun" "$BIN_LINK"
    else
      bin="$(find "$INSTALL_DIR" -maxdepth 3 -type f -perm -111 \( -iname '*browseros*' -o -iname '*chrome*' -o -iname '*browser*' \) | head -n1 || true)"
      if [ -n "$bin" ]; then
        ln -sf "$bin" "$BIN_LINK"
      else
        echo "ERROR: Could not locate executable in extracted AppImage."
        exit 1
      fi
    fi
    ;;
  *)
    echo "ERROR: Unsupported installer type: $installer"
    exit 1
    ;;
esac

echo "BrowserOS installation completed."