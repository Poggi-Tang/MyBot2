---
name: higgs-voice-actor
description: Direct expressive Higgs TTS 3 performances without changing the spoken reply. Use when preparing MyBot voice replies, narration, dialogue, or other speech that needs emotional beats, pauses, emphasis, pitch, pacing, whispering, shouting, or vocal sound effects encoded as Higgs inline tags.
---

# Higgs Voice Actor

Preserve the reply verbatim and add performance direction around it.

1. Read [references/higgs-tags.md](references/higgs-tags.md).
2. Infer an emotional arc from the user message and reply.
3. Split the reply at natural semantic boundaries into one to four segments.
4. Keep the concatenated segment text identical to the reply, ignoring whitespace only.
5. Assign only documented Higgs tags. Use at most one tag from each category per segment.
6. Add an SFX tag only when the original text already contains the matching vocal cue.
7. Prefer contrast, pauses, and restrained intensity over stacking many tags.

Return strict JSON:

```json
{"segments":[{"text":"原文片段","emotion":"affection","style":"","speed":"normal","pitch":"normal","expressiveness":"high","pause_after":"none","sfx":""}]}
```

Reject output that rewrites text, invents a tag, contains more than four segments, or omits any original content. Fall back to one conservative segment when validation fails.
