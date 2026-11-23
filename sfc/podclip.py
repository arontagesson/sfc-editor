#!/usr/bin/env python3
"""Podcast clip builder: one moment of a wide multi-person shot -> edit.json (-> FCPXML).

Steps for one clip:
  1. exact audio->video sync for the clip (1 ms envelope correlation, detects edit jumps)
  2. drop silent gaps (> MIN_GAP) inside the chosen ranges, never inside a word
  3. split into shots at speaker changes; long shots get an extra punch-in at a sentence end
  4. frame each shot on the speaker's face (YuNet), alternating close / medium
  5. captions from word timings

Needs a work dir with: words_spk.json (words + seat per word), offsets.json (coarse chunk offsets),
the audio and video files, and models/face_detection_yunet_2023mar.onnx.
"""
import json, os, subprocess, numpy as np

SR_ENV = 16000
MIN_GAP, PAD = 0.45, 0.12          # cut silences longer than MIN_GAP, keep PAD on each side
CLOSE, MEDIUM = 2.0, 1.5
TARGET = [540, 760]                 # where the speaker's face lands (x, y) in the 1080x1920 frame
MIN_SHOT, MAX_SHOT = 1.6, 6.5       # seconds
# Arons undertextstil (Resolve Text-klipp): Montserrat Bold 40, svart kant 16, små bokstäver utom namn,
# Transform Y -313 (= y 1273 px). "Outside only" på kanten och av-bockad skugga/bakgrund sätts i Resolve.
CAPTION_STYLE = dict(font="Montserrat", face="Bold", size=40, stroke=16, y=1273, case="lower", max_words=3, max_chars=20)


def read_audio(path, t0, dur, sr=SR_ENV):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(t0, 0):.3f}", "-t", f"{dur:.3f}", "-i", path,
                          "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def env(a, hop=16):  # 1 ms log envelope, z-scored
    n = len(a) // hop
    e = np.log(np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-4)
    return (e - e.mean()) / (e.std() + 1e-9)


def local_offset(audio, video, ta, coarse, win=6.0, search=3.0):
    a = env(read_audio(audio, ta, win))
    v0 = ta + coarse - search
    v = env(read_audio(video, v0, win + 2 * search))
    c = np.correlate(v, a, mode="valid") / len(a)
    k = int(np.argmax(c))
    return round(v0 + k / 1000 - ta, 3), float(c.max())


def sync_clip(work, audio, video, a, b):
    """Offsets across [a, b]; returns list of (t, offset, corr)."""
    chunks = [o for o in json.load(open(os.path.join(work, "offsets.json"))) if o[2] > 0.55]
    def coarse(t):
        best = min(chunks, key=lambda o: abs(o[0] + 7.5 - t)); return best[1]
    out = []
    ts = list(np.arange(a, b - 3, 3.0)) or [b - 6.0]   # short range: one window ending at b
    for t in ts:
        off, c = local_offset(audio, video, t, coarse(t))
        if c < 0.45:   # maybe an edit jump: search wide
            off, c = local_offset(audio, video, t, coarse(t), search=90.0)
        out.append((round(float(t), 2), off, round(c, 2)))
    return out


def speech_mask_range(audio, a, b):
    import sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sfc.transcribe import speech_mask
    x = read_audio(audio, a, b - a)
    return speech_mask(x)  # 10 ms frames from a


def keep_pieces(audio, words, ranges):
    """Split each [in, out] range at silent gaps > MIN_GAP (that contain no word)."""
    pieces = []
    for a, b in ranges:
        m = speech_mask_range(audio, a - 0.5, b + 0.5); base = a - 0.5
        cuts, i, n = [], int(0.5 * 100), int((b - a + 0.5) * 100)
        while i < n:
            if not m[i]:
                j = i
                while j < n and not m[j]: j += 1
                g0, g1 = base + i / 100, base + j / 100
                if g1 - g0 > MIN_GAP and not any(w["start"] < g1 - PAD and w["end"] > g0 + PAD for w in words):
                    cuts.append((g0 + PAD, g1 - PAD))
                i = j
            else:
                i += 1
        cur = a
        for c0, c1 in cuts:
            if c0 > cur: pieces.append([cur, c0])
            cur = max(cur, c1)
        if b > cur: pieces.append([cur, b])
    return [p for p in pieces if p[1] - p[0] > 0.15]


def detect_faces(work, video, tv_list):
    import cv2
    det = None; seats = {"V": [], "M": [], "H": []}
    for tv in tv_list:
        p = os.path.join(work, "_face.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{tv:.2f}", "-i", video, "-frames:v", "1", p], check=True)
        img = cv2.imread(p); H, W = img.shape[:2]
        if det is None:
            det = cv2.FaceDetectorYN.create(os.path.join(work, "models", "face_detection_yunet_2023mar.onnx"), "", (W, H), 0.5, 0.3, 5000)
        _, faces = det.detect(img)
        for f in (faces if faces is not None else []):
            cx, cy = f[0] + f[2] / 2, f[1] + f[3] / 2
            seats["V" if cx < 380 else "M" if cx < 780 else "H"].append((cx, cy))
    default = {"V": (187, 817), "M": (586, 814), "H": (978, 747)}
    return {k: (tuple(np.median(np.array(v), axis=0).round().astype(int).tolist()) if v else default[k]) for k, v in seats.items()}


