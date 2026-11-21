# Instruktioner för Claude i sfc-editor

- Svara på svenska.
- Målet är en **redigerbar tidslinje** för DaVinci Resolve gratis (Windows) via FCPXML + SRT,
  inte en renderad video. Resolve gratis har ingen extern skriptning (21.1+), så allt går via import.
- **Skriv aldrig över originalfiler.** Lägg arbetsfiler i `.reel_work/` bredvid råfilen.
- Använd riktiga Windows-sökvägar i tidslinjen. På Windows heter Python oftast `python` eller `py`.
- Saknas ffmpeg eller whisper: säg vilket och stanna.

## Arons standardval
- Klipp **aldrig** mitt i en replik. Bara vid ord- och meningsgränser. Ta bara bort tystnad,
  "eh", andetag, omtag och upprepningar. Tempo kommer från punch-ins och hook, inte från avbrutna repliker.
- Undertexter är prio 1: välj ett tydligt format, 1–3 ord per rad, i synk med ordtiderna.
- Hook med riser, punch-ins och SFX från Arons eget bibliotek (variera, samma ljud högst två
  gånger per klipp). Hitta aldrig på eller generera ljud i riktiga klipp.
- Inga inzoom-freezes om Aron inte ber om det.
- Format: vertikalt 1080×1920 (TikTok, Reels, Shorts).

## Läget just nu
Fas 0, kompatibilitetstestet i `compat-test/`, avgör vilka FCPXML-funktioner Resolve tar emot
(keyframes, titlar, captions, övergångar, volym-keyframes). Bygg inte på en funktion
som testet inte har bekräftat.
