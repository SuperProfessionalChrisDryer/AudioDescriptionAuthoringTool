# Local scan server — pipeline notes (verified 2026-11-20)

What this file is: the tested facts about the scan pipeline, so the server
build doesn't have to rediscover them. Verified in this workspace on the real
Clip 2 / Clip 3 files. The server code itself (`server.py`) is being built
separately; this file only records what was measured.

## Environment

- FFmpeg 8.1.2 present (`/usr/bin/ffmpeg`), Python 3.12.3.
- System Python is PEP 668 locked — `pip install` fails without
  `--break-system-packages`. The server MUST use its own venv
  (`.venv/` here, created 2026-11-20, 479 MB with deps).
- `faster-whisper` 1.2.1 installs cleanly into the venv.
  `av` 19.0.2 (prebuilt wheel) is INCOMPATIBLE with faster-whisper 1.2.1:
  `av.open(..., metadata_errors="ignore")` raises TypeError. `av` 14.4.0
  would not build from source here. **Design decision: never let
  faster-whisper decode files. Decode audio with FFmpeg to raw PCM and pass
  a numpy array to `model.transcribe()`.** That path is tested and works.

## Verified steps (Clip 3, 14:01, 352x480 h264 + aac, 67 MB)

1. **Audio extraction** — `ffmpeg -i clip.mp4 -vn -ac 1 -ar 16000 -c:a
   pcm_s16le out-16k.wav` — took **~5 s** for the full 14-minute episode.
2. **Scene detection** — `ffmpeg -i clip.mp4 -vf
   "select='gt(scene,0.4)',showinfo" -f null -` — **~10 s**, 50 scenes at
   threshold 0.4; 124 scenes at 0.3. Known truth for Clip 3 is ~39 scene
   changes, so start at **threshold ~0.45** and tune against that count.
3. **Pause detection must come from transcription, NOT silence.**
   `silencedetect=noise=-45dB:d=0.8` on Clip 3 finds only **2** silences
   ≥0.8 s, while the Whisper transcript has **5** speech gaps ≥1 s. The
   episode is near-continuous dialogue/song — the "quiet" is music, not
   digital silence. The in-browser "Generate spots" quiet-gap method is a
   weaker approximation; the server's pauses are word-timing gaps from
   Whisper.

## Verified transcription (Clip 2, 2:03, synthetic-voice dialogue + guitar)

- `faster-whisper`, model `tiny`, CPU int8, word_timestamps=True, audio via
  FFmpeg-decoded numpy array: **~9 s** for the whole clip, 20 segments,
  language en. Full output saved as `tests/clip2-tiny-transcript.json`.
- **Tiny is fast but drops sung/quiet speech.** It reports word gaps of
  8.7 s, 17.1 s and 6.5 s where the earlier (larger-model) transcript has
  continuous dialogue/song (e.g. 44–56 s, 64–82 s guitar song). It also
  garbles words ("my old boat" for "my abode", "Hold on their honey").
  **Recommendation: default model `base` (or `small` for accuracy), offer
  `tiny` only as a fast-draft option.** Tiny's gaps would otherwise become
  false pause spots.
- Word-level gaps ≥1.0 s are the pause measure (segment boundaries alone
  are too coarse). In faster-whisper 1.2.1, `segment.words` entries can be
  dicts — handle both dict and object access.

## Model download (first run)

- The tiny model (~75 MB) downloads from Hugging Face on first use.
- In this sandbox the first attempt failed (Xet 403, then HF 429 rate
  limit on the shared IP, unauthenticated). Retrying after ~90 s with
  `HF_HUB_DISABLE_XET=1` succeeded. On Chris's own machine it should
  download normally — but the server's install/first-run step should
  **retry the download and show progress**, not fail silently on one 429.
- The model is now cached in `~/.cache/huggingface/hub/` here.

## What is still open (not decided here)

- Drafting provider: Kavi drafting is NOT available from the server (no
  Muse API) — Kavi drafting stays the chat flow. Claude/OpenAI need a key
  Chris pastes once; "None" (timings only) must always work.
- TTS and the three audio exports (AD-only track, embedded second track,
  mixed/replaced audio) are phase 2, after the scan proves itself.
- Page wiring ("Send for full scan" button) comes after the server is
  built and tested.
- FFmpeg must be installed on the user's machine (or bundled later);
  the server calls it as a helper program, it is not inside the server.

## How to re-run the checks

```bash
cd workspace/goals/audio-description-metadata-tool/server
.venv/bin/python -c "from faster_whisper import WhisperModel; print('ok')"
ffmpeg -v error -y -i <clip.mp4> -vn -ac 1 -ar 16000 -c:a pcm_s16le /tmp/out-16k.wav
```
