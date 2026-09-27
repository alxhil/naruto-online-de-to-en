r"""mitmproxy addon: show the German Naruto Online client in English.

The DE client downloads its text tables (zlib'd AMF3 .cfg files and .pkg bundles) from
cdn-naruto-de-res.oasgames.com. For each one, this fetches the same file from the English
CDN and overlays the English strings onto the German data. Only text changes; ids, numbers,
links and anything the EN file lacks stay exactly as the German server sent them.

Run via run.ps1 (admin):
  mitmdump -s en_patch.py --mode "local:Naruto Online.exe" --allow-hosts "cdn-naruto-de-res\.oasgames\.com"
See README.md for setup and AGENTS.md for internals.
"""
import collections
import logging
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import merge
import nfiles

DE_HOST = "cdn-naruto-de-res.oasgames.com"
EN_CDN = "https://cdnnarutoen-gmt.oasgames.com"
EN_BUILD_SEED = "EN_NarutoAlpha9.55Build303"   # last known EN build; newer ones are probed
DE_PATH = re.compile(r"^/(DE_NarutoAlpha[\d.]+Build\d+)/(.+?)(?:\?.*)?$")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
log = logging.getLogger("en_patch")
_fh = logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "patch.log"), encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
log.addHandler(_fh)
log.setLevel(logging.INFO)


def is_de_cdn(flow):
    """Local-capture flows can carry the server IP as host, so also check TLS SNI and Host header."""
    names = (flow.request.pretty_host, flow.request.headers.get("host", ""),
             getattr(flow.client_conn, "sni", None) or "")
    return DE_HOST in names or bool(DE_PATH.match(flow.request.path))


MERGE_VERSION = "m2"   # bump when merge logic changes so saved merges are rebuilt
SWF_SWAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swf_swap.txt")


def swf_swap_list():
    """Flash files to replace wholesale with the EN build (one path per line, # comments).
    Re-read on every request so entries can be added/removed without restarting the proxy."""
    try:
        with open(SWF_SWAP_FILE, encoding="utf-8") as f:
            return {l.split("#", 1)[0].strip() for l in f} - {""}
    except FileNotFoundError:
        return set()


def is_text_config(rel):
    return (rel.startswith("config/") and rel.endswith((".cfg", ".pkg", ".xml"))
            or rel.startswith("flash/") and rel.endswith("Config.xml"))


def merger_for(rel):
    if rel.endswith(".pkg"):
        return merge.merge_pkg_bytes
    return merge.merge_xml_bytes if rel.endswith(".xml") else merge.merge_cfg_bytes


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def cached_get(url):
    """Fetch once per URL; version folders are immutable so the disk copy never goes stale."""
    path = os.path.join(CACHE_DIR, re.sub(r"[^\w.-]", "_", url.split("//", 1)[1]))
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    data = http_get(url)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return data


def _build_exists(tag):
    try:
        http_get(f"{EN_CDN}/{tag}/assets/loading/cfg.xml")
        return True
    except urllib.error.HTTPError:
        return False


def latest_en_build(seed=EN_BUILD_SEED):
    """Walk forward from the seed build to the newest one the EN CDN serves."""
    m = re.match(r"EN_NarutoAlpha(\d+)\.(\d+)Build(\d+)", seed)
    major, minor, build = int(m[1]), int(m[2]), int(m[3])
    best = seed
    for mi in range(minor, minor + 6):
        found = False
        for b in range(300 if mi != minor else build, 320):
            tag = f"EN_NarutoAlpha{major}.{mi:02d}Build{b}"
            if tag != best and _build_exists(tag):
                best, found = tag, True
        if not found and mi > minor:
            break
    return best


class EnPatch:
    def __init__(self):
        self.en_index = None
        self.de_tag_by_path = {}
        self.stats = collections.Counter()

    def _ensure_en_index(self):
        if self.en_index is None:
            build = latest_en_build()
            self.en_index = nfiles.read_resource_index(cached_get(f"{EN_CDN}/{build}/resource.cfg"))
            log.info("EN build %s: %d files indexed", build, len(self.en_index))

    def en_file(self, rel):
        info = self.en_index.get(rel)
        return cached_get(f"{EN_CDN}/{info['tag']}/{rel}") if info else None

    def _ensure_fallback(self, de_build):
        if merge.FALLBACK:
            return
        def read_de(rel):
            tag = self.de_tag_by_path.get(rel, de_build)
            return cached_get(f"https://{DE_HOST}/{tag}/{rel}")
        merge.load_fallback(read_de, self.en_file)
        log.info("fallback dictionary: %d entries", len(merge.FALLBACK))

    def request(self, flow):
        """Force full downloads of text configs; a cached 304 would bypass the patch."""
        if not is_de_cdn(flow):
            return
        m = DE_PATH.match(flow.request.path)
        if m and (is_text_config(m[2]) or m[2] == "resource.cfg" or m[2] in swf_swap_list()):
            for h in ("If-None-Match", "If-Modified-Since"):
                flow.request.headers.pop(h, None)

    def response(self, flow):
        if not flow.response or not is_de_cdn(flow):
            return
        m = DE_PATH.match(flow.request.path)
        if not m:
            return
        build, rel = m[1], m[2]
        if is_text_config(rel) or rel == "resource.cfg":
            log.info("seen %s %s", flow.response.status_code, rel)
        if flow.response.status_code != 200:
            return

        if rel == "resource.cfg":                      # learn where each DE file lives
            try:
                idx = nfiles.read_resource_index(flow.response.content)
                self.de_tag_by_path = {k: v["tag"] for k, v in idx.items()
                                       if isinstance(k, str) and isinstance(v, dict)}
            except Exception as e:
                log.warning("could not read DE resource index: %r", e)
            return

        if rel.endswith(".swf") and rel in swf_swap_list():
            try:
                self._ensure_en_index()
                en = self.en_file(rel)
                if en is not None:
                    flow.response.content = en
                    flow.response.headers["Cache-Control"] = "no-store"
                    log.info("SWF %s swapped for %s", rel, self.en_index[rel]["tag"])
            except Exception as e:
                log.warning("SWF %s left German: %r", rel, e)
            return

        if not is_text_config(rel):
            return
        try:
            self._ensure_en_index()
            en = self.en_file(rel)
            if en is None:
                return
            st = collections.Counter()
            out_path = os.path.join(CACHE_DIR, "merged", MERGE_VERSION, build, self.en_index[rel]["tag"], rel)
            if os.path.exists(out_path):               # same DE+EN versions -> reuse earlier merge
                with open(out_path, "rb") as f:
                    flow.response.content = f.read()
            else:
                self._ensure_fallback(build)
                flow.response.content = merger_for(rel)(flow.response.content, en, st)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(flow.response.content)
            flow.response.headers["Cache-Control"] = "no-store"   # stop the patch persisting in the client cache
            self.stats += st
            log.info("EN %-55s %s", rel, f"{st['replaced'] + st['fallback']} strings" if st else "(saved merge)")
        except Exception as e:                         # never break the game: fall back to German
            log.warning("left %s German: %r", rel, e)


addons = [EnPatch()]
