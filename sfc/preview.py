#!/usr/bin/env python3
"""Render a low-res preview mp4 of an edit.json exactly as the timeline describes it
(same cuts, same zoom/position, captions burned in). For checking before import in Resolve.

usage: python -m sfc.preview <edit.json> <srt> <out.mp4> --video <local video> --audio <local audio>
"""
import argparse, json, os, subprocess, tempfile


def crop_box(seg, W=1080, H=1920):
    s = seg.get("scale", 1.0)
    fx, fy = seg.get("focus", [W / 2, H / 2]); tx, ty = seg.get("target", [W / 2, H * 0.42])
    dx = tx - W / 2 - s * (fx - W / 2); dy = ty - H / 2 - s * (fy - H / 2)
    mx, my = (s - 1) * W / 2, (s - 1) * H / 2
    dx = max(-mx, min(mx, dx)); dy = max(-my, min(my, dy))
    x0 = W / 2 - (W / 2 + dx) / s; y0 = H / 2 - (H / 2 + dy) / s
    return int(round(x0)), int(round(y0)), int(round(W / s)), int(round(H / s))


def render(job, srt, out, video, audio, w=540, h=960):
    tmp = tempfile.mkdtemp()
    parts = []
    off0 = job.get("video_offset", 0)
    for i, s in enumerate(job["segments"]):
        vin = s["in"] + s.get("video_offset", off0); dur = s["out"] - s["in"]
        x, y, cw, ch = crop_box(s)
        p = os.path.join(tmp, f"p{i:03d}.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{vin:.3f}", "-t", f"{dur:.3f}", "-i", video,
                        "-ss", f"{s['in']:.3f}", "-t", f"{dur:.3f}", "-i", audio,
                        "-map", "0:v", "-map", "1:a", "-vf", f"crop={cw}:{ch}:{x}:{y},scale={w}:{h},fps=30",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-ar", "48000", "-ac", "2", p],
                       check=True)
        parts.append(p)
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    cat = os.path.join(tmp, "cat.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", cat], check=True)
    cj = job.get("captions", {})
    font = cj.get("font", "DejaVu Sans")
    size = cj.get("size", 60) * 1.45 / 1920 * 288          # Resolve Text size -> libass units (PlayResY 288)
    outline = max(1.0, cj.get("stroke", 4) / 1920 * 288 * 0.9)
    margin = (1920 - cj.get("y", 1350)) / 1920 * 288 - size * 0.45
    style = (f"FontName={font},Bold=1,FontSize={size:.1f},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
             f"BorderStyle=1,Outline={outline:.1f},Shadow=0,Alignment=2,MarginV={margin:.0f}")
    srt_esc = srt.replace("\\", "/").replace(":", "\\:")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", cat, "-vf", f"subtitles='{srt_esc}':force_style='{style}'",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-c:a", "copy", out], check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("job"); ap.add_argument("srt"); ap.add_argument("out")
    ap.add_argument("--video", required=True); ap.add_argument("--audio", required=True)
    a = ap.parse_args()
    render(json.load(open(a.job, encoding="utf-8")), a.srt, a.out, a.video, a.audio)
    print("preview ->", a.out)
