#!/usr/bin/env bash
# No shell initialization, sudo, system Python writes, or project deletion.
set -euo pipefail
repo_url='https://github.com/CarlFriGauss/clipharbor.git'
install_repo=0
setup_only=0
update=0
for arg in "$@"; do
    case "$arg" in
        --install) install_repo=1 ;;
        --setup-only) setup_only=1 ;;
        --update-dependencies) update=1 ;;
        *) printf 'Unknown option: %s\n' "$arg" >&2; exit 1 ;;
    esac
done
case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) platform=linux-64; checksum=366cd9cd8be14df1ab8ed50352a82111082a36686b2d389fdb79a92c3fafb3e3 ;;
    Linux-aarch64) platform=linux-aarch64; checksum=9f93b974adcb4d166996af969b6cd371287d1a3e52733704727884d9b74cb7a7 ;;
    Darwin-x86_64) platform=osx-64; checksum=1e71054bb3ac9a076e21f7ec48acfef536f9b3f1408f371a942784bf5ef83d8a ;;
    Darwin-arm64) platform=osx-arm64; checksum=ec2a072f028e1a7cf20f3e2e74d5a8127cf5a5f27636375b5359811565f4e5be ;;
    *) printf 'Automatic setup supports macOS and glibc Linux on x64/ARM64. See manual setup for other systems.\n' >&2; exit 1 ;;
esac
bootstrap="${CLIPHARBOR_BOOTSTRAP_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/clipharbor/bootstrap}"
mkdir -p "$bootstrap"
bootstrap="$(cd "$bootstrap" && pwd)"
prefix="$bootstrap/tools"
manager="$bootstrap/helper-2.9.0/micromamba"
export PATH="$prefix/bin:$PATH"
unset PYTHONPATH PYTHONHOME
trap 'printf "Setup or launch stopped. Check the error above, then rerun the same command to retry.\n" >&2' ERR
download() {
    if command -v curl >/dev/null 2>&1; then
        curl --fail --location --retry 3 --connect-timeout 30 --output "$2" "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget --https-only --timeout=30 --tries=3 -O "$2" "$1"
    else
        printf 'A download utility is missing. Use the README first-time install block to install it automatically.\n' >&2
        return 1
    fi
}
sha256() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
    else shasum -a 256 "$1" | awk '{print $1}'; fi
}
install_missing() {
    if [[ ! -f "$manager" ]] || [[ "$(sha256 "$manager")" != "$checksum" ]]; then
        mkdir -p "$(dirname "$manager")"
        printf 'Downloading the setup helper...\n'
        partial="$manager.$$.download"
        download "https://github.com/mamba-org/micromamba-releases/releases/download/2.9.0-0/micromamba-$platform" "$partial"
        if [[ "$(sha256 "$partial")" != "$checksum" ]]; then
            printf 'Setup helper checksum did not match. Nothing will be executed.\n' >&2
            rm -f -- "$partial"
            return 1
        fi
        chmod 700 "$partial"
        mv -f -- "$partial" "$manager"
    fi
    printf 'Installing missing components locally. Existing system installations are not changed.\n'
    action=create
    [[ ! -f "$prefix/conda-meta/history" ]] || action=install
    "$manager" --no-rc --root-prefix "$bootstrap/cache" "$action" --yes --prefix "$prefix" --override-channels --channel conda-forge "$@"
    hash -r
}
find_python() {
    for candidate in "$prefix/bin/python" python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys, venv, ensurepip, tkinter; assert sys.version_info >= (3,10)' >/dev/null 2>&1; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}
printf 'Checking ClipHarbor setup...\n'
# Avoid macOS's /usr/bin/git shim opening an Xcode installation dialog.
git_usable=0
if command -v git >/dev/null 2>&1; then
    if [[ "$platform" == osx-* && "$(command -v git)" == /usr/bin/git ]] && ! xcode-select -p >/dev/null 2>&1; then :
    elif git --version >/dev/null 2>&1; then git_usable=1; fi
fi
if [[ "$git_usable" == 0 ]]; then install_missing git; fi
if [[ "$install_repo" == 1 ]]; then
    project="$bootstrap/source"
    if [[ -e "$project" ]]; then
        if [[ "$(git -C "$project" remote get-url origin 2>/dev/null || true)" != "$repo_url" ]]; then
            printf 'Cannot reuse %s: it is not the ClipHarbor repository. No files were changed.\n' "$project" >&2
            exit 1
        fi
    else
        clone_stage="$(mktemp -d "$bootstrap/source-download.XXXXXXXX")"
        git clone --depth 1 "$repo_url" "$clone_stage"
        mv -- "$clone_stage" "$project"
    fi
else
    project="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
[[ -f "$project/app.py" ]] || { printf 'Run this inside the repository, or pass --install.\n' >&2; exit 1; }
missing=()
runtime="$(find_python || true)"
[[ -n "$runtime" ]] || missing+=(python=3.12 pip tk)
if ! ffmpeg -version >/dev/null 2>&1 || ! ffprobe -version >/dev/null 2>&1; then missing+=(ffmpeg); fi
if ! node -e 'if(Number(process.versions.node.split(".")[0])<22)process.exit(1)' >/dev/null 2>&1; then missing+=('nodejs>=22'); fi
if [[ ${#missing[@]} -gt 0 ]]; then install_missing "${missing[@]}"; fi
runtime="$(find_python)"
git --version >/dev/null
ffmpeg -version >/dev/null
ffprobe -version >/dev/null
node -e 'if(Number(process.versions.node.split(".")[0])<22)process.exit(1)'
venv="$project/.venv"
app_python="$venv/bin/python"
if [[ ! -x "$app_python" ]]; then
    printf 'Preparing the app environment...\n'
    "$runtime" -m venv "$venv"
fi
"$app_python" -c 'import sys; assert sys.version_info >= (3,10)' || { printf 'The app environment is damaged. Rename .venv and rerun; projects and media are separate.\n' >&2; exit 1; }
fingerprint="$(sha256 "$project/requirements.txt")"
stamp="$venv/.clipharbor-requirements"
previous=''
[[ ! -f "$stamp" ]] || previous="$(<"$stamp")"
if [[ "$update" == 1 || "$previous" != "$fingerprint" ]] || ! "$app_python" -c 'import flask, waitress, yt_dlp, yt_dlp_ejs' >/dev/null 2>&1; then
    printf 'Preparing ClipHarbor components...\n'
    "$app_python" -m pip install --disable-pip-version-check --upgrade -r "$project/requirements.txt"
    printf '%s\n' "$fingerprint" > "$stamp"
fi
if [[ "$setup_only" == 1 ]]; then printf 'ClipHarbor setup is ready: %s\n' "$project"; exit 0; fi
printf 'Opening ClipHarbor. Keep this terminal open; press Ctrl+C here when finished.\n'
exec "$app_python" "$project/app.py" --open
