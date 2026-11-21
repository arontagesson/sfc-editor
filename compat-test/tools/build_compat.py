#!/usr/bin/env python3
"""Build the Resolve compatibility-test timelines from media/info.json.

usage: python build_compat.py <kit_dir> [ROOT]
ROOT = where the kit folder lives on the PC (default C:/ReelTest). Writes:
  01_huvudtest.fcpxml   zooms (static + two keyframe variants), PNG overlay, transition,
                        titles, captions-as-title-clips, SFX, music ducking, markers
  02_undertexter.fcpxml FCPXML <caption> elements (subtitle track) on the plain source clip
  03_undertexter.srt    SRT that matches the 01 timeline (import onto a subtitle track)
"""
import json, os, re, sys, urllib.parse
from xml.sax.saxutils import escape, quoteattr

kit = sys.argv[1]
ROOT = (sys.argv[2] if len(sys.argv) > 2 else "C:/ReelTest").replace("\\", "/").rstrip("/")
info = json.load(open(os.path.join(kit, "media", "info.json"), encoding="utf-8"))
FPS, W, H, SEC = info["fps"], info["width"], info["height"], info["section_sec"]
D = info["durations"]

def fr(s): return int(round(s * FPS))
def t(s):
    f = fr(s); return f"{f}/{FPS}s" if f else "0s"
def url(name):
    p = f"{ROOT}/media/{name}"
    return "file:///" + p[0] + ":" + urllib.parse.quote(p[2:]) if p[1] == ":" else "file://" + urllib.parse.quote(p)
def px_to_pos(x, y):  # frame pixel (top-left origin) -> FCPXML position (% of frame height, +y up)
    return ((x - W / 2) / H * 100, (H / 2 - y) / H * 100)
def hexcol(h):
    h = h.lstrip("#"); return " ".join(f"{int(h[i:i+2], 16) / 255:.3f}" for i in (0, 2, 4)) + " 1"

FACE = px_to_pos(720, 760)  # centre of the red box in the source picture

def chunks(voice, maxw=3):
    """Split a spoken line into 1-3 word caption chunks, timed by character share."""
    out = []
    for sent in re.findall(r"[^.]+\.?", voice["text"]):
        words = sent.split()
        for i in range(0, len(words), maxw):
            out.append(" ".join(words[i:i + maxw]))
    total = sum(len(c) for c in out); pos = voice["start"]; res = []
    for c in out:
        d = voice["dur"] * len(c) / total; res.append((pos, d, c)); pos += d
    return res

def header(extra_resources=""):
    return ['<?xml version="1.0" encoding="UTF-8"?>', '<!DOCTYPE fcpxml>', '<fcpxml version="1.9">', '<resources>',
            f'<format id="fmt" name="FFVideoFormat{W}x{H}p{FPS}" frameDuration="1/{FPS}s" width="{W}" height="{H}"/>',
            f'<asset id="cam" name="testklipp.mp4" start="0s" duration="{t(D["testklipp.mp4"])}" hasVideo="1" format="fmt" '
            f'hasAudio="1" audioSources="1" audioChannels="2" audioRate="48000"><media-rep kind="original-media" src={quoteattr(url("testklipp.mp4"))}/></asset>',
            extra_resources, "</resources>"]

def footer(): return ['</spine>', '</sequence>', '</project>', '</event>', '</library>', '</fcpxml>']

def seq(name, total):
    return ['<library>', f'<event name={quoteattr(name)}>', f'<project name={quoteattr(name)}>',
            f'<sequence format="fmt" duration="{t(total)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">',
            '<spine>']

# ---------------------------------------------------------------- 01 main test
res01 = "\n".join([
    f'<asset id="sikte" name="sikte.png" start="0s" duration="0s" hasVideo="1" format="fmt"><media-rep kind="original-media" src={quoteattr(url("sikte.png"))}/></asset>',
    *[f'<asset id="{k}" name="{f}" start="0s" duration="{t(D[f])}" hasAudio="1" audioSources="1" audioChannels="2" audioRate="48000">'
      f'<media-rep kind="original-media" src={quoteattr(url(f))}/></asset>'
      for k, f in [("whoosh", "test_whoosh.wav"), ("pling", "test_pling.wav"), ("musik", "test_musik.wav")]],
    '<effect id="basictitle" name="Basic Title" uid=".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti"/>',
    '<effect id="xdiss" name="Cross Dissolve" uid="FxPlug:4731E73A-8DAC-4113-9A30-AE85B1761265"/>',
])

