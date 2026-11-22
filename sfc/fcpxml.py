#!/usr/bin/env python3
"""edit.json -> FCPXML timeline for DaVinci Resolve (free), + matching SRT.

Only uses what the Resolve compatibility tests confirmed:
  * asset-clips with static adjust-transform (scale + position)        (test 1, T2)
  * keyframed transforms with keyframe times in SOURCE time             (test 1, T3a)
  * Basic Title -> Resolve "Text" clip; position via adjust-transform,
    font/colour/size carried over, several colour runs per clip         (test 1, T5/T6)
  * connected audio clips with volume                                   (test 1, T7)
Not used: FCPXML <caption> (ignored by Resolve 19), Position param on titles, markers.

edit.json:
{
  "name": "avsnitt6_klipp1",
  "fps": 60, "width": 1080, "height": 1920,
  "video": {"path": "C:/.../video.mp4", "duration": 3103.77},
  "audio": {"path": "C:/.../mixdown.mp3", "duration": 2893.19},     # optional separate dialogue track
  "video_offset": -8.234,            # video_time = audio_time + video_offset
  "segments": [                      # in order; times are AUDIO (transcript) seconds
     {"in": 120.50, "out": 124.10, "scale": 1.8, "focus": [585, 790]},
     ...
  ],
  "captions": {"words": [{"word": "Hej", "start": 120.6, "end": 120.9}, ...],
               "size": 60, "y": 1350, "max_words": 3, "max_chars": 16},
  "srt": true
}
focus = pixel in the SOURCE frame that should end up at "target" (default [540, 800]); the
shift is clamped so the frame never shows black edges.
"""
import json, os, re, sys, urllib.parse
from xml.sax.saxutils import escape, quoteattr


def rate(fps):
    if abs(fps - 29.97) < 0.01: return 1001, 30000
    if abs(fps - 59.94) < 0.01: return 1001, 60000
    if abs(fps - 23.976) < 0.01: return 1001, 24000
    return 1, int(round(fps))


def file_url(p):
    p = p.replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        return "file:///" + p[0] + ":" + urllib.parse.quote(p[2:])
    return "file://" + urllib.parse.quote(p)


def hexcol(h):
    h = h.lstrip("#"); return " ".join(f"{int(h[i:i+2], 16) / 255:.3f}" for i in (0, 2, 4)) + " 1"


def display_word(w):
    """What a caption shows: no trailing commas/full stops or stray quotes; keep ? and !."""
    w = re.sub(r"^[\"'“”‘’]+|[\"'“”‘’]+$", "", w)
    return re.sub(r"(?<![.])[,.;:]+$", "", w) if not w.endswith("...") else w.rstrip(".")


def chunk_words(ws, max_words=3, max_chars=16, gap=0.35):
    """Caption lines: 1-3 words, <= max_chars, break after punctuation or a pause."""
    lines, cur = [], []
    for w in ws:
        if cur:
            text = " ".join(x["word"] for x in cur + [w])
            if (len(cur) >= max_words or len(text) > max_chars or w["start"] - cur[-1]["end"] > gap
                    or re.search(r"[.!?,:;]$", cur[-1]["word"])):
                lines.append(cur); cur = []
        cur.append(w)
    if cur: lines.append(cur)
    return lines


