#!/bin/sh
# Download the same ONNX exports used by the demo container.
set -eu
destination=${1:-models}
mkdir -p "$destination"
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
fetch() {
    release=$1
    name=$2
    digest=$3
    archive="$scratch/$name.tar.bz2"
    curl -fLsS --retry 3 "https://github.com/k2-fsa/sherpa-onnx/releases/download/$release/$name.tar.bz2" -o "$archive"
    python3 - "$archive" "$digest" <<'PY'
import hashlib, sys
with open(sys.argv[1], "rb") as downloaded:
    if hashlib.file_digest(downloaded, "sha256").hexdigest() != sys.argv[2]:
        raise SystemExit("Model checksum mismatch")
PY
    tar xjf "$archive" -C "$destination"
}
fetch tts-models sherpa-onnx-supertonic-3-tts-int8-2026-05-11 82fa96f91c4ef8abaae3a14a3f4153facf88bed821d1f7331cec2700f432c427
fetch asr-models sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8 1495e91b59d7fc53ddca91f3431758ec99f8fa253fdb0e1e851be0f72b14b0f9
