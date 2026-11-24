"""draft.py — AI drafting of AD lines (provider-swappable).

The pipeline step that needs an AI is ONLY the wording of the lines.
Transcription (Whisper) and pause/scene detection are plain local code and
run the same way whatever provider is chosen — or with no provider at all
("none" => timings only, empty text).

Providers:
- "claude" — Anthropic API, key from ANTHROPIC_API_KEY, model from
  ANTHROPIC_MODEL (default claude-3-5-sonnet-20241022).
- "openai" — OpenAI API, key from OPENAI_API_KEY, model from OPENAI_MODEL
  (default gpt-4o-mini).
- "kavi" — NOT available from the server. There is no Muse API to call.
  Drafting with Kavi stays the chat flow: send the file to Kavi and the
  lines come back there. Requesting "kavi" returns timings only with a
  note saying exactly that.

Only stdlib (urllib) is used. One API call per batch of up to 40 spots.
"""

import json
import os
import urllib.error
import urllib.request

BATCH_SIZE = 40
REQUEST_TIMEOUT = 120  # seconds

SYSTEM_PROMPT = """You draft Audio Description (AD) lines for blind and low-vision viewers. \
Each line describes what is seen on screen during one timed spot in a video.

Rules (follow all of them):
- Present tense, active voice, neutral third person ("A man opens the door", never "I see" or "you see").
- Describe ONLY what the visuals show that the audio does not already convey. Never describe \
dialogue, lyrics, or sounds the listener can already hear, and never repeat what the dialogue \
or captions already say.
- Never write dialogue, sound effects, or camera directions as description.
- Keep each line within its word budget — a line that is too long for its spot is useless.
- If a spot has nothing new worth saying (nothing visible that the audio doesn't cover), \
return an empty string for it. Do not fill every pause.
- Be concrete and specific (who, what, where) rather than vague ("something happens").

Reply with ONLY a JSON array, one entry per spot, in the same order:
[{"i": 0, "text": "..."}, {"i": 1, "text": ""}, ...]
No explanation, no markdown, just the JSON array."""


def _spot_context(spot, segments):
    """The dialogue just before and after a spot, so the drafter knows
    what the audio already says (and must not repeat)."""
    before = [s["text"] for s in segments if s["end"] <= spot["start"]][-2:]
    after = [s["text"] for s in segments if s["start"] >= spot["end"]][:2]
    return {"before": before, "after": after}


def _build_prompt(spots, segments, language):
    from scan import word_budget
    items = []
    for i, spot in enumerate(spots):
        ctx = _spot_context(spot, segments)
        items.append({
            "i": i,
            "start": spot["start"],
            "end": spot["end"],
            "type": spot["type"],
            "gap_seconds": spot["gap"],
            "word_budget": word_budget(spot),
            "dialogue_before": ctx["before"],
            "dialogue_after": ctx["after"],
        })
    return ("The dialogue is in %s. Draft one Audio Description line per spot below. "
            "Each spot's word_budget is a hard maximum.\n\n%s"
            % (language, json.dumps(items, ensure_ascii=False)))


def _parse_drafted(text, count):
    """Parse the model's JSON array reply into a list of `count` strings.

    Returns None if the reply cannot be understood at all.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start:end + 1])
        except (ValueError, TypeError):
            return None
    if not isinstance(data, list):
        return None
    out = [""] * count
    for entry in data:
        if isinstance(entry, dict) and "i" in entry and "text" in entry:
            i = entry["i"]
            if isinstance(i, int) and 0 <= i < count:
                out[i] = str(entry["text"]).strip()
    return out


def _post_json(url, payload, headers):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=dict(headers, **{"Content-Type": "application/json"}),
        method="POST")
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _call_provider(spots, segments, language, call_one_batch):
    """Call the provider in batches of BATCH_SIZE spots. Returns
    (texts, note). On any failure, texts are empty and the note explains."""
    texts = [""] * len(spots)
    for start in range(0, len(spots), BATCH_SIZE):
        batch = spots[start:start + BATCH_SIZE]
        prompt = _build_prompt(batch, segments, language)
        try:
            reply = call_one_batch(prompt)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            return ([""] * len(spots),
                    "Drafting failed: the provider returned HTTP %d (%s). "
                    "Timings only — check the API key and try again."
                    % (e.code, body))
        except Exception as e:  # network error, timeout, ...
            return ([""] * len(spots),
                    "Drafting failed: could not reach the provider (%s). "
                    "Timings only — check the network and try again." % e)
        parsed = _parse_drafted(reply, len(batch))
        if parsed is None:
            return ([""] * len(spots),
                    "Drafting failed: the provider's reply could not be read "
                    "as a list of lines. Timings only.")
        texts[start:start + len(batch)] = parsed
    return texts, ""


def _call_claude(prompt, key):
    model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    payload = {"model": model, "max_tokens": 4000,
               "system": SYSTEM_PROMPT,
               "messages": [{"role": "user", "content": prompt}]}
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    data = _post_json("https://api.anthropic.com/v1/messages",
                      payload, headers)
    parts = data.get("content") or []
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def _call_openai(prompt, key):
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    payload = {"model": model, "temperature": 0.3,
               "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt}]}
    headers = {"Authorization": "Bearer " + key}
    data = _post_json("https://api.openai.com/v1/chat/completions",
                      payload, headers)
    choices = data.get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message") or {}).get("content") or ""


def draft_lines(spots, segments, provider, language="en"):
    """Draft text for each spot. Returns (texts, note).

    `texts` is one string per spot ("" when no line was drafted).
    `note` is "" on success, otherwise a plain-language explanation of
    why the lines are empty.
    """
    if not spots:
        return [], ""
    if provider == "none":
        return ([""] * len(spots),
                "No drafting provider selected (provider=none) — timings only. "
                "Re-scan with provider=claude or provider=openai and the "
                "matching API key set to get drafted lines.")
    if provider == "kavi":
        return ([""] * len(spots),
                "Kavi drafting is not available from the server — there is no "
                "Muse API to call. Drafting with Kavi stays the chat flow: "
                "send the file to Kavi and the lines come back there.")
    if provider == "claude":
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            return ([""] * len(spots),
                    "ANTHROPIC_API_KEY is not set — timings only. "
                    "Set it and re-scan for drafted lines.")
        return _call_provider(spots, segments, language,
                              lambda p: _call_claude(p, key))
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            return ([""] * len(spots),
                    "OPENAI_API_KEY is not set — timings only. "
                    "Set it and re-scan for drafted lines.")
        return _call_provider(spots, segments, language,
                              lambda p: _call_openai(p, key))
    raise ValueError("unknown provider: %r (use none, claude, openai, kavi)"
                     % provider)
