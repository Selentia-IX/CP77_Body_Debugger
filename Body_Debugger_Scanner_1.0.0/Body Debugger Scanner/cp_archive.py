"""Extract files from Cyberpunk 2077 .archive (RDAR v12) files by path, using the game's Oodle DLL.

Usage: python cp_archive.py <out_dir> <archive or folder of archives>... -- <depot path>...
Writes each found file to <out_dir>/<depot path>, as WolvenKit does: the main CR2W segment followed by its buffers.
"""
import ctypes as C
import os
import struct
import sys
from pathlib import Path

GAME_BIN = Path(os.environ.get("CP2077_BIN", r"C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077\bin\x64"))


def fnv1a64(path):
    h = 0xCBF29CE484222325
    for b in path.lower().replace("/", "\\").encode():
        h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


assert fnv1a64("") == 0xCBF29CE484222325 and fnv1a64("a") == 0xAF63DC4C8601EC8C  # FNV-1a 64 test vectors

_oodle = None


def _dll():
    global _oodle
    if _oodle is None:
        _oodle = C.WinDLL(str(GAME_BIN / "oo2ext_7_win64.dll"))
        _oodle.OodleLZ_Decompress.restype = C.c_int64
        _oodle.OodleLZ_Decompress.argtypes = [C.c_char_p, C.c_int64, C.c_char_p, C.c_int64, C.c_int, C.c_int, C.c_int,
                                              C.c_void_p, C.c_int64, C.c_void_p, C.c_void_p, C.c_void_p, C.c_int64, C.c_int]
        _oodle.OodleLZ_Compress.restype = C.c_int64
        _oodle.OodleLZ_Compress.argtypes = [C.c_int, C.c_char_p, C.c_int64, C.c_char_p, C.c_int, C.c_void_p, C.c_void_p,
                                            C.c_void_p, C.c_void_p, C.c_int64]
    return _oodle


def oodle_decompress(src, size):
    dst = C.create_string_buffer(size)
    got = _dll().OodleLZ_Decompress(src, len(src), dst, size, 1, 1, 0, None, 0, None, None, None, 0, 3)
    if got != size:
        raise RuntimeError(f"Oodle returned {got}, expected {size}")
    return dst.raw


