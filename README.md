# Naruto Online DE → English patch
https://www.youtube.com/watch?v=jMk5ogjQWyg
Play on a **German (Oasis DE) Naruto Online server** with the game shown in **English**.

A small local proxy sits between the Naruto Online desktop client and the German resource
CDN. When the client downloads its text tables, the proxy fetches the same files from the
official **English** CDN and swaps in the English strings. All ids, numbers, links and game
data stay exactly as the German server sent them, so only what you *read* changes.
Optionally it can also serve English copies of selected Flash UI files (menus, icon labels,
window art).

Nothing is installed into the game, no game files on disk are modified, and nothing is sent
anywhere except the normal game CDNs.

| Before | After |
|---|---|
| `[Haupthandlung] Teamkampf-Drill`, `Leben`, `Prämiensaal`, `Narutos Geldbörse` | `[Main Quest] …`, `Life`, `Benefit Hall`, `Naruto's Froggy` |

## What gets translated

| Part of the game | Result | How |
|---|---|---|
| Quests, items, ninjas, skills, tooltips, rewards, loading tips, rank titles, code-generated UI text | ~95 % English | text-table merge (always on) |
| Icon labels on the main HUD, buttons, many window headings | English | Flash UI swap (`swf_swap.txt`) |
| Chat, mail, some server-sent event text | stays German | sent by the server, not from files |
| A few event windows | may stay German | their English UI file doesn't fit the DE event (see below) |

## Requirements

- Windows, the **Naruto Online desktop client** (Oasis launcher, `Naruto Online.exe`)
- Python 3.10+
- [mitmproxy](https://mitmproxy.org) 12+ (`pip install -r requirements.txt`)
- Administrator rights (mitmproxy's per-process capture needs them)

## Setup (once)

1. **Install mitmproxy**
   ```powershell
   pip install -r requirements.txt
   ```

2. **Create and trust mitmproxy's certificate.** Run `mitmdump` once and close it with
   Ctrl+C; it creates `%USERPROFILE%\.mitmproxy\`. Then trust the certificate for your user:
   ```powershell
   certutil -user -addstore Root "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.cer"
   ```
   Click **Yes** on the Windows security prompt.
   > This certificate lets the proxy decrypt traffic, but the patch only decrypts the one German
   > resource CDN (`cdn-naruto-de-res.oasgames.com`). Everything else (login, game server,
   > payments) passes through untouched. Remove it any time; see [Uninstall](#uninstall).

## Every time you play

1. **Close** the game.
2. Start the proxy: right-click **`run.ps1`** → *Run with PowerShell* and accept the admin
   prompt. Leave that window open while you play.
3. Start Naruto Online and log in.

The first load after a game update takes a little longer while the patch downloads and merges
the new English files. After that they come from `cache/`.

### First run / after changing the patch: clear the client cache

The client caches what it downloads. Files cached while the patch was **off** stay German.
Clear the cache once (game closed) the first time, and after updating this patch:

```powershell
Remove-Item "$env:APPDATA\Naruto Online\Browers\Cache\*\Cache\*" -Force
```

(`Browers` is the client's own spelling.) The game just re-downloads everything.

## Choosing which Flash UI files are swapped: `swf_swap.txt`

`swf_swap.txt` lists Flash files that are served from the English build instead of the German
one, grouped by game feature. The default list has ~400 UI/art files where the English copy is
the same age or newer than the German one, which is the low-risk group.

- **Turn one off:** put `#` in front of its line and reload the game (the reload button at the
  top right of the client). No proxy restart and no cache clearing needed; swapped files are
  never stored in the client cache.
- **Why one might break:** an English UI file carries the English server's own layout, and
  sometimes event dates or reward slots. If the German server's event differs, you can see
  empty reward boxes or wrong dates. Example: *Naruto's Froggy*
  (`flash/activity/minRenQianBao*.swf`) is disabled for that reason.
- **Not in the default list:** `*Plugin.swf` (window logic) and `flash/core/` (engine). They
  are much riskier because DE and EN code can differ. Add them one at a time if you want to
  experiment.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Black game area, never loads | The proxy is intercepting more than the DE CDN. Use `run.ps1` as-is; it passes `--allow-hosts` so the login server (which only speaks old TLS) is left alone. |
| Everything still German | (1) Proxy not running, or not as admin. (2) Client cache not cleared; see above. Check `patch.log`: you should see `EN config/...` lines while the game loads. |
| `patch.log` shows nothing at all | The proxy isn't seeing the client. Make sure the process is called `Naruto Online.exe` and `run.ps1` runs elevated. |
| One window blank / broken / wrong dates | Comment out that feature's block in `swf_swap.txt`, then reload. |
| `certutil ... ERROR_PATH_NOT_FOUND` | You used `%USERPROFILE%` in PowerShell. Use `$env:USERPROFILE` as shown above. |
| After a big game update something is off | Delete `cache/` in this folder (it's rebuilt) and clear the client cache. |

## Uninstall

```powershell
certutil -user -delstore Root mitmproxy
pip uninstall mitmproxy
```
Then delete this folder and clear the client cache so no English files remain cached.

## How it works (short)

- The client loads `https://cdn-naruto-de-res.oasgames.com/<DE_NarutoAlphaX.YYBuildZZZ>/<path>`.
  Every file has its own version folder, listed in `<build>/resource.cfg`.
- Text lives in `config/**/*.cfg` (zlib + AMF3), `config/archives/*.pkg` (zlib bundles of
  AMF3/XML entries) and config XMLs. The English CDN (`cdnnarutoen-gmt.oasgames.com`) has
  the same files with the same row ids.
- `en_patch.py` (mitmproxy addon) finds the current English build, looks up each file's English
  version in the English `resource.cfg`, and overlays English text onto the German data.
  Anything the English file lacks is looked up German → Chinese source → English through the
  game's own translation tables (`config/i18n/Kv*DebugCFG.cfg`).
- A string is only replaced if its placeholders (`%1`, `{0}`, …) match, so formatted messages
  can't break.
- Any error leaves that file German; the patch never blocks the game from loading.

Details for developers and AI assistants: [AGENTS.md](AGENTS.md).

## Disclaimer

Unofficial fan tool, not affiliated with Oasis Games, Tencent or the Naruto franchise. It
changes only the text your own client displays and doesn't touch game logic or send anything
to the game server. Modifying what a client loads may still be against the game's Terms of
Service. Use at your own risk.
