# AD Authoring Tool

A free, local-first tool for writing **Audio Descriptions (AD)** — the spoken
descriptions of what's happening on screen, for blind and low-vision viewers.

You drop in a video. The tool scans it, suggests timed description lines at
the natural pauses and scene changes, and lets you accept, edit, or rewrite
each line — with the video, a color-coded waveform, and a timeline you can
zoom into and drag. When you're done, export the script (WebVTT) or, once the
server's phase 2 lands, the finished AD audio.

## Who it's for

Anyone who needs to describe a video: access teams, teachers, small
studios, independent creators. No account, no upload, no subscription.
Your footage stays on your machine.

## Quick start

**Just the authoring page (no scan):**

1. Open `web/ad-authoring-prototype.html` in a browser (or serve the `web/`
   folder with any static server).
2. Click **[+ Add clip]** and pick a video file.
3. Click **Generate spots** — it finds the quiet gaps and marks them as
   spots. Write your descriptions in, or accept the suggestions.

**Full scan (transcription + scene changes + suggested lines):**

1. Install Python 3.10+ and FFmpeg (`brew install ffmpeg` on macOS).
2. `cd server && ./start.sh` — this starts the local scan server.
3. In the page, click **Send for full scan** on your clip and pick who
   drafts the lines: None (timings only), Claude, OpenAI, or Kavi.
   Claude/OpenAI need an API key set once (`ANTHROPIC_API_KEY` /
   `OPENAI_API_KEY`). Kavi drafting stays the chat flow — there is no Muse
   API for the server to call.

## What it does

- **Scans a video** into timed AD spots: real dialogue pauses (found by
  transcription, never by silence alone) and scene changes.
- **Suggests description lines** drafted by the AI provider you pick — or
  timings only, if you'd rather write everything yourself.
- **Lets you correct everything**: drag spot edges, type exact times,
  zoom the timeline, paint the waveform's sound colors by hand, undo.
- **Shows review status**: every spot is Not reviewed / Edited / Reviewed,
  right in the list. Questionable words and uncertain timings are flagged
  for review — the reviewer is the authority, not the machine.
- **Exports**: Audio Description as WebVTT (the master timed-text script),
  and captions as a separate, clearly labeled WebVTT file. Audio exports
  (AD-only track, second track in the video, ducked mix) are phase 2 —
  see `server/README.md`.

## Layout

```
web/      the authoring page (static HTML, runs entirely in the browser)
server/   the local scan server (Python, FFmpeg, faster-whisper)
docs/     guides — e.g. how the waveform colors are measured
examples/ example AD script + captions from a test clip
```

## Principles

- **Machine proposes, person decides.** Auto-detection is a starting point,
  not a verdict. Customization and user-friendliness matter more than
  perfect auto-detection.
- **Manual save, always.** You save your own work; there is no autosave.
- **The AI is a swappable plug.** No one is locked to any one provider.
- **WebVTT is the master script.** The AD audio track is rendered *from*
  it. Captions (dialogue) and AD (visuals) are separate tracks for
  opposite audiences — never mixed.
- **Transcribe first.** Silence can't tell speech from music, so pauses
  are found from the transcript.

## Status

Working prototype (November 2026). The page, the scan server, captions,
and the server wiring all work on real test clips. See `HANDOFF.md` for the
full state, known limits, and what's next.

## License

MIT — see `LICENSE`.
