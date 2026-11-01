# Third-party notices

## ElevenLabs UI

`web/src/components/ui/orb.tsx` and `web/src/assets/perlin-noise.png` come from
[ElevenLabs UI](https://github.com/elevenlabs/ui), used under the MIT License.

Copyright (c) 2025 Eleven Labs Inc.

## Piper

The server speaks through [Piper](https://github.com/OHF-Voice/piper1-gpl)
(`piper-tts` package), licensed under GPL-3.0-or-later. It is installed as a
dependency, not bundled.

The voice `en_US-libritts_r-medium` (speaker 0) comes from
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices), trained on
[LibriTTS-R](http://www.openslr.org/141/) (Koizumi et al., Google), licensed under
CC BY 4.0. According to its model card it was fine-tuned from the `en_US-lessac-medium`
voice, whose Blizzard 2013 dataset has its own
[licence](https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html);
check both before commercial use. It downloads on first use.
