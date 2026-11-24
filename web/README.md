# The authoring page (public version)

`ad-authoring-prototype.html` is the AD Authoring Prototype: a static page
that runs entirely in the browser. It was built in Muse and exported as one
self-contained HTML file.

## About the missing videos

The private prototype embeds two test clips (61 MB total). This public
version ships **without the videos**: one is a vintage TV episode whose
rights don't belong to this project, and 61 MB of video doesn't belong in a
code repo.

What remains: the full UI, the spot lists, the waveform data, and the
caption cues for both test clips — everything except the pictures. Click
**[+ Add clip]** and load your own video to use it. The spot thumbnails
(small stills) remain as UI examples.

## Use it

Open the file in a browser, or serve this folder with any static server
(for example `python3 -m http.server` from this folder, then open
http://127.0.0.1:8000/ad-authoring-prototype.html).

- **[+ Add clip]** loads a local video. **Generate spots** finds its quiet
  gaps and marks them as spots (timings only — you write the lines).
- **Send for full scan** (needs the `server/` program running) transcribes
  the clip, finds pauses and scene changes, and drafts suggested lines.
- **Save progress / Restore progress** saves your work to a file you keep.
  There is no autosave, by design.

See `../README.md` and `../HANDOFF.md` for the full picture.
