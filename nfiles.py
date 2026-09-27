"""Readers/writers for Naruto Online client data files."""
import lzma, struct, zlib
import amf3

def read_cfg(b):            # zlib(AMF3)
    return amf3.loads(zlib.decompress(b))
def write_cfg(o):
    return zlib.compress(amf3.dumps(o), 9)

def read_pkg(b):            # zlib( repeat[u16 nameLen, name, u32 len, AMF3] )
    raw = zlib.decompress(b); p = 0; out = []
    while p < len(raw):
        n = struct.unpack_from(">H", raw, p)[0]; p += 2
        name = raw[p:p + n].decode(); p += n
        l = struct.unpack_from(">I", raw, p)[0]; p += 4
        out.append((name, raw[p:p + l])); p += l
    return out
def write_pkg(entries):
    buf = bytearray()
    for name, data in entries:
        nb = name.encode(); buf += struct.pack(">H", len(nb)) + nb + struct.pack(">I", len(data)) + data
    return zlib.compress(bytes(buf), 9)

def read_lzma(b):           # LZMA-alone
    return lzma.decompress(b, format=lzma.FORMAT_ALONE)

def read_resource_index(b):
    """resource.cfg -> {path: FileAssetInfo(size, belong, tag, ver, url)}; tag = version folder."""
    raw = read_lzma(b); r = amf3.Reader(raw); r.p = 9; out = {}
    while r.p < len(raw):
        try: k = r.value(); out[k] = r.value()
        except ValueError: break          # trailer section after the index
    return out
