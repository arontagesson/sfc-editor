#!/usr/bin/env python3
"""Compatibility test 2: subtitle sync + text sizes + audio track layout + markers.

usage: python build_test2.py <compat-test dir> [ROOT]
ROOT = the ReelTest folder on the PC (default C:/Users/aront/ReelTest).
Reads media/info.json and test2/words.json (from `python -m sfc.transcribe`). Writes into test2/:
  01_test2.fcpxml          captions as text clips (chunks + karaoke), size ladder, PNG, SFX/music
                           with audio roles, markers + chapter markers
  02_ljudspar.fcpxml       same edit, dialogue as its own audio clip on lane -1 (track-layout variant)
  03_undertexter.srt       word-timed SRT, starts with a 1-frame "." at 0:00 so it lands right
  04_markorer.edl          timeline markers for Resolve's "Import Timeline Markers from EDL"
"""
import json, os, re, sys, urllib.parse
from xml.sax.saxutils import escape, quoteattr

kit = sys.argv[1]
ROOT = (sys.argv[2] if len(sys.argv) > 2 else "C:/Users/aront/ReelTest").replace("\\", "/").rstrip("/")
info = json.load(open(os.path.join(kit, "media", "info.json"), encoding="utf-8"))
words = json.load(open(os.path.join(kit, "test2", "words.json"), encoding="utf-8"))["words"]
FPS, W, H, SEC = info["fps"], info["width"], info["height"], info["section_sec"]
D = info["durations"]; SRC = D["testklipp.mp4"]; N = len(info["sections"])
out_dir = os.path.join(kit, "test2")

def fr(s): return int(round(s * FPS))
def t(s):
    f = fr(s); return f"{f}/{FPS}s" if f else "0s"
def url(rel):
    p = f"{ROOT}/{rel}"
    return "file:///" + p[0] + ":" + urllib.parse.quote(p[2:]) if p[1] == ":" else "file://" + urllib.parse.quote(p)
def pos(x, y): return ((x - W / 2) / H * 100, (H / 2 - y) / H * 100)
def hexcol(h):
    h = h.lstrip("#"); return " ".join(f"{int(h[i:i+2], 16) / 255:.3f}" for i in (0, 2, 4)) + " 1"

# ------------------------------------------------------------ captions from word timings
def chunk_words(ws, maxw=3, gap=0.35):
    """1-3 words per line; break after punctuation or a pause."""
    lines, cur = [], []
    for w in ws:
        if cur and (len(cur) == maxw or w["start"] - cur[-1]["end"] > gap or re.search(r"[.!?,:;]$", cur[-1]["word"])):
            lines.append(cur); cur = []
        cur.append(w)
    if cur: lines.append(cur)
    return lines

LEAD, HOLD = 0.03, 0.25   # show a line 1 frame early, keep it up to 0.25 s after the last word
lines = chunk_words(words)
cap = []                  # (start, end, [words])
for i, ln in enumerate(lines):
    s = max(0.0, ln[0]["start"] - LEAD)
    e = ln[-1]["end"] + HOLD
    if i + 1 < len(lines): e = min(e, lines[i + 1][0]["start"] - LEAD)
    cap.append((s, max(e, s + 0.2), ln))

def clean(w): return w["word"].upper()

# ------------------------------------------------------------ shared XML bits
ts_n = [0]
def title(lane, at, dur, runs, xy, name):
    defs, body = [], []
    for txt, size, col, stroke in runs:
        ts_n[0] += 1; tid = f"ts{ts_n[0]}"
        st = f' strokeColor="0 0 0 1" strokeWidth="{stroke}"' if stroke else ""
        body.append(f'<text-style ref="{tid}">{escape(txt)}</text-style>')
        defs.append(f'<text-style-def id="{tid}"><text-style font="Arial Black" fontSize="{size}" fontFace="Regular" '
                    f'fontColor="{hexcol(col)}"{st} alignment="center"/></text-style-def>')
    p = pos(*xy)
    return (f'<title ref="basictitle" lane="{lane}" offset="{t(at)}" name={quoteattr(name)} start="0s" duration="{t(dur)}">'
            f'<text>{"".join(body)}</text>{"".join(defs)}<adjust-transform position="{p[0]:.3f} {p[1]:.3f}"/></title>')

