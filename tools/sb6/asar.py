"""Runs asar (https://github.com/RPGHacker/asar) on scratch copies.

asar never touches the build image directly: SPC700 code is assembled into a
blank buffer, and 65816 code into a copy of the ROM, after which only the
changed bytes are taken back, so the caller can check that they fall inside
the space it allocated.
"""
import os
import subprocess
import tempfile

import numpy as np

DEFAULT_ASAR = r"D:\sb6-tools\asar\asar.exe"


def asar_path():
    path = os.environ.get("SB6_ASAR", DEFAULT_ASAR)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"asar not found at {path}; set SB6_ASAR")
    return path


def _run(asm, image, defines):
    with tempfile.TemporaryDirectory() as tmp:
        rom = os.path.join(tmp, "image.bin")
        with open(rom, "wb") as fh:
            fh.write(image)
        args = [asar_path(), "--fix-checksum=off", "--no-title-check"]
        args += [f"-D{k}={v}" for k, v in defines.items()]
        args += [asm, rom]
        res = subprocess.run(args, capture_output=True, text=True)
        if res.returncode:
            raise RuntimeError(f"asar failed on {os.path.basename(asm)}:\n{res.stdout}{res.stderr}")
        with open(rom, "rb") as fh:
            return fh.read(), res.stdout


def assemble_blob(asm, size, defines):
    """Assembles position-dependent code (`base`) at file offset 0; returns `size` bytes."""
    out, _ = _run(asm, bytes(size), defines)
    return out[:size]


def assemble_into(rom_bytes, asm, defines):
    """Assembles into a copy of the ROM.

    Returns ([(file_offset, bytes)] of changed runs, {name: value}) where the
    dict holds the `print "SYM name ", hex(value)` lines of the source."""
    out, stdout = _run(asm, bytes(rom_bytes), defines)
    if len(out) != len(rom_bytes):
        raise RuntimeError("asar changed the ROM size")
    diff = np.flatnonzero(np.frombuffer(out, np.uint8) != np.frombuffer(bytes(rom_bytes), np.uint8))
    runs = []
    for k in diff:
        if runs and runs[-1][1] == k:
            runs[-1][1] = k + 1
        else:
            runs.append([int(k), int(k) + 1])
    syms = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "SYM":
            syms[parts[1]] = int(parts[2], 16)
    return [(a, out[a:b]) for a, b in runs], syms