def shots_for(pieces, words, overrides):
    """Speaker runs over the kept pieces -> list of (t_start, seat). overrides: [(t, seat)] force a seat from t."""
    ws = [w for w in words if any(p[0] <= (w["start"] + w["end"]) / 2 < p[1] for p in pieces)]
    lab = [w["spk"] for w in ws]
    sm = []
    for i in range(len(ws)):                     # majority over 7 words
        win = [x for x in lab[max(0, i - 3):i + 4] if x != "?"]
        sm.append(max(set(win), key=win.count) if win else "M")
    runs = []
    for w, s in zip(ws, sm):
        if not runs or runs[-1][1] != s: runs.append([w["start"], s, w["end"]])
        else: runs[-1][2] = w["end"]
    merged = []                                   # merge too-short runs into the previous one
    for r in runs:
        if merged and (r[2] - r[0] < MIN_SHOT or merged[-1][1] == r[1]): merged[-1][2] = r[2]
        else: merged.append(r)
    shots = [(r[0], r[1]) for r in merged]
    for t, seat in overrides:                     # manual corrections win
        shots = [s for s in shots if not (t - 0.01 <= s[0] < t + 0.5)] + [(t, seat)]
    shots.sort()
    # split long shots at sentence ends for an extra punch-in
    ends = [w["end"] for w in ws if w["word"][-1:] in ".?!"]
    out = []
    for k, (t0, seat) in enumerate(shots):
        t1 = shots[k + 1][0] if k + 1 < len(shots) else pieces[-1][1]
        out.append((t0, seat)); last = t0
        for e in ends:
            nxt = [w["start"] for w in ws if w["start"] > e]
            if nxt and last + MAX_SHOT * 0.6 < nxt[0] < t1 - MIN_SHOT and nxt[0] - last > 3.5:
                out.append((nxt[0], seat)); last = nxt[0]
    return sorted(out)


def build_clip(work, spec, pc_video, pc_audio, out_dir, fps=60):
    words_all = json.load(open(os.path.join(work, "words_spk.json"), encoding="utf-8"))["words"]
    audio, video = os.path.join(work, "mixdown.mp3"), os.path.join(work, "video.mp4")
    ranges = spec["ranges"]; a, b = ranges[0][0], ranges[-1][1]
    words = [w for w in words_all if a - 1 <= w["start"] <= b + 1]
    # 1. sync
    sync, range_off = [], []
    for k, (r0, r1) in enumerate(ranges):
        sy = sync_clip(work, audio, video, r0, r1); sync += sy
        if spec.get("range_offsets"):
            range_off.append(spec["range_offsets"][k]); continue
        good = [o for _, o, c in sy if c > 0.6]
        med = float(np.median(good))
        if any(abs(o - med) > 0.02 for o in good):
            raise SystemExit(f"{spec['name']}: range {r0}-{r1} has several offsets {sorted(set(good))}; split it")
        range_off.append(round(med, 3))
    def off_at(t):
        for (r0, r1), o in zip(ranges, range_off):
            if r0 - 0.01 <= t <= r1 + 0.01: return o
        return range_off[0]
    # 2. cuts
    pieces = keep_pieces(audio, words, ranges)
    # 3/4. shots + framing
    shots = shots_for(pieces, words, spec.get("speaker_overrides", []))
    mid = [(p[0] + p[1]) / 2 + off_at((p[0] + p[1]) / 2) for p in pieces]
    faces = detect_faces(work, video, [mid[0], mid[len(mid) // 2], mid[-1]])
    faces.update({k: tuple(v) for k, v in spec.get("faces", {}).items()}); faces["W"] = (540, 960)
    # shot changes inside a piece; ignore ones that would leave a sliver (< 0.5 s) at a piece edge
    bounds = []
    for t0, _ in shots:
        if any(p[0] + 0.5 < t0 < p[1] - 0.5 for p in pieces) and all(abs(t0 - b) > 0.5 for b in bounds):
            bounds.append(t0)
    bounds.sort()
    shot_at = lambda t: ([s for s in shots if s[0] <= t + 0.5] or shots[:1])[-1][1]
    segs, last_seat, alt = [], None, 0
    for p0, p1 in pieces:
        cuts = [p0] + [t for t in bounds if p0 < t < p1] + [p1]
        for s0, s1 in zip(cuts, cuts[1:]):
            seat = shot_at(s0)
            alt = alt + 1 if seat == last_seat else 0
            sc = 1.0 if seat == "W" else spec.get("scales", [CLOSE, MEDIUM])[alt % 2]   # W = wide (off-screen voice, group)
            segs.append(dict(**{"in": round(s0, 3), "out": round(s1, 3)}, scale=sc, focus=list(faces[seat]),
                             target=TARGET, video_offset=off_at((s0 + s1) / 2), label=f"{seat} {sc:g}x"))
            last_seat = seat
    # merge consecutive segments with identical framing and contiguous audio (pure framing splits)
    merged = []
    for s in segs:
        if merged and merged[-1]["out"] == s["in"] and merged[-1]["scale"] == s["scale"] and merged[-1]["focus"] == s["focus"] \
                and merged[-1]["video_offset"] == s["video_offset"]:
            merged[-1]["out"] = s["out"]
        else: merged.append(s)
    job = dict(name=spec["name"], fps=fps, width=1080, height=1920,
               video=dict(path=pc_video, duration=3103.767), audio=dict(path=pc_audio, duration=2893.19),
               video_offset=merged[0]["video_offset"], segments=merged,
               captions=dict(CAPTION_STYLE, words=[dict(word=w["word"], start=w["start"], end=w["end"]) for w in words],
                             names=spec.get("names", []), **spec.get("caption", {})), srt=True)
    os.makedirs(out_dir, exist_ok=True)
    json.dump(job, open(os.path.join(out_dir, spec["name"] + ".edit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return job, dict(sync=sync, pieces=pieces, shots=shots, faces=faces)
