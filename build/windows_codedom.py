
"""Repair the disposable Windows bootstrap CodeDOM, never boot/coreclr."""
import hashlib
import io
from pathlib import Path
import struct
import urllib.request
import zipfile

VERSION = "10.0.0"
SHA256 = "7df3177b7e57544e3d19de9b6f3d904664e4083793b929c661f29367afccb52f"
URL = f"https://api.nuget.org/v3-flatcontainer/system.codedom/{VERSION}/system.codedom.{VERSION}.nupkg"
ENTRY = "lib/net10.0/System.CodeDom.dll"


def _portable_il(data):
    """Accept managed AnyCPU IL, not a platform-specific ReadyToRun image."""
    try:
        if len(data) < 512 or data[:2] != b"MZ":
            return False
        pe = struct.unpack_from("<I", data, 0x3c)[0]
        if pe + 24 > len(data) or data[pe:pe + 4] != b"PE\0\0":
            return False
        machine, sections, optional_size = (
            struct.unpack_from("<H", data, pe + 4)[0],
            struct.unpack_from("<H", data, pe + 6)[0],
            struct.unpack_from("<H", data, pe + 20)[0],
        )
        opt = pe + 24
        if machine != 0x14c or struct.unpack_from("<H", data, opt)[0] != 0x10b:
            return False
        if optional_size < 0xd0 or opt + optional_size > len(data):
            return False
        cli_rva = struct.unpack_from("<I", data, opt + 96 + 8 * 14)[0]
        if not cli_rva:
            return False
        table = opt + optional_size
        for i in range(sections):
            sec = table + 40 * i
            if sec + 40 > len(data):
                return False
            va, raw_size, raw = (
                struct.unpack_from("<I", data, sec + 12)[0],
                struct.unpack_from("<I", data, sec + 16)[0],
                struct.unpack_from("<I", data, sec + 20)[0],
            )
            if va <= cli_rva < va + raw_size:
                cli = raw + cli_rva - va
                if cli + 72 > len(data):
                    return False
                flags = struct.unpack_from("<I", data, cli + 16)[0]
                native_header = struct.unpack_from("<I", data, cli + 64)[0]
                return bool(flags & 1) and native_header == 0
        return False
    except (IndexError, struct.error):
        return False


def ensure_windows_codedom(seed):
    target = Path(seed) / "System.CodeDom.dll"
    if not target.is_file():
        raise RuntimeError(f"Missing staged System.CodeDom.dll: {target}")
    if _portable_il(target.read_bytes()):
        print("Windows CodeDOM: portable IL already staged", flush=True)
        return

    cache = Path.home() / ".cache/neo-nemerle/system.codedom.10.0.0.nupkg"
    cache.parent.mkdir(parents=True, exist_ok=True)
    package = cache.read_bytes() if cache.is_file() else b""

    if hashlib.sha256(package).hexdigest() != SHA256:
        print("Windows CodeDOM: fetching verified portable .NET 10 package", flush=True)
        with urllib.request.urlopen(URL, timeout=45) as response:
            package = response.read()
        if hashlib.sha256(package).hexdigest() != SHA256:
            raise RuntimeError("System.CodeDom NuGet package SHA-256 mismatch")
        cache.write_bytes(package)

    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        replacement = archive.read(ENTRY)
    if not _portable_il(replacement):
        raise RuntimeError("NuGet CodeDOM DLL is not portable managed IL")

    temp = target.with_name(target.name + ".tmp")
    try:
        temp.write_bytes(replacement)
        temp.replace(target)
    finally:
        if temp.exists():
            temp.unlink()
    print(f"Windows CodeDOM: repaired temporary seed at {target}", flush=True)
