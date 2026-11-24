# Handoff — AD Authoring Tool

*For the next person (or the next AI) picking this project up. Last updated:
2026-11-24.*

## What this is

Software that scans a video and helps a human author **Audio Descriptions
(AD)** — timed lines describing what's on screen, for blind and low-vision
viewers. It started as a student project and is being shared so it can help
people. The user (Chris) directs it in small steps; the governing principle
throughout is **the machine proposes, the person decides**.

## The two parts

| Part | What it is | Where |
|---|---|---|
| **Authoring page** | Static HTML page. Video + transport + color-coded waveform timeline + spot editor + spot list. Runs entirely in the browser. | `web/ad-authoring-prototype.html` |
| **Scan server** | Small local Python program. Transcribes audio (faster-whisper), finds dialogue pauses and scene changes (FFmpeg), drafts AD lines via a swappable AI provider. Runs on `127.0.0.1:8765`. | `server/` |

The page can do a light local scan on its own (**Generate spots**: quiet gaps
from the audio, timings only). The **full** scan (transcription, scenes,
suggested lines) needs the server, via the **Send for full scan** button.

## Current state (2026-11-24)

**Working, tested on real clips:**

- Authoring page: two built-in test clips in the private version (Mannequins,
  2:03; The Letter People "Mr. Y" episode, 14:01) with 16 and 33 spots;
  fully editable spots (drag edges, type exact times, nudge ±0.1s, change
  type, delete, add at playhead); timeline zoom; waveform from real measured
  audio, color-coded by sound class, paintable by dragging; per-spot review
  status (Not reviewed / Edited / Reviewed); Undo; yellow clamp warnings;
  floating status toasts; draggable dividers (stage vs. spot rail, and
  vertical: video / waveform / description); manual Save/Restore of progress
  as a file; delete-clip confirmation; [+ Add clip] + Generate spots for
  new clips.
- Captions: real caption cues for the two built-in clips (28 + 307 cues),
  downloadable as separate WebVTT, clearly labeled apart from the AD script.
- Scan server v1: `GET /health`, `POST /scan` (multipart file ≤ 2 GB,
  provider `none` / `claude` / `openai` / `kavi`). Clip 2 reproduces exactly
  (28 transcript segments, 2 pause spots, 13.2 s); the full 14-minute
  episode scans in ~1m44s (299 segments, 46 spots). CORS headers fixed so
  the published page can read the server's replies.
- Page wiring: Send for full scan with a drafter picker; a finished scan
  loads spots, waveform colors, and a separate captions track into the clip.
  If the server isn't running, the button says so and sends nothing.

**Not built yet (phase 2):**

- `/export` endpoint on the server: the three audio shapes — AD-only audio
  track, second audio track embedded in the video, ducked mix replacing the
  video's audio — all rendered by FFmpeg from the WebVTT master script.
  The export menu in the page lists them and honestly says they aren't
  built yet.
- Drafting with a live Claude/OpenAI key: the missing-key path is tested;
  a live API call is not.
- Surfacing "highlight for review" inside the app: flagged caption words
  and uncertain AD timings should be visibly highlighted; the Approve
  button is the mechanism. (Standing rule, agreed 2026-11-20.)

## Key design decisions (don't undo these casually)

1. **Transcription first, never silence alone.** Silence detection cannot
   tell speech from music (learned the hard way on Clip 2). Pauses come
   from the Whisper transcript. VAD is required in the server pipeline.
2. **Manual save, always.** No autosave, by design. The user once got
   soft-locked by autosave in Sierra point-and-click games and does not
   trust it. Saving is a file you choose to write (Save/Restore progress).
3. **The AI is a swappable plug.** The drafter is one setting: Kavi /
   Claude / OpenAI / None (timings only). Whisper transcription and
   pause/scene detection are local code and need no AI at all. Kavi
   drafting has no server API — it stays the chat flow (send the file to
   Kavi in chat).
