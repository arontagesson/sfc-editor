import json, os, sys, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from sfc.podclip import build_clip
from sfc import fcpxml
from sfc.preview import render
# SFC_WORK: folder with mixdown.mp3, video.mp4, words_spk.json, offsets.json, models/
WORK = os.environ.get("SFC_WORK", "/home/user/work/avsnitt6")
OUT = os.path.join(WORK, "out")
PC = "C:/Users/aront/Videos/3vligt_avsnitt6/"
# namn som behåller stor bokstav i undertexterna (allt annat blir små bokstäver)
NAMES = ["Ben", "Bosse", "Andersson", "Dennis", "Denko", "Momo", "Caroline", "Anis", "Karl", "Stockholm", "Vasastan",
         "Östermalm", "Djurgården", "NK", "Lund", "Subbee", "Pantamera", "Musikhjälpen", "CS", "Black", "Friday"]
SPECS = [
 dict(name="avsnitt6_01_ankorna", ranges=[(1444.87, 1506.45), (1531.43, 1533.30)]),
 dict(name="avsnitt6_02_kungen", ranges=[(2655.32, 2661.76), (2662.17, 2735.05)], range_offsets=[144.583, 197.921],
      speaker_overrides=[(2668.3, "M"), (2673.8, "W"), (2676.1, "M"), (2687.7, "W"), (2691.8, "M"), (2694.9, "W"),
                         (2703.6, "M"), (2711.3, "W"), (2712.6, "M"), (2716.4, "W"), (2718.8, "M")]),
 dict(name="avsnitt6_03_julklappar", ranges=[(994.06, 1030.55)]),
 dict(name="avsnitt6_04_riga", ranges=[(123.30, 155.95)]),
 dict(name="avsnitt6_05_pantamera", ranges=[(600.48, 606.25), (613.10, 630.50)]),
 dict(name="avsnitt6_06_gymkompisen", ranges=[(445.92, 473.32)]),
]
only = sys.argv[1:]
for spec in SPECS:
    if only and not any(o in spec["name"] for o in only): continue
    spec.setdefault("names", NAMES)
    job, info = build_clip(WORK, spec, PC + "synkatklipp_avsnitt6.mp4", PC + "3vligt_avsnitt6_mixdown.mp3", OUT)
    xml, srt, st = fcpxml.build(job)
    base = os.path.join(OUT, spec["name"])
    open(base + ".fcpxml", "w", encoding="utf-8").write(xml)
    open(base + ".srt", "w", encoding="utf-8", newline="").write(srt)
    offs = sorted(set(round(s[1], 2) for s in info["sync"] if s[2] > 0.45))
    weak = [s for s in info["sync"] if s[2] <= 0.45]
    print(f"{spec['name']}: {st['seconds']:.1f}s, {st['segments']} delar, {st['captions']} UT, offsets {offs}, svaga {len(weak)}, ansikten {info['faces']}")
    print("   shots:", [(round(t, 1), s) for t, s in info["shots"]])
    render(job, base + ".srt", base + "_preview.mp4", os.path.join(WORK, "video.mp4"), os.path.join(WORK, "mixdown.mp3"))