def build(job):
    fps = job.get("fps", 30); num, den = rate(fps)
    W, H = job.get("width", 1080), job.get("height", 1920)
    fr = lambda s: int(round(s * den / num))
    t = lambda f: f"{f * num}/{den}s" if f else "0s"
    off = job.get("video_offset", 0.0)
    has_audio = "audio" in job

    # ---- lay out segments on the timeline (frame-exact, no gaps)
    segs, pos = [], 0
    for s in job["segments"]:
        a_in, a_out = fr(s["in"]), fr(s["out"])
        if a_out <= a_in: sys.exit(f"segment has no length: {s}")
        segs.append(dict(s, a_in=a_in, dur=a_out - a_in, v_in=fr(s["in"] + s.get("video_offset", off)), offset=pos))
        pos += a_out - a_in
    total = pos

    def transform(s):
        sc = s.get("scale", 1.0)
        if sc == 1.0 and not s.get("focus"): return ""
        fx, fy = s.get("focus", [W / 2, H / 2]); tx, ty = s.get("target", [W / 2, H * 0.42])
        dx = tx - W / 2 - sc * (fx - W / 2); dy = ty - H / 2 - sc * (fy - H / 2)
        mx, my = (sc - 1) * W / 2, (sc - 1) * H / 2
        dx = max(-mx, min(mx, dx)); dy = max(-my, min(my, dy))
        return f'<adjust-transform position="{dx / H * 100:.3f} {-dy / H * 100:.3f}" scale="{sc:.3f} {sc:.3f}"/>'

    # ---- captions -> (timeline_start_frame, dur_frames, text)
    caps = []
    cj = job.get("captions")
    if cj:
        def to_tl(a):   # audio seconds -> timeline frame (None if cut away)
            f = fr(a)
            for s in segs:
                if s["a_in"] <= f < s["a_in"] + s["dur"]: return s["offset"] + f - s["a_in"]
            return None
        def kept(a, b):   # seconds of [a, b] that survive the edit
            return sum(max(0.0, min(b, (s["a_in"] + s["dur"]) * num / den) - max(a, s["a_in"] * num / den)) for s in segs)
        ws = []
        for w in cj["words"]:
            if kept(w["start"], w["end"]) < 0.6 * max(w["end"] - w["start"], 0.01): continue   # word mostly cut away
            st = to_tl(w["start"]) if to_tl(w["start"]) is not None else to_tl((w["start"] + w["end"]) / 2)
            if st is None: continue
            en = to_tl(max(w["start"], w["end"] - 0.01))
            en = en + 1 if en is not None and en >= st else st + fr(0.15)
            ws.append(dict(word=w["word"], start=st * num / den, end=en * num / den))
        lines = chunk_words(ws, cj.get("max_words", 3), cj.get("max_chars", 16))
        lead, hold = 1, fr(0.25)
        for i, ln in enumerate(lines):
            s = max(1, fr(ln[0]["start"]) - lead); e = fr(ln[-1]["end"]) + hold   # frame 0 is the SRT anchor dot
            if i + 1 < len(lines): e = min(e, fr(lines[i + 1][0]["start"]) - lead)
            e = min(max(e, s + fr(0.2)), total)
            if e > s: caps.append((s, e - s, " ".join(display_word(w["word"]) for w in ln)))

    # ---- XML
    vid, aud = job["video"], job.get("audio")
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<!DOCTYPE fcpxml>', '<fcpxml version="1.9">', '<resources>',
           f'<format id="fmt" name="FFVideoFormat{W}x{H}p{fps}" frameDuration="{num}/{den}s" width="{W}" height="{H}"/>',
           f'<asset id="vid" name={quoteattr(os.path.basename(vid["path"].replace(chr(92), "/")))} start="0s" '
           f'duration="{t(fr(vid["duration"]))}" hasVideo="1" format="fmt" hasAudio="1" audioSources="1" audioChannels="2" '
           f'audioRate="48000"><media-rep kind="original-media" src={quoteattr(file_url(vid["path"]))}/></asset>']
    if aud:
        out.append(f'<asset id="aud" name={quoteattr(os.path.basename(aud["path"].replace(chr(92), "/")))} start="0s" '
                   f'duration="{t(fr(aud["duration"]))}" hasAudio="1" audioSources="1" audioChannels="2" audioRate="44100">'
                   f'<media-rep kind="original-media" src={quoteattr(file_url(aud["path"]))}/></asset>')
    out += ['<effect id="basictitle" name="Basic Title" uid=".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti"/>',
            '</resources>']
    name = quoteattr(job.get("name", "klipp"))
    out += ['<library>', f'<event name={name}>', f'<project name={name}>',
            f'<sequence format="fmt" duration="{t(total)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">',
            '<spine>']
    size, cy = (cj or {}).get("size", 60), (cj or {}).get("y", 1350)
    cpos = f"0 {(H / 2 - cy) / H * 100:.3f}"
    ts_n = 0
    for k, s in enumerate(segs):
        kids = []
        if has_audio:   # dialogue from the separate recording, exactly under this segment
            kids.append(f'<asset-clip ref="aud" lane="-1" offset="{t(s["v_in"])}" name="dialog" start="{t(s["a_in"])}" '
                        f'duration="{t(s["dur"])}" audioRole="dialogue" tcFormat="NDF"/>')
        for (cs, cd, text) in caps:   # captions that START inside this segment hang off it
            if s["offset"] <= cs < s["offset"] + s["dur"]:
                ts_n += 1
                at = s["v_in"] + cs - s["offset"]
                kids.append(
                    f'<title ref="basictitle" lane="1" offset="{t(at)}" name={quoteattr(text)} start="0s" duration="{t(cd)}">'
                    f'<text><text-style ref="c{ts_n}">{escape(text.upper())}</text-style></text>'
                    f'<text-style-def id="c{ts_n}"><text-style font="Arial Black" fontSize="{size}" fontFace="Regular" '
                    f'fontColor="{hexcol("#FFFFFF")}" strokeColor="0 0 0 1" strokeWidth="4" alignment="center"/></text-style-def>'
                    f'<adjust-transform position="{cpos}"/></title>')
        mute = '<adjust-volume amount="-96dB"/>' if has_audio else ""
        en = ' srcEnable="video"' if has_audio else ""
        out.append(f'<asset-clip ref="vid" offset="{t(s["offset"])}" name={quoteattr(s.get("label", f"del {k+1}"))} '
                   f'start="{t(s["v_in"])}" duration="{t(s["dur"])}" format="fmt" tcFormat="NDF"{en}>'
                   f'{transform(s)}{mute}{"".join(kids)}</asset-clip>')
    out += ['</spine>', '</sequence>', '</project>', '</event>', '</library>', '</fcpxml>']

    srt = None
    if caps and job.get("srt", True):
        def ts(f):
            ms = int(round(f * num / den * 1000)); return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"
        srt = ["1", f"{ts(0)} --> {ts(1)}", ".", ""]   # 1-frame dot at 0:00 keeps Resolve from shifting the SRT
        for i, (cs, cd, text) in enumerate(caps):
            srt += [str(i + 2), f"{ts(cs)} --> {ts(cs + cd)}", text, ""]
        srt = "\r\n".join(srt)
    return "\n".join(out) + "\n", srt, dict(frames=total, seconds=total * num / den, segments=len(segs), captions=len(caps))


if __name__ == "__main__":
    job = json.load(open(sys.argv[1], encoding="utf-8"))
    xml, srt, info = build(job)
    base = os.path.splitext(sys.argv[2])[0]
    open(base + ".fcpxml", "w", encoding="utf-8").write(xml)
    if srt: open(base + ".srt", "w", encoding="utf-8", newline="").write(srt)
    print(f"{base}.fcpxml: {info['seconds']:.1f} s, {info['segments']} delar, {info['captions']} undertextrader")
