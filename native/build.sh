#!/bin/sh
# Cross compile the tiny device side helper without any Android NDK:
# clang emits a freestanding, statically linked binary (raw syscalls only).
#
# Override the tools if needed, for example on macOS with Homebrew LLVM:
#   CLANG="$(brew --prefix llvm)/bin/clang" ./build.sh
set -e
cd "$(dirname "$0")"

CLANG="${CLANG:-clang}"
STRIP="${STRIP:-strip}"

CFLAGS="-nostdlib -static -O2 -fno-stack-protector -fno-pic -fno-builtin -ffreestanding"
LDFLAGS="-fuse-ld=lld -Wl,-e,_start -Wl,--build-id=none"

mkdir -p ../twrpscrcpy/bin

"$CLANG" --target=aarch64-linux-gnu $CFLAGS $LDFLAGS -o ../twrpscrcpy/bin/fbstream-arm64 fbstream.c
"$CLANG" --target=armv7a-linux-gnueabi -march=armv7-a $CFLAGS $LDFLAGS -o ../twrpscrcpy/bin/fbstream-arm fbstream.c

"$STRIP" -s ../twrpscrcpy/bin/fbstream-arm64 2>/dev/null || true
"$STRIP" -s ../twrpscrcpy/bin/fbstream-arm 2>/dev/null || true

ls -l ../twrpscrcpy/bin/
