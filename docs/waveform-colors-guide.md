# Waveform colors — how they work

A plain-language guide for the AD Authoring Prototype's waveform.
(Kept here, out of the app, so the app stays uncluttered.)

## The colors

| Color | Meaning |
|---|---|
| Blue | Speech — someone is talking (or singing words) |
| Green | Music / song — sound, but no speech |
| Teal | Speech + music — talking over music |
| Violet | Speech + laughter — talking and laughing at the same time |
| Pink | Laughter / effects — laughing, or a sound effect, with no speech |
| Grey | Silence / quiet — (almost) nothing audible |

## How the program decides the colors

The scan cuts the audio into quarter-second slices and measures each one:

- **Loudness.** Every slice's loudness is measured. A slice is called quiet
  when it is much softer than the clip as a whole — the threshold adapts to
  each clip, because old recordings have a louder background hiss than
  clean modern ones.
- **Speech.** The scan transcribes the audio (Whisper). Any slice that
  overlaps a transcribed word is speech.
- **Music.** Sound that is loud enough but has no transcribed words in it.
  The Letter People's opening theme (0:00–0:19) is forced to music: it is
  sung, and the transcriber wrongly reads sung lyrics as speech.
- **Speech + music.** A speech slice whose sound is unusually *tonal*
  (measured as "spectral flatness" — music has strong, steady tones, voice
  is noisier). In Clip 2 the guitar under the dialogue measures clearly
  more tonal than dialogue alone, so those slices become teal.
- **Laughter.** This is the honest weak spot. Laughter usually happens
  *on top of* talking, so no measurement in this scan can separate it
  from speech. The program does not pretend to detect it: no slice is
  ever automatically colored laughter. If you hear laughter, paint it
  yourself (see below) — that is the point of the tool.

The colors are the scan's best guess, not a verdict. You correct them;
the program remembers your correction.

## Painting (recoloring) a stretch

Painting changes the color of a stretch of waveform. It never changes the
audio itself — only the colored guide on screen.

- **Choose a color** by clicking one of the class buttons in the
  "Waveform Colors" dropdown. That color is now your brush.
- **Drag to paint:** click on the waveform and drag across the stretch
  you want to recolor. The dragged range gets the brush color. Release
  to finish.
- **Click to paint:** clicking once (without dragging) recolors a fixed
  length around the playhead. Choose the length with the small selector
  next to the class buttons: the current spot's window, 5 seconds, or
  1 second.
- **Mixed colors:** painting a non-speech color onto a stretch that is
  already speech does not erase the speech — it blends into the mixed
  color. Painting laughter onto speech makes violet (speech + laughter);
  painting music onto speech makes teal (speech + music). Painting
  speech onto a mixed stretch turns it back into plain speech.
- **Undo:** every paint action can be undone (Undo button, or Ctrl+Z).
- **Reset this spot:** the "Reset colors for this spot" button restores
  the program's original measured colors for the selected spot's window
  only — your other painting stays untouched.
- **Reset the whole clip:** "Reset colors to scan" (in the same dropdown)
  restores the program's original colors for the entire clip.

## What the colors are for

They are a map of where description can go. Grey stretches are the
natural pauses where a line fits without stopping the video. Blue
stretches mean someone is talking, so a line there would have to wait
for a pause or pause the playback (a "< Standard Gap" spot). Teal and
violet stretches warn you that music or laughter is underneath the
talking — description there has to compete with sound the audience
needs to hear.