secs = info["sections"]
clips = []  # (src_in, src_out)
for i in range(len(secs)):
    a = i * SEC + 0.5
    b = a + 5.0 if i < len(secs) - 1 else min(a + 5.4, D["testklipp.mp4"] - 0.1)
    clips.append((a, b))
offsets, pos = [], 0.0
for a, b in clips: offsets.append(pos); pos += b - a
TOTAL = pos

def to_local(i, timeline_s):  # timeline seconds -> local (source) time of spine clip i
    return clips[i][0] + (timeline_s - offsets[i])

ts_n = [0]
def title(lane, at_local, dur, runs, transform="", param="", name="Titel"):
    """runs = [(text, font, size, hexcolor, stroke)]"""
    defs, body = [], []
    for txt, font, size, col, stroke in runs:
        ts_n[0] += 1; tid = f"ts{ts_n[0]}"
        st = f' strokeColor="0 0 0 1" strokeWidth="{stroke}"' if stroke else ""
        body.append(f'<text-style ref="{tid}">{escape(txt)}</text-style>')
        defs.append(f'<text-style-def id="{tid}"><text-style font={quoteattr(font)} fontSize="{size}" fontFace="Regular" '
                    f'fontColor="{hexcol(col)}"{st} alignment="center"/></text-style-def>')
    return (f'<title ref="basictitle" lane="{lane}" offset="{t(at_local)}" name={quoteattr(name)} start="0s" duration="{t(dur)}">'
            f'{param}<text>{"".join(body)}</text>{"".join(defs)}{transform}</title>')

def audio(ref, lane, at_local, dur, gain=None, keys=None, start=0.0, name=None):
    vol = ""
    if keys:
        kf = "".join(f'<keyframe time="{t(start + k)}" value="{v}dB"/>' for k, v in keys)
        vol = f'<adjust-volume amount="{keys[0][1]}dB"><param name="amount"><keyframeAnimation>{kf}</keyframeAnimation></param></adjust-volume>'
    elif gain is not None:
        vol = f'<adjust-volume amount="{gain}dB"/>'
    return (f'<asset-clip ref="{ref}" lane="{lane}" offset="{t(at_local)}" name={quoteattr(name or ref)} '
            f'start="{t(start)}" duration="{t(dur)}" tcFormat="NDF">{vol}</asset-clip>')

def zoom_kf(t0, t1, s1, target):
    px, py = -s1 * target[0], -s1 * target[1]
    return ('<adjust-transform position="0 0" scale="1 1">'
            f'<param name="position"><keyframeAnimation><keyframe time="{t(t0)}" value="0 0"/>'
            f'<keyframe time="{t(t1)}" value="{px:.3f} {py:.3f}"/></keyframeAnimation></param>'
            f'<param name="scale"><keyframeAnimation><keyframe time="{t(t0)}" value="1 1"/>'
            f'<keyframe time="{t(t1)}" value="{s1} {s1}"/></keyframeAnimation></param></adjust-transform>')

