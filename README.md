# sfc-editor

Claude klipper short form-videor (TikTok, Reels, Shorts) och lämnar resultatet som en
**redigerbar tidslinje i DaVinci Resolve (gratis)**, inte som en färdigrenderad mp4.
Alla klipp, undertexter, rubriker, zoomar och SFX ligger på egna spår och kan justeras
som i vilket Resolve-projekt som helst.

## Så funkar det

```
råfil ──► analys ──► edit.json ──► exporter ──► .fcpxml + .srt ──► Resolve
         (whisper,   (Claudes       (kod)        (File → Import     (du finjusterar)
          tystnad,    klippbeslut)                → Timeline)
          ansikte)
```

- **`edit.json` är källan till sanningen.** Spår, klipp, zoomar, texter och ljud som data.
  "Byt hook" eller "färre SFX" ändrar bara filen, och sedan byggs tidslinjen om.
- **Resolve är tidslinjen.** Claude Code är terminal och chatt och visar ingen video,
  så vi bygger ingen egen editor. Claude är klipparen, Resolve är skärmen.
- Allt körs lokalt på PC:n med Claude Code: råfiler, SFX-bibliotek, whisper och Resolve finns där.

## Planerad tidslinje

| Spår | Innehåll |
|---|---|
| V3 | B-roll och overlays |
| V2 | Rubriker och textklipp |
| V1 | Kamera med jump cuts och punch-ins |
| ST1 | Undertexter (redigerbar text) |
| A1 | Dialog |
| A2–A3 | SFX |
| A4 | Musik (sänks automatiskt under tal) |
| Markörer | Claudes anteckningar ("omtag borttaget", "alternativ hook") |

## Klippregler
- **Klipp aldrig mitt i en replik.** Klipp bara vid ord- och meningsgränser, med 2–4 frames luft.
- Ta bort tystnad, "eh", andetag, omtag och upprepningar. Inget annat.
- Tempo skapas med punch-ins (1.0 ↔ 1.08–1.15) och en stark hook, inte genom att korta ner repliker.

## Undertexter (prio 1)
- Ordtider med exakt alignment (whisper med ordtider, gärna WhisperX eller stable-ts).
- 1–3 ord per rad, radbrytning vid naturliga pauser och skiljetecken, aldrig mitt i ett uttryck.
- Tiderna mappas genom klippen, så att texten följer den klippta tidslinjen.

## Status

| Fas | Innehåll | Status |
|---|---|---|
| 0 | Kompatibilitetstest: vad överlever FCPXML-importen i Resolve gratis? | **Väntar på testresultat**, se [`compat-test/`](compat-test/) |
| 1 | Analys + `edit.json` + exporter (klipp, undertexter, SFX, markörer) | Ej påbörjad |
| 2 | Animerade zoomar mot ansiktet, rubriker, b-roll, musik med ducking | Ej påbörjad |
| 3 | Lärande: jämför Arons färdiga tidslinje med Claudes förslag och uppdatera stilguiden | Ej påbörjad |

## Kompatibilitetstest
Se [`compat-test/LÄS_MIG.txt`](compat-test/LÄS_MIG.txt). Lägg mappen i `C:\Users\aront\ReelTest\`
och importera `01_huvudtest.fcpxml` (bocka i *Use sizing information*).
Det testar statisk och animerad zoom, PNG-overlay, övergång, rubriker, undertexter
(tre sätt), SFX, musik-ducking och markörer.
