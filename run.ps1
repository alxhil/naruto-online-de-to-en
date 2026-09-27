# Starts the English patch proxy for the Naruto Online desktop client.
# Only traffic from "Naruto Online.exe" is captured; everything else on the PC is untouched.
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {   # local capture mode needs admin; relaunch elevated
    Start-Process powershell -Verb RunAs -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}
Set-Location $PSScriptRoot
$mitmdump = Join-Path (python -c "import sysconfig;print(sysconfig.get_path('scripts','nt_user'))") "mitmdump.exe"
if (-not (Test-Path $mitmdump)) { $mitmdump = "mitmdump" }
# Only decrypt the DE resource CDN; every other connection (login page, game server, payments)
# passes through untouched - the login host only speaks legacy TLS and breaks if intercepted.
& $mitmdump -s en_patch.py --mode 'local:Naruto Online.exe' --allow-hosts 'cdn-naruto-de-res\.oasgames\.com'
