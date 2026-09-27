# AGENTS.md: guide for AI assistants working on this repo

Read this before changing anything. It records how the game's data works and the traps
already found the hard way. User-facing docs are in `README.md`.

## What this is

A mitmproxy addon that makes the **German** Naruto Online client (Oasis DE, Flash game in a
CefSharp + PepperFlash desktop wrapper, `Naruto Online.exe`) display **English**. It rewrites
responses from the DE resource CDN using the matching files from the EN CDN.

## Files

| File | Role |
|---|---|
| `en_patch.py` | mitmproxy addon (`addons = [EnPatch()]`): request/response hooks, EN build discovery, disk cache, SWF swap, logging to `patch.log` |
| `merge.py` | Overlay logic: `merge()` for AMF3 trees, `merge_cfg_bytes`, `merge_pkg_bytes`, `merge_xml_bytes`, the German→Chinese→English `FALLBACK` dictionary |
| `amf3.py` | Minimal AMF3 codec that **preserves class traits** (typed sealed objects); round-trips game files byte-for-byte |
| `nfiles.py` | Container formats: `.cfg`, `.pkg`, LZMA `resource.cfg` index |
| `swf_swap.txt` | User-editable list of Flash files served wholesale from EN; re-read on every request |
| `run.ps1` | Self-elevating launcher: `mitmdump -s en_patch.py --mode local:Naruto Online.exe --allow-hosts cdn-naruto-de-res\.oasgames\.com` |
| `cache/` | Runtime only (git-ignored): downloaded EN/DE files + `merged/<MERGE_VERSION>/<de_tag>/<en_tag>/<path>` |
| `patch.log` | Runtime only (git-ignored): `seen <status> <path>`, `EN <path> N strings`, `SWF ... swapped`, warnings |

## Data formats (verified)

- **URLs:** DE `https://cdn-naruto-de-res.oasgames.com/<DE_NarutoAlphaX.YYBuildZZZ>/<path>`,
  EN `https://cdnnarutoen-gmt.oasgames.com/<EN_...>/<path>`. The folder is a **per-file**
  version tag; a wrong tag gives 404. Cloudflare returns 403 without a browser `User-Agent`.
- **`<build>/resource.cfg`:** LZMA-alone; after an 8-byte header plus one AMF3 undefined
  byte (start at offset 9), an AMF3 stream of alternating `path` and
  `FileAssetInfo{size, belong, tag, ver, url}`. A trailer at the end doesn't parse; stop there.
  Some values aren't dicts, so filter them.
- **`.cfg`:** zlib(AMF3). Top level is usually an object keyed by row id; rows are typed objects
  (`traits = (class, dynamic, sealed_keys)`), so re-encoding must reuse traits (`amf3.Obj.traits`).
- **`.pkg`** (`config/archives/item1-3.pkg`): zlib of repeated `[u16 BE name_len][name][u32 BE len][data]`;
  data is AMF3 (starts with `0x0A`) or XML (starts with `<`).
- **XML configs:** usually zlib-compressed (`78 9c`), sometimes plain. Rows keyed by `id`-like
  attributes or leaf elements (`<id>`, `<award_id>`).
- **String keys:** `TranslatedKeyCFG` rows are `as_<module>_<md5>` and are shared between DE
  and EN. `config/i18n/KvExcelDebugCFG.cfg` / `KvDebugCFG.cfg` map `word_zh` (Chinese source)
  → `word` (localised) in both languages, which gives the fallback.
- **`fl_*` keys** are text typed into Flash layouts at build time. The client never looks them
  up at runtime; the text is baked into the (encrypted) SWF. Only a SWF swap changes it.
- **SWFs** have a fake `ZWS` header with `ffffffff` length and are custom-encrypted. They can't
  be decompressed or edited. DE and EN use the same scheme, so swapping whole files works.

## Hard-won gotchas

1. **Never intercept all hosts.** `naruto-de.oasgames.com` / `naruto-en.oasgames.com`
   (login page, `version.js`) only speak legacy TLS. mitmproxy's upstream TLS fails, which gives
   a black screen. Keep `--allow-hosts` limited to the DE CDN. Do **not** "fix" this by lowering
   TLS security levels.
2. **In local-capture mode `flow.request.pretty_host` is the server IP**, not the hostname.
   Match via SNI (`flow.client_conn.sni`), the Host header, or the `DE_NarutoAlpha...` path
   (`is_de_cdn()`).
3. **304 responses bypass the patch.** `request()` strips `If-None-Match` / `If-Modified-Since`
   for patched paths. Files already cached as fresh by the client never hit the network at all,
   so the user must clear the client cache
   (`%APPDATA%\Naruto Online\Browers\Cache\<account>\Cache\*`) after patch changes.
4. **Patched responses get `Cache-Control: no-store`** so turning the patch off returns to German.
5. **Placeholder safety:** only substitution tokens (`%1`, `{0}`, `#x#`) must match between DE
   and EN; HTML `<font>` tags may differ. A regex typo once silently disabled this check, so test
   `merge.PLACEHOLDER` when touching it.
6. **`is_text()` decides what counts as display text.** Identifiers, paths, link commands
   (`openui,5,1`) and csv ids must never be swapped.
7. **Bump `MERGE_VERSION`** in `en_patch.py` whenever merge output changes, or stale saved
   merges keep being served.
8. **XML files with zero translations are passed through byte-for-byte** (no reformatting risk).
9. **SWF swap caveat:** an EN UI file can carry EN-specific event content (dates, reward-slot
   layout). Naruto's Froggy (`flash/activity/minRenQianBao*.swf`) broke that way and is
   commented out. `*Plugin.swf` and `flash/core/` are excluded on purpose (code differs
   between builds).
10. The client's `debug.log` is at `C:\Program Files (x86)\Naruto Online\debug.log`; the client
    runs elevated.

## Testing without the game

Simulate mitmproxy flows with stub objects; nothing needs a live proxy:

```python
import en_patch
class O: pass
f = O(); f.request = O(); f.client_conn = O(); f.response = O()
f.request.pretty_host = "104.18.49.72"          # what local mode really reports
f.request.headers = {}; f.client_conn.sni = en_patch.DE_HOST
f.request.path = "/DE_NarutoAlpha9.53Build300/config/props/NinjaAttributeCFG.cfg"
f.response.status_code = 200; f.response.headers = {}
f.response.content = open("de_NinjaAttributeCFG.cfg", "rb").read()   # fetched from the DE CDN
en_patch.EnPatch().response(f)                   # f.response.content is now the merged file
```

Checks worth keeping when changing codecs or merge logic:
- `amf3.dumps(amf3.loads(raw)) == raw` for real `.cfg` files (byte-identical round trip).
- `nfiles.write_pkg(nfiles.read_pkg(b))` decompresses to the original bytes.
- Merged XML still parses (`xml.etree.ElementTree.fromstring`).
- Coverage report: count `replaced` / `fallback` / `no_en` / `placeholder_mismatch` / `same`
  from the `st` counter. Last measured: about 95 % of differing game text becomes English.

## Working with the user

- The user runs the proxy (admin) and the game; you can't see the game window. Ask for
  screenshots and read `patch.log` to confirm what was patched.
- Trusting the mitmproxy CA and deleting the client cache are the user's actions; give them
  exact PowerShell commands (`$env:...`, not `%...%`).
- Keep the patch **display-only**: never alter ids, numbers, prices, links or anything sent to
  the game server.
