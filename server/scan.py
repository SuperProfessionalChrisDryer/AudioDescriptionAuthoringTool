"""AD scan pipeline (v1).

Established behaviour this matches (see ~/workspace/ad-work/):
- Transcription FIRST for pause detection. Silence/volume alone cannot tell
  speech from music, so dialogue gaps come from the Whisper transcript, never
  from audio energy alone.
- Dialogue gaps >= 0.8s become pause spots. Gaps separated by a speech burst
  shorter than 0.35s are merged into one gap first.
- Scene changes come from ffmpeg scene detection (threshold 0.33 — measured
  against Clip 3: it finds all 39 stored cuts, plus 4 extra; 0.35 finds 37 and
  misses 2 real cuts, so 0.33 is the safer side).
- Waveform classes in 0.25s buckets, adaptive quiet threshold
  max(0.006, 0.18 * median RMS). Speech = overlaps a transcript segment.
  Music = audible, no speech. Speech+music = speech bucket whose Hann-
  windowed spectral flatness falls below 0.14 — a compromise threshold
  (Clip 2: 85% agreement with its stored classes; Clip 3: 80%). No
  single threshold fits both clips: Clip 2's guitar-under-dialogue
  separates cleanly at 0.185, but Clip 3's vintage audio is tonally
  narrow overall, so its plain speech lands in the same range. The mixed
  class is the least reliable auto-label; the user corrects it by
  painting. Sung passages (e.g. Clip 3's theme song) are read by Whisper
  as speech, so they come out as speech instead of music — also a
  paint-by-hand case.
  Laughter is NEVER auto-detected (it overlaps speech) — no bucket is
  labelled laughter by this code; the user paints it.

Only stdlib + numpy + faster-whisper are used. numpy and faster-whisper are
imported lazily inside the functions that need them, so a missing install
produces a clear ScanError instead of breaking the whole server.
"""

import math
import os
import re
import subprocess
import tempfile

WHISPER_MODEL = os.environ.get("AD_WHISPER_MODEL", "base")
SCENE_THRESHOLD = float(os.environ.get("AD_SCENE_THRESHOLD", "0.33"))
MIN_GAP = 0.8            # seconds; a dialogue gap must be at least this long
MERGE_BURST = 0.35       # seconds; gaps split by a shorter speech burst merge
BUCKET_SEC = 0.25        # waveform bucket length, matching the prototype
FLATNESS_THRESHOLD = 0.14  # Hann-windowed spectral flatness below this => speech+music.
# This is a COMPROMISE, not a clean separation — measured on both clips:
#   threshold  clip2 agreement  clip3 agreement
#   0.185      99.8%            39.6%   (Clip 2's own tuned value)
#   0.14       85.2%            80.0%   <- chosen (best worst-case)
#   0.10       69.4%            96.5%
# Clip 2's guitar-under-dialogue is genuinely separable; Clip 3's vintage
# audio is tonally narrow overall, so its plain speech lands in the same
# flatness range as Clip 2's mixed stretches and no single threshold fits
# both. The mixed class is therefore the least reliable auto-label; the
# user corrects it by painting (the tool's whole philosophy: the machine
# proposes, the person corrects). Speech / music-only / quiet are reliable.
WORDS_PER_SEC = 2.6      # narration speed used for word budgets
SCENE_WINDOW = 10.0      # seconds of a new shot a scene spot covers


class ScanError(Exception):
    """A scan failure. `status` is the HTTP status the server should use."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _run(cmd, timeout=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ---------------------------------------------------------------- ffmpeg ---

def ffprobe_duration(path):
    """Duration in seconds, via ffprobe (ships with every ffmpeg install)."""
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", path])
    if r.returncode != 0 or not r.stdout.strip():
        raise ScanError(
            "ffprobe could not read %r — is it a video or audio file?"
            % os.path.basename(path))
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise ScanError("ffprobe returned an unreadable duration")


def has_video(path):
    r = _run(["ffprobe", "-v", "error", "-select_streams", "v:0",
              "-show_entries", "stream=codec_type", "-of", "csv=p=0", path])
    return r.returncode == 0 and "video" in r.stdout


def extract_audio(src, dst):
    """Extract the audio as 16 kHz mono WAV (what Whisper wants)."""
    r = _run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", src,
              "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst])
    if r.returncode != 0 or not os.path.exists(dst):
        raise ScanError(
            "ffmpeg could not extract audio from %r%s"
            % (os.path.basename(src),
               (": " + r.stderr.strip()[:200]) if r.stderr.strip() else
               " — the file may have no audio track"))


def detect_scenes(path):
    """Scene-change times in seconds, via ffmpeg's scene filter."""
    r = _run(["ffmpeg", "-nostdin", "-v", "info", "-i", path,
              "-vf", "select='gt(scene,%s)',showinfo" % SCENE_THRESHOLD,
              "-f", "null", "-"], timeout=1800)
    times = sorted({round(float(t), 2)
                    for t in re.findall(r"pts_time:([0-9.]+)", r.stderr)})
    return times