def aclip(ref, lane, at, dur, role, gain=None, keys=None, start=0.0, name=None, extra=""):
    vol = ""
    if keys:
        kf = "".join(f'<keyframe time="{t(start + k)}" value="{v}dB"/>' for k, v in keys)
        vol = f'<adjust-volume amount="{keys[0][1]}dB"><param name="amount"><keyframeAnimation>{kf}</keyframeAnimation></param></adjust-volume>'
    elif gain is not None:
        vol = f'<adjust-volume amount="{gain}dB"/>'
    return (f'<asset-clip ref="{ref}" lane="{lane}" offset="{t(at)}" name={quoteattr(name or ref)} start="{t(start)}" '
            f'duration="{t(dur)}" audioRole="{role}" tcFormat="NDF"{extra}>{vol}</asset-clip>')

def resources():
    r = ['<resources>',
         f'<format id="fmt" name="FFVideoFormat{W}x{H}p{FPS}" frameDuration="1/{FPS}s" width="{W}" height="{H}"/>',
         f'<asset id="cam" name="testklipp.mp4" start="0s" duration="{t(SRC)}" hasVideo="1" format="fmt" hasAudio="1" '
         f'audioSources="1" audioChannels="2" audioRate="48000"><media-rep kind="original-media" src={quoteattr(url("media/testklipp.mp4"))}/></asset>',
         f'<asset id="sikte" name="sikte2.png" start="0s" duration="0s" hasVideo="1" format="fmt">'
         f'<media-rep kind="original-media" src={quoteattr(url("test2/sikte2.png"))}/></asset>']
    for k, f in [("whoosh", "test_whoosh.wav"), ("pling", "test_pling.wav"), ("musik", "test_musik.wav")]:
        r.append(f'<asset id="{k}" name="{f}" start="0s" duration="{t(D[f])}" hasAudio="1" audioSources="1" '
                 f'audioChannels="2" audioRate="48000"><media-rep kind="original-media" src={quoteattr(url("media/" + f))}/></asset>')
    r += ['<effect id="basictitle" name="Basic Title" uid=".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti"/>',
          '</resources>']
    return r

