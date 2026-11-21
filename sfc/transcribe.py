#!/usr/bin/env python3
"""Transcribe speech to word timestamps, then snap each word to the real audio.

usage: python -m sfc.transcribe <media> <out_words.json> [--lang sv] [--model small]

Whisper's word times are often off by several hundred ms (a word can "start" in the
silence before it). We fix that with the audio itself: every word is trimmed to the
first and last 10 ms frame inside its window that is actually louder than the noise floor.
Needs: ffmpeg on PATH, `pip install faster-whisper numpy`.
"""
import argparse, json, subprocess
import numpy as np

SR, HOP = 16000, 160  # 10 ms frames

def load_audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768

def speech_mask(audio, margin_db=30.0):
    n = len(audio) // HOP
    rms = np.sqrt(np.mean(audio[:n * HOP].reshape(n, HOP) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    loud = np.percentile(db, 95)
    mask = db > max(loud - margin_db, np.percentile(db, 10) + 6)
    return close_gaps(mask, 12)

def close_gaps(mask, max_gap):
    """Fill silent gaps shorter than max_gap frames (stop consonants like the t in "static")."""
    mask = mask.copy(); i, n = 0, len(mask)
    while i < n:
        if not mask[i]:
            j = i
            while j < n and not mask[j]: j += 1
            if 0 < i and j < n and j - i < max_gap: mask[i:j] = True
            i = j
        else:
            i += 1
    return mask

def refine(words, mask, max_shift=0.6):
    """Snap word edges to audible speech.

    Start: if whisper's start lands in speech, walk back to where that speech run begins
    (but never into the previous word); if it lands in silence, walk forward to the first sound.
    End: the mirror image, never past the next word's start. Inside continuous speech there is
    no silence to snap to, so whisper's boundary is kept there.
    """
    n = len(mask); out = []; ms = int(max_shift * 100)
    for i, w in enumerate(words):
        lo = int(round(out[-1]["end"] * 100)) if out else 0
        nxt = int(round(words[i + 1]["start"] * 100)) if i + 1 < len(words) else n
        a = min(max(int(round(w["start"] * 100)), lo), n - 1)
        b = min(max(int(round(w["end"] * 100)), a + 1), n)
        if mask[a]:
            k = a
            while k - 1 >= max(lo, a - ms) and mask[k - 1]: k -= 1
        else:
            k = a
            while k < min(b + ms, n) and not mask[k]: k += 1
            if k >= min(b + ms, n): k = a                      # nothing audible: keep whisper's guess
        e = max(b, k + 1)
        if mask[e - 1]:
            while e < min(max(nxt, e), e + ms, n) and mask[e]: e += 1
        else:
            while e - 1 > k and not mask[e - 1]: e -= 1
        out.append(dict(w, start=round(k / 100, 2), end=round(max(e, k + 5) / 100, 2)))
    return out

def transcribe(path, lang="sv", model="small"):
    from faster_whisper import WhisperModel
    audio = load_audio(path)
    m = WhisperModel(model, device="auto", compute_type="int8")
    segs, _ = m.transcribe(audio, language=lang, word_timestamps=True, vad_filter=True)
    words = [dict(word=w.word.strip(), start=w.start, end=w.end, p=round(w.probability, 3))
             for s in segs for w in s.words if w.word.strip()]
    return refine(words, speech_mask(audio)), words

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("media"); ap.add_argument("out")
    ap.add_argument("--lang", default="sv"); ap.add_argument("--model", default="small")
    a = ap.parse_args()
    words, raw = transcribe(a.media, a.lang, a.model)
    json.dump(dict(source=a.media, words=words, raw=raw), open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"{len(words)} ord -> {a.out}")
