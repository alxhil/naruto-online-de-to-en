"""Minimal AMF3 codec that preserves class traits so rewritten files load identically."""
import struct

class Obj(dict):
    """AMF3 object; .traits = (class_name, dynamic, sealed_keys)."""
    traits = ("", True, ())

class Arr(list):
    assoc = None

class Reader:
    def __init__(s, b): s.b = b; s.p = 0; s.strs = []; s.objs = []; s.traits = []
    def u8(s): v = s.b[s.p]; s.p += 1; return v
    def u29(s):
        v = 0
        for i in range(4):
            c = s.u8()
            if i < 3:
                v = (v << 7) | (c & 0x7f)
                if not c & 0x80: return v
            else: v = (v << 8) | c
        return v
    def string(s):
        h = s.u29()
        if not h & 1: return s.strs[h >> 1]
        n = h >> 1
        if n == 0: return ""
        v = s.b[s.p:s.p + n].decode("utf-8"); s.p += n; s.strs.append(v); return v
    def value(s):
        m = s.u8()
        if m == 0: return Undefined
        if m == 1: return None
        if m == 2: return False
        if m == 3: return True
        if m == 4:
            v = s.u29(); return v - (1 << 29) if v & (1 << 28) else v
        if m == 5: v = struct.unpack(">d", s.b[s.p:s.p + 8])[0]; s.p += 8; return Double(v)
        if m == 6: return s.string()
        if m == 9:
            h = s.u29()
            if not h & 1: return s.objs[h >> 1]
            a = Arr(); s.objs.append(a); assoc = {}
            while True:
                k = s.string()
                if k == "": break
                assoc[k] = s.value()
            a.assoc = assoc or None
            a.extend(s.value() for _ in range(h >> 1))
            return a
        if m == 10:
            h = s.u29()
            if not h & 1: return s.objs[h >> 1]
            if not h & 2: t = s.traits[h >> 2]
            else:
                if h & 4: raise ValueError("externalizable not supported")
                name = s.string(); t = (name, bool(h & 8), tuple(s.string() for _ in range(h >> 4)))
                s.traits.append(t)
            o = Obj(); o.traits = t; s.objs.append(o)
            for k in t[2]: o[k] = s.value()
            if t[1]:
                while True:
                    k = s.string()
                    if k == "": break
                    o[k] = s.value()
            return o
        raise ValueError(f"unsupported marker {m} at {s.p}")

class _U: pass
Undefined = _U()
class Double(float): pass

class Writer:
    def __init__(s): s.out = bytearray(); s.strs = {}; s.traits = {}; s.objs = {}
    def u29(s, v):
        if v < 0x80: s.out.append(v)
        elif v < 0x4000: s.out += bytes([(v >> 7) | 0x80, v & 0x7f])
        elif v < 0x200000: s.out += bytes([(v >> 14) | 0x80, ((v >> 7) & 0x7f) | 0x80, v & 0x7f])
        else: s.out += bytes([(v >> 22) | 0x80, ((v >> 15) & 0x7f) | 0x80, ((v >> 8) & 0x7f) | 0x80, v & 0xff])
    def string(s, v):
        if v == "": s.out.append(1); return
        if v in s.strs: s.u29(s.strs[v] << 1); return
        s.strs[v] = len(s.strs); b = v.encode("utf-8"); s.u29((len(b) << 1) | 1); s.out += b
    def value(s, v):
        if v is Undefined: s.out.append(0)
        elif v is None: s.out.append(1)
        elif v is False: s.out.append(2)
        elif v is True: s.out.append(3)
        elif isinstance(v, int) and not isinstance(v, bool) and -(1 << 28) <= v < (1 << 28):
            s.out.append(4); s.u29(v & 0x1fffffff)
        elif isinstance(v, (int, float)): s.out.append(5); s.out += struct.pack(">d", float(v))
        elif isinstance(v, str): s.out.append(6); s.string(v)
        elif isinstance(v, list):
            s.out.append(9)
            if id(v) in s.objs: s.u29(s.objs[id(v)] << 1); return
            s.objs[id(v)] = len(s.objs); s.u29((len(v) << 1) | 1)
            for k, x in (getattr(v, "assoc", None) or {}).items(): s.string(k); s.value(x)
            s.string("")
            for x in v: s.value(x)
        elif isinstance(v, dict):
            s.out.append(10)
            if id(v) in s.objs: s.u29(s.objs[id(v)] << 1); return
            s.objs[id(v)] = len(s.objs)
            t = getattr(v, "traits", ("", True, ()))
            if t in s.traits: s.u29((s.traits[t] << 2) | 1)
            else:
                s.traits[t] = len(s.traits)
                s.u29((len(t[2]) << 4) | (8 if t[1] else 0) | 3); s.string(t[0])
                for k in t[2]: s.string(k)
            for k in t[2]: s.value(v[k])
            if t[1]:
                for k, x in v.items():
                    if k not in t[2]: s.string(k); s.value(x)
                s.string("")
        else: raise TypeError(type(v))

def loads(b): return Reader(b).value()
def dumps(v): w = Writer(); w.value(v); return bytes(w.out)
