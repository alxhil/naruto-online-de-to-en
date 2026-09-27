"""Overlay English text onto German-server config data, keeping every non-text field from DE."""
import collections
import re
import zlib
import amf3, nfiles

LETTER = re.compile(r"[A-Za-zÀ-ÿ]")
PLACEHOLDER = re.compile(r"%\d+|\{\d+\}|#\w+#")    # substitution tokens only; HTML tags are cosmetic
IDENTIFIER = re.compile(r"^[\w./:,;|#-]*$")          # paths, link commands, csv ids...

def is_text(s):
    return bool(LETTER.search(s)) and not (IDENTIFIER.match(s) and ("/" in s or "_" in s or "," in s or "." in s))

# Fallback dictionary: German text -> Chinese source -> English, built from the i18n Kv tables.
FALLBACK = {}
KV_TABLES = ("config/i18n/KvExcelDebugCFG.cfg", "config/i18n/KvDebugCFG.cfg")

def load_fallback(read_de, read_en):
    """read_de/read_en(path) -> bytes of that config for each language."""
    zh_en = {}
    for t in KV_TABLES:
        for r in nfiles.read_cfg(read_en(t)).values():
            w, zh = r.get("word"), r.get("word_zh")
            if zh and isinstance(w, str) and w.strip() and w != zh: zh_en.setdefault(zh, w)
    for t in KV_TABLES:
        for r in nfiles.read_cfg(read_de(t)).values():
            w, zh = r.get("word"), r.get("word_zh")
            if zh in zh_en and isinstance(w, str) and w != zh_en[zh]: FALLBACK.setdefault(w, zh_en[zh])

def tokens_match(a, b):
    return sorted(PLACEHOLDER.findall(a)) == sorted(PLACEHOLDER.findall(b))

def swap(de_s, en_s, st):
    if de_s == en_s: st["same"] += is_text(de_s); return de_s
    if not is_text(de_s): return de_s
    if not isinstance(en_s, str) or not en_s.strip():
        fb = FALLBACK.get(de_s)
        if fb and tokens_match(de_s, fb): st["fallback"] += 1; return fb
        st["no_en"] += 1
        return de_s
    if not tokens_match(de_s, en_s):
        st["placeholder_mismatch"] += 1; return de_s
    st["replaced"] += 1; return en_s

def merge(de, en, st):
    """Return DE structure with English strings where the same key path exists in EN."""
    if isinstance(de, str):
        st["texts"] += is_text(de); return swap(de, en, st)
    if isinstance(de, dict):
        ed = en if isinstance(en, dict) else {}
        for k, v in de.items():
            de[k] = merge(v, ed.get(k), st)
        return de
    if isinstance(de, list):
        el = en if isinstance(en, list) else []
        for i, v in enumerate(de):
            de[i] = merge(v, el[i] if i < len(el) else None, st)
        return de
    return de

def merge_cfg_bytes(de_b, en_b, st):
    return nfiles.write_cfg(merge(nfiles.read_cfg(de_b), nfiles.read_cfg(en_b), st))

def merge_pkg_bytes(de_b, en_b, st):
    en_map = dict(nfiles.read_pkg(en_b)); out = []
    for name, data in nfiles.read_pkg(de_b):
        if name in en_map and data[:1] == b"\x0a":       # AMF3 object; XML entries pass through
            data = amf3.dumps(merge(amf3.loads(data), amf3.loads(en_map[name]), st))
        elif name in en_map:
            st["pkg_xml_skipped"] += 1
        out.append((name, data))
    return nfiles.write_pkg(out)


# ---------------------------------------------------------------- XML configs
import xml.etree.ElementTree as ET

def _is_value(s):
    """Attribute/leaf values that identify a row rather than being display text."""
    return s is not None and not is_text(s)

def _signature(el):
    ids = tuple(sorted((k, v) for k, v in el.attrib.items() if _is_value(v)))
    leaves = tuple((c.tag, (c.text or "").strip()) for c in el
                   if len(c) == 0 and not c.attrib and _is_value((c.text or "").strip()))
    return el.tag, ids, leaves

def _merge_el(de, en, st):
    for k, v in de.attrib.items():
        if is_text(v):
            st["texts"] += 1
            de.attrib[k] = swap(v, en.attrib.get(k) if en is not None else None, st)
    t = (de.text or "").strip()
    if t and len(de) == 0 and is_text(t):
        st["texts"] += 1
        new = swap(t, (en.text or "").strip() if en is not None else None, st)
        if new != t: de.text = de.text.replace(t, new)
    # pair children by signature, in order of occurrence
    pool = collections.defaultdict(list)
    for c in (list(en) if en is not None else []):
        pool[_signature(c)].append(c)
    for c in de:
        match = pool.get(_signature(c))
        _merge_el(c, match.pop(0) if match else None, st)

def merge_xml_text(de_b, en_b, st):
    parser = lambda: ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    de = ET.fromstring(de_b, parser=parser()); en = ET.fromstring(en_b, parser=parser())
    _merge_el(de, en, st)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(de, encoding="utf-8", xml_declaration=False)

def merge_xml_bytes(de_b, en_b, st):
    """Config XML as served: zlib-compressed, or plain."""
    original = de_b
    packed = de_b[:1] == b"x"
    if packed: de_b, en_b = zlib.decompress(de_b), zlib.decompress(en_b)
    before = st["replaced"] + st["fallback"]
    out = merge_xml_text(de_b, en_b, st)
    if st["replaced"] + st["fallback"] == before:      # nothing translated: serve the file untouched
        return original
    return zlib.compress(out, 9) if packed else out