srt_items = []  # (timeline start, dur, text)
spine = []
for i, (a, b) in enumerate(clips):
    transform, kids = "", []
    label = secs[i]["label"]
    v = secs[i]["voice"]
    if i == 1:   # T2 static punch-in, red box should land on the green cross
        s = 1.25; transform = f'<adjust-transform position="{-s*FACE[0]:.3f} {-s*FACE[1]:.3f}" scale="{s} {s}"/>'
        kids.append(f'<video ref="sikte" lane="2" offset="{t(a)}" name="sikte (mitt)" start="0s" duration="{t(15.0)}"/>')
        kids.append(audio("pling", -2, a, D["test_pling.wav"], gain=-6, name="pling (punch-in)"))
    if i == 2:   # T3a keyframes in SOURCE time (clip local time starts at `start`)
        transform = zoom_kf(a + 1.0, a + 2.0, 1.3, FACE)
    if i == 3:   # T3b keyframes counted from 0
        transform = zoom_kf(1.0, 2.0, 1.3, FACE)
        kids.append(audio("whoosh", -2, b - 0.4, D["test_whoosh.wav"], gain=-8, name="whoosh (övergång)"))
    if i == 5:   # T5 titles: one placed with adjust-transform, one with the Basic Title Position param
        top = px_to_pos(540, 380)
        kids.append(title(1, a + 0.2, 4.6, [("RUBRIK ÖVERST", "Arial Black", 110, "#FE6A3C", 4)],
                          transform=f'<adjust-transform position="{top[0]:.3f} {top[1]:.3f}"/>', name="Rubrik (transform)"))
        kids.append(title(2, a + 0.2, 4.6, [("liten etikett", "Arial", 56, "#FFFFFF", 0)],
                          param='<param name="Position" key="9999/999166631/999166633/1/100/101" value="-250 -560"/>',
                          name="Etikett (Position-param)"))
    if i == 6:   # T6 captions as title clips, one highlighted word
        cap = px_to_pos(540, 1300)
        for k, (s0, d, txt) in enumerate(chunks(v)):
            words = txt.upper().split()
            if k == 1:   # highlight the first word in yellow
                runs = [(words[0] + " ", "Arial Black", 96, "#FFD400", 5), (" ".join(words[1:]), "Arial Black", 96, "#FFFFFF", 5)]
            else:
                runs = [(" ".join(words), "Arial Black", 96, "#FFFFFF", 5)]
            kids.append(title(1, s0, d, runs, transform=f'<adjust-transform position="{cap[0]:.3f} {cap[1]:.3f}"/>',
                              name=f"UT {k+1}"))
    if i == 7:   # T7 SFX + music with volume keyframes (ducking under the voice)
        vs = v["start"] - a; ve = vs + v["dur"]
        kids.append(audio("pling", -2, a, D["test_pling.wav"], gain=-6, name="pling"))
        kids.append(audio("musik", -3, a, b - a, name="musik (ducking)",
                          keys=[(0, -6), (vs - 0.3, -6), (vs, -22), (ve, -22), (min(ve + 0.35, b - a - 0.05), -6)]))
    # SRT for the whole 01 timeline
    for s0, d, txt in chunks(v):
        srt_items.append((offsets[i] + (s0 - a), d, txt))
    marker = f'<marker start="{t(a + 0.1)}" duration="1/{FPS}s" value={quoteattr(label)}/>'
    if i == 4:   # transition between T3b and T4, centred on the cut
        spine.append(f'<transition name="Cross Dissolve" offset="{t(offsets[i] - 0.5)}" duration="{t(1.0)}">'
                     f'<filter-video ref="xdiss" name="Cross Dissolve"/></transition>')
    spine.append(f'<asset-clip ref="cam" offset="{t(offsets[i])}" name={quoteattr(label)} start="{t(a)}" '
                 f'duration="{t(b - a)}" format="fmt" tcFormat="NDF">{transform}{"".join(kids)}{marker}</asset-clip>')

out01 = header(res01) + seq("ReelTest 01 huvudtest", TOTAL) + spine + footer()
open(os.path.join(kit, "01_huvudtest.fcpxml"), "w", encoding="utf-8").write("\n".join(out01) + "\n")

# ---------------------------------------------------------------- 02 FCPXML captions
caps, n = [], 0
for sct in secs:
    for s0, d, txt in chunks(sct["voice"]):
        n += 1
        caps.append(f'<caption lane="1" offset="{t(s0)}" name={quoteattr(txt)} start="0s" duration="{t(d)}" role="SRT?captionFormat=SRT.sv">'
                    f'<text placement="bottom"><text-style ref="c{n}">{escape(txt)}</text-style></text>'
                    f'<text-style-def id="c{n}"><text-style font=".SF NS Text" fontSize="13" fontFace="Regular" '
                    f'fontColor="1 1 1 1" backgroundColor="0 0 0 1"/></text-style-def></caption>')
full = D["testklipp.mp4"]
out02 = header() + seq("ReelTest 02 undertexter", full) + [
    f'<asset-clip ref="cam" offset="0s" name="testklipp" start="0s" duration="{t(full)}" format="fmt" tcFormat="NDF">'
    + "".join(caps) + '</asset-clip>'] + footer()
open(os.path.join(kit, "02_undertexter.fcpxml"), "w", encoding="utf-8").write("\n".join(out02) + "\n")

# ---------------------------------------------------------------- 03 SRT (matches 01 timeline)
def ts(s):
    ms = int(round(s * 1000)); return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"
srt = []
for k, (s0, d, txt) in enumerate(srt_items):
    srt += [str(k + 1), f"{ts(s0)} --> {ts(s0 + d)}", txt, ""]
open(os.path.join(kit, "03_undertexter.srt"), "w", encoding="utf-8").write("\n".join(srt))

print(f"01: {len(clips)} spine clips, {TOTAL:.2f} s | 02: {n} captions | 03: {len(srt_items)} srt lines | root {ROOT}")
