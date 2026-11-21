#!/usr/bin/env python3
"""Generate the synthetic test media for the Resolve compatibility test.

usage: python3 gen_media.py <kit_dir>
Needs ffmpeg with flite + drawtext. Writes <kit_dir>/media/* and media/info.json.
All sounds here are synthetic TEST tones, not real SFX.
"""
import json, os, subprocess, sys

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H, FPS, SEC = 1080, 1920, 30, 6.0

# (label burned into the picture, spoken English line, voice delay into the section in s)
SECTIONS = [
    ("T1  Baslinje (ingen zoom)",            "Test one. Baseline. No zoom.", 0.8),
    ("T2  Statisk zoom mot röda rutan",      "Test two. Static zoom on the red box.", 0.8),
    ("T3a Animerad zoom (källtid)",          "Test three A. Animated zoom in.", 0.8),
    ("T3b Animerad zoom (från noll)",        "Test three B. Animated zoom, second method.", 0.8),
    ("T4  Övergång + whoosh",                "Test four. Cross dissolve transition.", 0.8),
    ("T5  Rubriker / titlar",                "Test five. Titles and headlines.", 0.8),
    ("T6  Undertexter som textklipp",        "Test six. Subtitles as text clips.", 0.8),
    ("T7  SFX + musik som sänks under tal",  "Test seven. Sound effects and music ducking.", 2.0),
]

def run(args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def dur(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", path])
    return float(out)

def esc(s):  # drawtext escaping
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")

def main(kit):
    m = os.path.join(kit, "media"); os.makedirs(m, exist_ok=True)
    tmp = os.path.join(kit, ".tmp"); os.makedirs(tmp, exist_ok=True)
    total = SEC * len(SECTIONS)

    # 1. voice lines
    voices = []
    for i, (_, line, delay) in enumerate(SECTIONS):
        p = os.path.join(tmp, f"v{i}.wav")
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"flite=text='{line}'", "-ar", "48000", "-ac", "2", p])
        voices.append(dict(start=i * SEC + delay, dur=round(dur(p), 3), text=line, file=p))

    # 2. picture: dark bg, grid, centre cross, red "face" box, section label, running source time
    vf = [f"drawgrid=w=108:h=96:t=1:c=white@0.18",
          f"drawbox=x={W//2-1}:y={H//2-60}:w=3:h=120:c=white@0.6:t=fill",
          f"drawbox=x={W//2-60}:y={H//2-1}:w=120:h=3:c=white@0.6:t=fill",
          "drawbox=x=670:y=690:w=100:h=140:c=red@0.9:t=fill",
          f"drawtext=fontfile={FONT}:text='ANSIKTE':x=652:y=845:fontsize=34:fontcolor=red",
          f"drawtext=fontfile={FONT}:text='källtid %{{pts\\:hms}}':x=(w-tw)/2:y=h-220:fontsize=56:fontcolor=white"]
    for i, (label, _, _) in enumerate(SECTIONS):
        vf.append(f"drawtext=fontfile={FONT}:text='{esc(label)}':x=(w-tw)/2:y=1180:fontsize=44:"
                  f"fontcolor=yellow:box=1:boxcolor=black@0.6:boxborderw=18:"
                  f"enable='between(t,{i*SEC},{(i+1)*SEC})'")
    # audio: voices placed at their section offsets
    ins, filt, labels = [], [], []
    for i, v in enumerate(voices):
        ins += ["-i", v["file"]]
        ms = int(v["start"] * 1000)
        filt.append(f"[{i+1}:a]adelay={ms}|{ms}[a{i}]"); labels.append(f"[a{i}]")
    filt.append("".join(labels) + f"amix=inputs={len(voices)}:normalize=0,apad,atrim=0:{total}[aout]")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x202428:s={W}x{H}:r={FPS}:d={total}", *ins,
         "-filter_complex", f"[0:v]{','.join(vf)}[vout];" + ";".join(filt),
         "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-crf", "24", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", os.path.join(m, "testklipp.mp4")])

    # 3. transparent crosshair overlay (tests PNG overlays). Drawn with PIL: ffmpeg drawbox
    #    leaves alpha at 0 on rgba input, which made the first version invisible.
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rectangle([W//2-2, H//2-140, W//2+2, H//2+140], fill=(0, 255, 170, 255))
    d.rectangle([W//2-140, H//2-2, W//2+140, H//2+2], fill=(0, 255, 170, 255))
    im.save(os.path.join(m, "sikte.png"))

    # 4. synthetic test sounds
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=color=pink:d=0.8:a=0.6",
         "-af", "highpass=f=400,afade=t=in:d=0.5,afade=t=out:st=0.5:d=0.3", "-ar", "48000", "-ac", "2",
         os.path.join(m, "test_whoosh.wav")])
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=1320:d=0.4",
         "-af", "afade=t=out:st=0.02:d=0.38", "-ar", "48000", "-ac", "2", os.path.join(m, "test_pling.wav")])
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=220:d=10", "-f", "lavfi", "-i", "sine=f=277.18:d=10",
         "-f", "lavfi", "-i", "sine=f=329.63:d=10", "-filter_complex",
         "amix=inputs=3:normalize=0,volume=0.25,tremolo=f=4:d=0.5", "-ar", "48000", "-ac", "2",
         os.path.join(m, "test_musik.wav")])

    info = dict(fps=FPS, width=W, height=H, section_sec=SEC,
                sections=[dict(label=s[0], voice=dict(start=v["start"], dur=v["dur"], text=v["text"]))
                          for s, v in zip(SECTIONS, voices)],
                durations={f: round(dur(os.path.join(m, f)), 3) for f in
                           ["testklipp.mp4", "test_whoosh.wav", "test_pling.wav", "test_musik.wav"]})
    json.dump(info, open(os.path.join(m, "info.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    for f in os.listdir(tmp): os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
    print(json.dumps(info, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main(sys.argv[1])