# -------------------------------------------------------------- whisper ----

def transcribe(wav_path):
    """Transcribe with faster-whisper (base, int8, CPU).

    Returns (segments, language). Segments are {start, end, text} with
    times in seconds. Language is auto-detected.

    The audio is passed to Whisper as a numpy array, not a file path: the
    installed PyAV does not accept the `metadata_errors` keyword that
    faster-whisper passes to av.open(), so path input crashes. (This is
    the same workaround the original Clip 2/3 scans used.)

    vad_filter=True is REQUIRED, not optional. Without VAD, the plain
    decoder silently drops stretches of quiet or music-covered dialogue:
    on Clip 2 it skipped 45-53s, 64-82s and 91-98s entirely, inventing
    8-18s "gaps" that are not real pauses. With VAD, the transcript is
    byte-identical to the stored Clip 2 transcript (28 segments, the only
    real gap 32.53-33.53s). The VAD model (Silero, ~2 MB) downloads on
    first use.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ScanError(
            "faster-whisper is not installed in this Python environment. "
            "Install it with: pip install faster-whisper", status=500)
    import wave as wave_mod
    import numpy as np
    with wave_mod.open(wav_path, "rb") as w:
        raw = w.readframes(w.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        audio, language=None, vad_filter=True, word_timestamps=False)
    out = [{"start": round(float(s.start), 2),
            "end": round(float(s.end), 2),
            "text": s.text.strip()} for s in segments]
    return out, (info.language or "en")


# ----------------------------------------------------------------- gaps ----

def find_gaps(segments, duration, min_gap=MIN_GAP, merge_burst=MERGE_BURST):
    """Dialogue gaps from the transcript (never from silence alone).

    Raw gaps are the spaces between consecutive segments, plus the lead-in
    (0 -> first segment) and the tail (last segment -> duration). Gaps split
    by a speech burst shorter than `merge_burst` are merged, then only gaps
    of at least `min_gap` seconds survive.

    NOTE: gaps are computed from SEGMENT boundaries, not word timestamps.
    Word timestamps were tested and rejected: on Clip 2's synthetic voice
    over guitar, the word aligner drops whole lines, inventing phantom
    gaps of 9-19 seconds (e.g. 63.37-82.62) where the segment transcript
    has continuous dialogue. Segment boundaries are the reliable measure.
    """
    segs = sorted(segments, key=lambda s: s["start"])
    raw = []
    prev_end = 0.0
    for s in segs:
        if s["start"] > prev_end:
            raw.append([prev_end, s["start"]])
        prev_end = max(prev_end, s["end"])
    if duration > prev_end:
        raw.append([prev_end, duration])
    merged = []
    for g in raw:
        if merged and g[0] - merged[-1][1] < merge_burst:
            merged[-1][1] = g[1]
        else:
            merged.append(list(g))
    return [(round(a, 2), round(b, 2)) for a, b in merged
            if b - a >= min_gap]


# --------------------------------------------------------- wave classes ----

def _flatness(chunk):
    """Spectral flatness of a sample chunk (0 = pure tone, 1 = white noise).

    Music is more tonal (lower flatness) than voice alone. Uses the
    magnitude spectrum with a Hann window (without the window, leakage
    flattens the spectrum and the two classes blur together). On Clip 2
    this separates speech-only (mean 0.321) from guitar-under-dialogue
    (mean 0.099) at 99.8% with a 0.185 threshold — but that threshold
    does not transfer: Clip 3's vintage audio is tonally narrow, so its
    plain speech lands in the same range. See FLATNESS_THRESHOLD below
    for the compromise actually used.
    """
    import numpy as np
    windowed = chunk * np.hanning(len(chunk))
    spec = np.abs(np.fft.rfft(windowed))
    spec = spec[1:] + 1e-12  # drop the DC bin
    geo = float(np.exp(np.mean(np.log(spec))))
    arith = float(np.mean(spec))
    return geo / arith if arith > 0 else 1.0


def wave_classes(wav_path, segments, duration):
    """0.25s waveform buckets: peaks (0-1, normalised) and class letters.

    Classes: s = speech, m = music/song, x = speech+music, q = silence/quiet.
    Laughter (l) is never auto-assigned — see the module docstring.
    """
    import wave as wave_mod
    import numpy as np

    with wave_mod.open(wav_path, "rb") as w:
        raw = w.readframes(w.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    sr = 16000
    n_buckets = max(1, int(math.ceil(duration / BUCKET_SEC)))

    rms = np.zeros(n_buckets)
    peak_raw = np.zeros(n_buckets)
    for i in range(n_buckets):
        a = int(i * BUCKET_SEC * sr)
        b = min(len(audio), int((i + 1) * BUCKET_SEC * sr))
        chunk = audio[a:b]
        if len(chunk):
            rms[i] = float(np.sqrt(np.mean(chunk ** 2)))
            peak_raw[i] = float(np.max(np.abs(chunk)))
    global_max = float(np.max(peak_raw)) if n_buckets else 0.0
    peaks = [round(float(p / global_max), 3) if global_max > 0 else 0.0
             for p in peak_raw]

    med = float(np.median(rms)) if n_buckets else 0.0
    quiet_thr = max(0.006, 0.18 * med)
    spans = [(s["start"], s["end"]) for s in segments]

    classes = []
    for i in range(n_buckets):
        t0 = i * BUCKET_SEC
        t1 = min(duration, (i + 1) * BUCKET_SEC)
        if rms[i] < quiet_thr:
            classes.append("q")
        elif any(s0 < t1 and s1 > t0 for s0, s1 in spans):
            a = int(i * BUCKET_SEC * sr)
            b = min(len(audio), int((i + 1) * BUCKET_SEC * sr))
            chunk = audio[a:b]
            if len(chunk) >= 512 and _flatness(chunk) < FLATNESS_THRESHOLD:
                classes.append("x")
            else:
                classes.append("s")
        else:
            classes.append("m")
    return {"bucket_sec": BUCKET_SEC, "peaks": peaks,
            "classes": "".join(classes)}


# ----------------------------------------------------------------- spots ---

def build_spots(gaps, scenes, duration):
    """Assemble the spot list: pause spots from gaps, scene spots from cuts.

    A scene spot covers the first SCENE_WINDOW seconds of the new shot
    (clamped at the next cut and at the end of the clip). A cut that lands
    inside a dialogue gap, or within 1s before one, is skipped — the pause
    spot already covers that moment.
    """
    spots = []
    for a, b in gaps:
        spots.append({"start": a, "end": b, "type": "pause", "text": "",
                      "gap": round(b - a, 2)})
    for i, t in enumerate(scenes):
        if any(a - 1.0 <= t <= b for a, b in gaps):
            continue
        nxt = scenes[i + 1] if i + 1 < len(scenes) else duration
        end = round(min(t + SCENE_WINDOW, nxt, duration), 2)
        if end <= t:
            continue
        spots.append({"start": round(t, 2), "end": end, "type": "scene",
                      "text": "", "gap": 0.0})
    spots.sort(key=lambda s: (s["start"], s["type"]))
    return spots


def word_budget(spot):
    """How many words fit in this spot at ~2.6 words/sec of narration."""
    if spot["type"] == "pause":
        return max(2, round(spot["gap"] * WORDS_PER_SEC))
    window = spot["end"] - spot["start"]
    return min(20, max(5, round(window * WORDS_PER_SEC)))


# -------------------------------------------------------------- pipeline ---

def run_scan(upload_path, provider):
    """Full v1 pipeline. Returns the /scan response dict."""
    import draft

    duration = ffprobe_duration(upload_path)
    video = has_video(upload_path)
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "audio.wav")
        extract_audio(upload_path, wav)
        segments, language = transcribe(wav)
        gaps = find_gaps(segments, duration)
        scenes = detect_scenes(upload_path) if video else []
        wave = wave_classes(wav, segments, duration)
    spots = build_spots(gaps, scenes, duration)
    texts, note = draft.draft_lines(spots, segments, provider, language)
    for spot, text in zip(spots, texts):
        spot["text"] = text
    meta = {"duration": round(duration, 2),
            "provider": provider,
            "note": note,
            "language": language,
            "scene_count": len(scenes),
            "gap_count": len(gaps)}
    return {"spots": spots, "transcript": segments, "wave": wave,
            "meta": meta}
