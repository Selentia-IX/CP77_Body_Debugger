"""Parse a CR2W file (v195) and print its exports as nested property trees (JSON-like).

Usage: python cr2w_dump.py <file> [export class filter...]
Primitive types and arrays/structs are decoded; anything unknown is shown as "<N bytes>".
"""
import json
import struct
import sys

PRIMS = {"Bool": "<?", "Uint8": "<B", "Int8": "<b", "Uint16": "<H", "Int16": "<h", "Uint32": "<I", "Int32": "<i",
         "Uint64": "<Q", "Int64": "<q", "Float": "<f", "Double": "<d", "TweakDBID": "<Q", "CRUID": "<Q"}


class CR2W:
    def __init__(self, data):
        if data[:4] != b"CR2W":
            raise ValueError("not CR2W")
        self.d = data
        tables = [struct.unpack_from("<III", data, 40 + i * 12) for i in range(10)]
        str_off, str_size, _ = tables[0]
        self.strings = data[str_off:str_off + str_size]
        self.names = [self._str(struct.unpack_from("<I", data, tables[1][0] + i * 8)[0]) for i in range(tables[1][1])]
        self.exports = [struct.unpack_from("<HHIIIII", data, tables[4][0] + i * 24) for i in range(tables[4][1])]
        self.buffers = [struct.unpack_from("<IIIIII", data, tables[5][0] + i * 24) for i in range(tables[5][1])]
        self.imports = [self._str(struct.unpack_from("<I", data, tables[2][0] + i * 8)[0]) for i in range(tables[2][1])]

    def _str(self, off):
        end = self.strings.index(b"\0", off)
        return self.strings[off:end].decode("utf-8", "replace")

    # value decoding -------------------------------------------------------
    def value(self, typ, pos, end):
        d = self.d
        if typ in PRIMS:
            return struct.unpack_from(PRIMS[typ], d, pos)[0], pos + struct.calcsize(PRIMS[typ])
        if typ == "CName":
            return self.names[struct.unpack_from("<H", d, pos)[0]], pos + 2
        if typ.startswith(("handle:", "whandle:")):
            return f"#{struct.unpack_from('<i', d, pos)[0]}", pos + 4
        if typ.startswith(("rRef:", "raRef:")):
            return f"import:{struct.unpack_from('<H', d, pos)[0]}", pos + 2
        if typ == "String":
            n = d[pos]
            if n & 0x80:  # ascii, length in low bits
                ln = n & 0x3F
                return d[pos + 1:pos + 1 + ln].decode("ascii", "replace"), pos + 1 + ln
            return f"<string>", end
        if typ.startswith("array:"):
            count = struct.unpack_from("<I", d, pos)[0]
            pos += 4
            inner = typ[6:]
            items = []
            for _ in range(count):
                if pos >= end:
                    break
                v, npos = self.value(inner, pos, end)
                if npos is None:
                    return f"<array {count} x {inner}>", end
                items.append(v)
                pos = npos
            return items, pos
        if typ.startswith("static:"):
            n, inner = typ[7:].split(",", 1)
            count = struct.unpack_from("<I", d, pos)[0]
            pos += 4
            items = []
            for _ in range(count):
                v, npos = self.value(inner, pos, end)
                if npos is None:
                    return f"<static {count} x {inner}>", end
                items.append(v)
                pos = npos
            return items, pos
        if typ in ("DataBuffer", "SharedDataBuffer", "serializationDeferredDataBuffer", "DeferredDataBuffer"):
            return f"buffer:{struct.unpack_from('<H', d, pos)[0]}", end
        # anything else is an enum (stored as a CName) or a struct (a property list)
        if end - pos == 2:
            return self.names[struct.unpack_from("<H", d, pos)[0]], pos + 2
        return self.props(pos, end)

    def props(self, pos, end, top=False):
        out = {}
        pos += 1  # every serialized class/struct starts with a zero byte
        while pos + 2 <= end:
            name_idx = struct.unpack_from("<H", self.d, pos)[0]
            if name_idx == 0:
                return out, pos + 2
            type_idx, size = struct.unpack_from("<HI", self.d, pos + 2)
            name, typ = self.names[name_idx], self.names[type_idx]
            vstart, vend = pos + 8, pos + 4 + size
            try:
                v, _ = self.value(typ, vstart, vend)
                out[name] = v if v is not None else f"<{typ} {vend - vstart} bytes>"
            except (struct.error, IndexError, ValueError):
                out[name] = f"<{typ} {vend - vstart} bytes, undecoded>"
            pos = vend
        return out, pos

    def dump(self, class_filter=None):
        result = []
        for i, (cls, _flags, parent, size, off, _tpl, _crc) in enumerate(self.exports):
            name = self.names[cls]
            if class_filter and name not in class_filter:
                continue
            body, _ = self.props(off, off + size, top=True)
            result.append({"export": i + 1, "class": name, "props": body})
        return result


if __name__ == "__main__":
    cr = CR2W(open(sys.argv[1], "rb").read())
    print(json.dumps(cr.dump(set(sys.argv[2:]) or None), indent=1, default=str))