def kark_compress(raw):
    """Oodle Kraken-compress raw bytes into the game's KARK container ("KARK", u32 size, data)."""
    dst = C.create_string_buffer(len(raw) + len(raw) // 8 + 65536)
    n = _dll().OodleLZ_Compress(8, raw, len(raw), dst, 4, None, None, None, None, 0)  # Kraken, level Normal
    if n <= 0:
        raise RuntimeError("Oodle compression failed")
    out = b"KARK" + struct.pack("<I", len(raw)) + dst.raw[:n]
    assert oodle_decompress(out[8:], len(raw)) == raw
    return out


class Archive:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        magic, version, index_pos, index_size = struct.unpack("<4sIQI", self.f.read(20))
        if magic != b"RDAR":
            raise ValueError(f"{path}: not an RDAR archive")
        self.f.seek(index_pos)
        index = self.f.read(index_size)
        _tbl_off, _tbl_size, _crc, n_files, n_segments, _n_deps = struct.unpack_from("<IIQIII", index, 0)
        pos = 28
        self.files = {}
        for _ in range(n_files):
            name_hash, _ts, _inline, seg_start, seg_end = struct.unpack_from("<QqIII", index, pos)
            self.files[name_hash] = (seg_start, seg_end)
            pos += 56
        self.segments = [struct.unpack_from("<QII", index, pos + i * 16) for i in range(n_segments)]

    def read(self, name_hash):
        seg_start, seg_end = self.files[name_hash]
        out = bytearray()
        for offset, zsize, size in self.segments[seg_start:seg_end]:
            self.f.seek(offset)
            blob = self.f.read(zsize)
            if zsize == size:
                out += blob
            elif blob[:4] == b"KARK":
                out += oodle_decompress(blob[8:], struct.unpack_from("<I", blob, 4)[0])
            else:
                out += oodle_decompress(blob, size)
        return bytes(out)

    def raw_entries(self):
        """Every file as [hash, timestamp, inline_count, [(stored bytes, size), ...], dependency hashes, sha1]."""
        self.f.seek(0)
        _magic, _ver, index_pos, index_size = struct.unpack("<4sIQI", self.f.read(20))
        self.f.seek(index_pos)
        index = self.f.read(index_size)
        n_files, n_segments, n_deps = struct.unpack_from("<III", index, 16)
        deps_pos = 28 + n_files * 56 + n_segments * 16
        deps = [struct.unpack_from("<Q", index, deps_pos + i * 8)[0] for i in range(n_deps)]
        out = []
        for i in range(n_files):
            h, ts, inline, s0, s1, d0, d1, sha1 = struct.unpack_from("<QqIIIII20s", index, 28 + i * 56)
            segs = []
            for offset, zsize, size in self.segments[s0:s1]:
                self.f.seek(offset)
                segs.append((self.f.read(zsize), size))
            out.append([h, ts, inline, segs, deps[d0:d1], sha1])
        return out


def _crc64_xz(data):
    if not hasattr(_crc64_xz, "table"):
        poly = 0xC96C5795D7870F42  # CRC-64/XZ (ECMA-182, reflected)
        _crc64_xz.table = [0] * 256
        for i in range(256):
            c = i
            for _ in range(8):
                c = (c >> 1) ^ poly if c & 1 else c >> 1
            _crc64_xz.table[i] = c
    t, c = _crc64_xz.table, 0xFFFFFFFFFFFFFFFF
    for b in data:
        c = t[(c ^ b) & 0xFF] ^ (c >> 8)
    return c ^ 0xFFFFFFFFFFFFFFFF


def write_archive(path, entries):
    """Write an RDAR v12 archive laid out like WolvenKit's, from raw_entries()-style lists."""
    data, seg_table, file_table, dep_table = bytearray(b"\0" * 172), [], [], []
    for h, ts, inline, segs, deps, sha1 in entries:
        s0, d0 = len(seg_table), len(dep_table)
        for stored, size in segs:
            seg_table.append((len(data), len(stored), size))
            data += stored
        dep_table += deps
        file_table.append(struct.pack("<QqIIIII20s", h, ts, inline, s0, len(seg_table), d0, len(dep_table), sha1))
    pad = lambda n: (-n) % 4096
    data += b"\xd9" * pad(len(data))
    body = struct.pack("<III", len(file_table), len(seg_table), len(dep_table)) + b"".join(file_table) + \
        b"".join(struct.pack("<QII", *s) for s in seg_table) + b"".join(struct.pack("<Q", d) for d in dep_table)
    index = struct.pack("<IIQ", 8, len(body) + 8, _crc64_xz(body)) + body
    index_pos = len(data)
    data += index + b"\xd9" * pad(len(index))
    struct.pack_into("<4sIQIQIQ", data, 0, b"RDAR", 12, index_pos, len(index), 0, 0, len(data))
    Path(path).write_bytes(data)


def main():
    args = sys.argv[1:]
    cut = args.index("--")
    out_dir, sources, paths = Path(args[0]), args[1:cut], args[cut + 1:]
    archives = []
    for src in sources:
        p = Path(src)
        archives += [Archive(a) for a in sorted(p.rglob("*.archive"))] if p.is_dir() else [Archive(p)]
    for depot_path in paths:
        h = fnv1a64(depot_path)
        hits = [a for a in archives if h in a.files]
        if not hits:
            print(f"not found: {depot_path}")
            continue
        data = hits[-1].read(h)  # later archives override earlier ones
        target = out_dir / depot_path.replace("\\", "/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print(f"{len(data):>9}  {Path(hits[-1].path).name}  {depot_path}")


if __name__ == "__main__":
    main()
