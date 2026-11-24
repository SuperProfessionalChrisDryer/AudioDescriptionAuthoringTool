# AD scan server — v1 (scan only)

A small local program that scans a video or audio file and returns timed
Audio Description spots. It runs on your own computer; the web prototype
calls it at `http://127.0.0.1:8765`. Nothing leaves your machine except an
optional call to a drafting provider (Claude / OpenAI) — and only the
transcript and spot timings go to them, never the video itself.

v1 is **scan only**: transcription + dialogue gaps + scene changes +
drafted lines when a provider key is set. There is no TTS and no audio
export yet — those are phase 2 (see "Planned phase 2" below).

## What it does

1. `ffmpeg` extracts the audio as 16 kHz mono WAV.
2. `faster-whisper` (base model, int8, CPU) transcribes it.
3. Dialogue gaps ≥ 0.8 s (from the **transcript**, never from silence alone —
   silence can't tell speech from music) become **pause** spots. Gaps split
   by a speech burst shorter than 0.35 s are merged first.
4. `ffmpeg` scene detection (threshold 0.33) finds cuts; each cut becomes a
   **scene** spot covering the first 10 s of the new shot. A cut landing
   inside a dialogue gap is skipped — the pause spot already covers it.
5. Waveform classes are computed in 0.25 s buckets (speech / music /
   speech+music / quiet) with the adaptive quiet threshold from the
   prototype's scan notes. Laughter is never auto-detected (it overlaps
   speech); paint it by hand in the app.
6. If a drafting provider is configured, one batched API call drafts a line
   per spot (present tense, active voice, neutral third person, only visuals
   the audio doesn't already give, word budget fits the gap at ~2.6
   words/sec). Otherwise the spots come back with empty text — timings only.

## Setup

Requires Python 3.10+ and ffmpeg (which includes ffprobe).

**macOS** (Homebrew):

```sh
brew install ffmpeg
python3 -m venv ~/.venvs/whisp
~/.venvs/whisp/bin/pip install faster-whisper
```

**Ubuntu/Debian:**

```sh
sudo apt install ffmpeg python3-venv
python3 -m venv ~/.venvs/whisp
~/.venvs/whisp/bin/pip install faster-whisper
```

The Whisper base model (~150 MB) downloads on first use into
`$HF_HOME` (default `~/workspace/.venvs/hf`). No other dependencies are
needed — the server itself is standard-library only.

## Start it

```sh
./start.sh
# AD scan server v1 listening on http://127.0.0.1:8765 (Ctrl-C to stop)
```

If your venv lives somewhere else, point at it:

```sh
WHISP_VENV="$HOME/my-venv" ./start.sh
```

Or run directly: `~/path/to/venv/bin/python server.py`.
`AD_HOST` / `AD_PORT` override the listen address (default 127.0.0.1:8765).
Keep it on 127.0.0.1 — this server has no authentication and is meant for
your own machine only.

## Endpoints

### `GET /health`

```json
{"ok": true, "version": 1}
```

### `GET /`

A small help page listing the endpoints.

### `POST /scan`

Multipart form, file field **`file`** (a video or audio file, up to 2 GB),
optional form field **`provider`**:

| provider | What happens |
|---|---|
| `none` (default) | Timings only — every spot's `text` is `""`. |
| `claude` | Drafts lines via the Anthropic API. Needs `ANTHROPIC_API_KEY` set before starting the server. Model from `ANTHROPIC_MODEL` (default `claude-3-5-sonnet-20241022`). |
| `openai` | Drafts lines via the OpenAI API. Needs `OPENAI_API_KEY`. Model from `OPENAI_MODEL` (default `gpt-4o-mini`). |
| `kavi` | **Not available from the server.** There is no Muse API to call. Drafting with Kavi stays the chat flow: send the file to Kavi and the lines come back there. Returns timings only, with a note saying so. |

```sh
curl -F file=@clip.mp4 -F provider=none http://127.0.0.1:8765/scan
curl -F file=@clip.mp4 -F provider=claude http://127.0.0.1:8765/scan
```

If a provider key is missing, the scan still succeeds — spots come back
with empty text and `meta.note` explains why. An unknown provider is a
`400`; a file ffmpeg can't read is a `400` with the reason; anything else
is a `500` and the details go to the server log (stdout).

Response:

```json
{
  "spots": [
    {"start": 32.5, "end": 33.5, "type": "pause", "text": "", "gap": 1.0},
    {"start": 9.6, "end": 19.6, "type": "scene", "text": "", "gap": 0.0}
  ],
  "transcript": [
    {"start": 0.24, "end": 4.24, "text": "Hold on there honey..."}
  ],
  "wave": {
    "bucket_sec": 0.25,
    "peaks": [0.0, 0.42, 0.81],
    "classes": "ssmq..."
  },
  "meta": {
    "duration": 123.0,
    "provider": "none",
    "note": "No drafting provider selected (provider=none) — timings only. ...",
    "language": "en",
    "scene_count": 19,
    "gap_count": 2
  }
}
```