4. **WebVTT is the master timed-text script.** The AD audio track is
   rendered *from* it, not a competing output. Captions (dialogue, for
   deaf/hard-of-hearing viewers) and AD (visuals, for blind/low-vision
   viewers) are separate tracks for opposite audiences in the same file
   format — never mixed, separate downloads, clearly labeled. AD drafting
   must never describe what the audio/captions already say.
5. **A standard gap is 3.0 s (~7 words).** A spot whose natural pause is
   shorter than that is labeled "< Standard Gap" — playback pauses while
   the line is read.
6. **Highlight for review.** Any questionable area — garbled words,
   uncertain timings — gets flagged so the reviewer knows where to pay
   attention. Approve clears it.
7. **In-app text stays minimal.** Explanations live in docs/ or in chat,
   not in the app. The app must never scroll; messages float as toasts and
   never shift the layout.

## How to run it

**Page:** open `web/ad-authoring-prototype.html` in a browser, or serve
`web/` with any static server. Click [+ Add clip] to load a video.

**Server:** needs Python 3.10+, FFmpeg, and faster-whisper
(`cd server && ./start.sh`; see `server/README.md` for setup, endpoint
contract, provider keys, and troubleshooting). The server binds only
`127.0.0.1` — nothing leaves the machine except an API call to the
drafter provider you pick, if any.

## Known limits (honest list)

- Clip 3's pause spots vary run to run (Whisper/VAD variability on noisy
  vintage audio); the reviewer adjusts timings in the app.
- The speech+music waveform class is the least reliable auto-label
  (~85% / 80% on the test clips); laughter cannot be auto-detected at all
  (it overlaps speech) — paint it by hand.
- Clip 3's caption timings are segment-level only, coarse to about ±0.5 s;
  75 caption cues carry flagged Whisper garbles (39 systematic, safe to
  bulk-fix — see `examples/` notes; 36 need a human listen).
- Drafting with a live Claude/OpenAI key is untested. Concurrent scans
  are untested. Upload cap 2 GB. Drafting assumes English.
- The public web version ships **without built-in videos** (see below).
- The Send-for-full-scan round trip was verified from curl, not live from
  the page with a real pointer/file.

## Why the public web version has no built-in videos

The private prototype embeds its two test clips (61 MB total). One is a
vintage TV episode whose rights don't belong to this project, and 61 MB of
video doesn't belong in a code repo. The public page therefore loads with
its spots, waveform, and caption data intact but no video — add your own
clip with [+ Add clip]. The spot thumbnails (small stills) remain as UI
examples. If a public-domain sample is wanted later, *Steamboat Willie*
(1928, public domain in the US) is the suggested first test film.

## File map

```
README.md                  project overview + quick start (this is the front door)
HANDOFF.md                 this file — state, decisions, what's next
LICENSE                    MIT
web/
  ad-authoring-prototype.html   the authoring page (media-free public version)
  README.md                how the page relates to the private prototype
server/
  server.py                stdlib-only HTTP server (127.0.0.1:8765)
  scan.py                  ffprobe → ffmpeg WAV → faster-whisper → gaps/scenes/wave
  draft.py                 Claude/OpenAI drafting via urllib
  start.sh                 launcher (picks the venv python)
  README.md                setup, contract, keys, limits, troubleshooting
  PIPELINE_NOTES.md        verified pipeline findings (thresholds, VAD, bugs found)
  tests/                   small verified transcripts
docs/
  waveform-colors-guide.md how each waveform color is measured + painting rules
examples/
  clip2-audio-description.vtt/.txt   example AD script from a test clip
  clip2_captions.json      example caption cues from the same clip
```

## What's next (in the order the user named them)

1. Phase 2 `/export` — the three audio shapes (needs a TTS voice choice).
2. Test drafting with a live Claude/OpenAI key.
3. Surface highlight-for-review inside the app.
4. A denser re-scan of the Letter People clip (micro-pauses + more beats).
5. A full test run on a public-domain film (Steamboat Willie first, then
   Night of the Living Dead, 1968).

## Contact / ownership

Project owner: Chris (student). License: MIT. This handoff is the
record — if something here disagrees with the code, the code as shipped is
what's true, and the handoff should be corrected.
