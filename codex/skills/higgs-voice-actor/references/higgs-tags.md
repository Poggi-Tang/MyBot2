# Higgs TTS 3 Tag Reference

Source: https://docs.boson.ai/models/higgs-tts/tags

Place emotion, style, speed, pitch, and expressiveness tags at the beginning of each synthesized segment. Place pause tags at the intended break. Place SFX immediately before its matching written vocal cue.

## Allowed values

- Emotion: `elation`, `amusement`, `enthusiasm`, `determination`, `pride`, `contentment`, `affection`, `relief`, `contemplation`, `confusion`, `surprise`, `awe`, `longing`, `arousal`, `anger`, `fear`, `disgust`, `bitterness`, `sadness`, `shame`, `helplessness`.
- Style: `singing`, `shouting`, `whispering`.
- Speed: `speed_very_slow`, `speed_slow`, `speed_fast`, `speed_very_fast`.
- Pitch: `pitch_low`, `pitch_high`.
- Expressiveness: `expressive_low`, `expressive_high`.
- Pause: `pause`, `long_pause`.
- SFX: `cough`, `laughter`, `crying`, `screaming`, `burping`, `humming`, `sigh`, `sniff`, `sneeze`.

## Syntax

```text
<|emotion:affection|><|prosody:expressive_high|>我一直都在。
<|prosody:speed_slow|>慢慢说，<|prosody:pause|>不用着急。
<|sfx:laughter|>哈哈，原来是这样。
```

Do not send free-form prose inside a tag. Do not add vocal cues that were absent from the reply. For a pronounced emotional turn, synthesize the next segment separately with its own leading tags and merge the audio afterward.