- `spots[].type` is `"pause"` (a real dialogue gap; `gap` = its length in
  seconds) or `"scene"` (a cut; `gap` is 0.0, `end` is up to 10 s after the
  cut). `text` is the drafted line, or `""` when none was drafted.
- `wave.classes` is one letter per 0.25 s bucket: `s` speech, `m` music/song,
  `x` speech+music, `q` silence/quiet. `peaks` are 0–1, normalised.
- Times are seconds, rounded to 2 decimals.

## Honest limits (v1)

- **Kavi drafting is not available from the server.** There is no Muse API
  for it to call. Kavi drafting stays the chat flow.
- **No TTS, no audio export yet.** Those are phase 2 (below).
- **English is assumed for drafting.** Transcription auto-detects the
  language, but the drafting prompt is written for English dialogue.
- **One scan at a time, in the request thread.** A 2-minute clip scans in
  ~10 s; a 14-minute episode takes a few minutes on CPU. The HTTP
  connection stays open until it finishes — set a long client timeout
  (the prototype will need one). Concurrent scans will contend for CPU.
- **Scene detection is heuristic.** Threshold 0.33 was measured against
  Clip 3: it finds all 39 stored cuts plus 4 extra. Fast cuts, fades, and
  whip-pans may be missed or doubled; the reviewer can delete or add spots.
- **The speech+music wave colour is the least reliable auto-label.**
  It is a spectral-flatness heuristic with one compromise threshold
  (0.14) for all clips: it reproduces Clip 2's stored colours at 85%
  and Clip 3's at 80%. Clip 2's guitar-under-dialogue separates cleanly
  at 0.185, but Clip 3's vintage audio is tonally narrow overall, so its
  plain speech lands in the same range — no single threshold fits both.
  Speech / music-only / quiet are reliable. The user corrects mixed
  stretches by painting, which is the point of the tool. Sung passages
  (e.g. Clip 3's theme song) are read by Whisper as speech, so they come
  out as speech instead of music — also a paint-by-hand case.
- **Pause times vary a little from run to run.** Whisper/VAD
  segmentation of noisy vintage audio shifts by seconds between runs:
  re-scanning Clip 3 found 299 transcript segments (stored run: 307)
  and 4 gaps, of which one matches a stored gap and the rest are nearby
  but different pauses. Clip 2 reproduces exactly. The reviewer adjusts
  timings in the app — that is what the app is for.
- **Drafted lines are drafts.** The provider has no eyes on the video — it
  drafts from the transcript and timings alone, so lines can miss the
  actual visuals. A human must review every line (that is what the app is
  for). A spot the provider can't describe comes back with empty text.
- **No authentication.** Bind is 127.0.0.1 only, for your own machine.

## Troubleshooting

- **First scan downloads models.** The Whisper base model (~150 MB) and
  the Silero VAD model (~2 MB) download from the Hugging Face Hub on
  first use, into `$HF_HOME`. If the first scan is slow, that is why.
- **`vad_filter` must stay on.** Transcription uses voice-activity
  detection before Whisper. Without it, the plain decoder silently drops
  stretches of quiet or music-covered dialogue (on Clip 2 it skipped
  45–53 s, 64–82 s and 91–98 s entirely, inventing 8–18 s "gaps" that
  are not real pauses). With VAD on, the Clip 2 transcript matches the
  stored one exactly.
- **Audio is passed to Whisper as a numpy array, not a file path.** The
  installed PyAV rejects the `metadata_errors` keyword faster-whisper
  passes to `av.open()`, so path input crashes. The array workaround is
  in `scan.py:transcribe` and is the same one the original Clip 2/3
  scans used.

## Planned phase 2 (not built yet)

- `POST /export` — render the finished AD as audio, using ffmpeg:
  - `mode=ad-only` — an audio file with just the synthetic AD voice, one
    line per spot at its time.
  - `mode=second-track` — the video with the AD voice added as a second,
    switchable audio track.
  - `mode=mixed` — the video's audio replaced with a ducked mix (original
    audio lowered under each AD line).
  These need a TTS step first (synthetic voice for the AD lines), which is
  also phase 2. The WebVTT the prototype already exports is the master
  timed-text script the audio is rendered **from** — captions (dialogue)
  and AD (visuals) stay separate tracks for opposite audiences and are
  never mixed into one file.