# spine: the whole source, cut at every section so there are 8 clips (timeline time == source time)
clips = [(i * SEC, min((i + 1) * SEC, SRC)) for i in range(N)]
def parent_of(ts): return min(int(ts // SEC), N - 1)

def build(name, dialogue_lane):
    kids = {i: [] for i in range(N)}
    def add(ts, xml): kids[parent_of(ts)].append(xml)
    # captions on V2: sections 1-4 = plain lines, 5-8 = karaoke (active word yellow)
    CAP_XY, CAP_SIZE = (540, 1300), 65
    for n, (s, e, ln) in enumerate(cap):
        if s < 4 * SEC:
            add(s, title(1, s, e - s, [(" ".join(clean(w) for w in ln), CAP_SIZE, "#FFFFFF", 4)], CAP_XY, f"UT {n+1}"))
        else:
            for k, w in enumerate(ln):
                ks = s if k == 0 else w["start"] - LEAD
                ke = e if k == len(ln) - 1 else ln[k + 1]["start"] - LEAD
                runs = [((" " if j else "") + clean(x), CAP_SIZE, "#FFD400" if j == k else "#FFFFFF", 4) for j, x in enumerate(ln)]
                add(ks, title(1, ks, ke - ks, runs, CAP_XY, f"UT {n+1}.{k+1}"))
    # size ladder on V3 (0-12 s)
    for k, size in enumerate([50, 65, 80, 95]):
        add(0.5, title(2 + k, 0.5, 11.0, [(f"RUBRIK {size}", size, "#FE6A3C", 4)], (540, 260 + k * 190), f"Storlek {size}"))
    # PNG crosshair (fixed alpha) on top, 12-18 s
    add(12.0, f'<video ref="sikte" lane="6" offset="{t(12.0)}" name="sikte2.png" start="0s" duration="{t(6.0)}"/>')
    # SFX + music (roles: effects / music)
    add(SEC * 2, aclip("pling", -2, SEC * 2, D["test_pling.wav"], "effects", gain=-6, name="pling"))
    add(SEC * 4 - 0.4, aclip("whoosh", -2, SEC * 4 - 0.4, D["test_whoosh.wav"], "effects", gain=-8, name="whoosh"))
    m0 = SEC * 6
    v7 = [w for w in words if w["start"] >= SEC * 7]; vs, ve = v7[0]["start"] - m0, v7[-1]["end"] - m0
    add(m0, aclip("musik", -3, m0, SRC - m0, "music", name="musik (ducking)",
                  keys=[(0, -6), (vs - 0.3, -6), (vs, -22), (ve, -22), (min(ve + 0.35, SRC - m0 - 0.05), -6)]))
    spine = []
    for i, (a, b) in enumerate(clips):
        label = info["sections"][i]["label"]
        dlg = ""
        if dialogue_lane:   # variant: video-only spine + dialogue as its own clip on lane -1
            dlg = aclip("cam", -1, a, b - a, "dialogue", start=a, name="dialog", extra=' srcEnable="audio"')
        markers = (f'<marker start="{t(a + 0.5)}" duration="1/{FPS}s" value={quoteattr("M " + label)} completed="0"/>'
                   f'<chapter-marker start="{t(a + 1.0)}" duration="1/{FPS}s" value={quoteattr("K " + label)}/>')
        en = ' srcEnable="video"' if dialogue_lane else ' audioRole="dialogue"'
        spine.append(f'<asset-clip ref="cam" offset="{t(a)}" name={quoteattr(label)} start="{t(a)}" duration="{t(b - a)}" '
                     f'format="fmt" tcFormat="NDF"{en}>{dlg}{"".join(kids[i])}{markers}</asset-clip>')
    x = ['<?xml version="1.0" encoding="UTF-8"?>', '<!DOCTYPE fcpxml>', '<fcpxml version="1.9">', *resources(),
         '<library>', f'<event name={quoteattr(name)}>', f'<project name={quoteattr(name)}>',
         f'<sequence format="fmt" duration="{t(SRC)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">',
         '<spine>', *spine, '</spine>', '</sequence>', '</project>', '</event>', '</library>', '</fcpxml>']
    return "\n".join(x) + "\n"

open(os.path.join(out_dir, "01_test2.fcpxml"), "w", encoding="utf-8").write(build("ReelTest test2", False))
open(os.path.join(out_dir, "02_ljudspar.fcpxml"), "w", encoding="utf-8").write(build("ReelTest test2 ljudspar", True))

# ------------------------------------------------------------ SRT (dummy "." at 0 so Resolve keeps the timing)
def srt_ts(s):
    ms = int(round(s * 1000)); return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"
srt = ["1", f"{srt_ts(0)} --> {srt_ts(1 / FPS)}", ".", ""]
for n, (s, e, ln) in enumerate(cap):
    srt += [str(n + 2), f"{srt_ts(s)} --> {srt_ts(e)}", " ".join(w["word"] for w in ln), ""]
open(os.path.join(out_dir, "03_undertexter.srt"), "w", encoding="utf-8", newline="\r\n").write("\n".join(srt))

# ------------------------------------------------------------ EDL with timeline markers (Resolve's own format)
def tc(s):
    f = fr(s); return f"{f // (3600 * FPS):02d}:{f // (60 * FPS) % 60:02d}:{f // FPS % 60:02d}:{f % FPS:02d}"
edl = ["TITLE: ReelTest test2 markorer", "FCM: NON-DROP FRAME", ""]
for i, (a, b) in enumerate(clips):
    m = a + 1.5
    edl += [f"{i+1:03d}  001      V     C        {tc(m)} {tc(m + 1/FPS)} {tc(m)} {tc(m + 1/FPS)}  ",
            f" |C:ResolveColorBlue |M:E {info['sections'][i]['label']} |D:1", ""]
open(os.path.join(out_dir, "04_markorer.edl"), "w", encoding="utf-8", newline="\r\n").write("\n".join(edl))

print(f"{len(words)} ord, {len(cap)} undertextrader, root {ROOT}")
for s, e, ln in cap[:6]: print(f"  {s:6.2f}-{e:6.2f}  {' '.join(w['word'] for w in ln)}")
