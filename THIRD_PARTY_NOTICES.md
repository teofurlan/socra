# Third-party notices

## Piper

The server speaks through [Piper](https://github.com/OHF-Voice/piper1-gpl)
(`piper-tts` package), licensed under GPL-3.0-or-later. It is installed as a
dependency, not bundled. Anyone who bundles it into a distribution of Socra must
meet the GPL's terms for that distribution.

The voice `en_US-libritts_r-medium` (speaker 0) comes from
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices), trained on
[LibriTTS-R](http://www.openslr.org/141/) (Koizumi et al., Google), licensed under
CC BY 4.0. According to its model card it was fine-tuned from the `en_US-lessac-medium`
voice, whose Blizzard 2013 dataset has its own
[licence](https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html);
check both before commercial use. It downloads on first use.

## Whisper

The server transcribes through
[faster-whisper](https://github.com/SYSTRAN/faster-whisper), licensed under MIT and
installed as a dependency. Its default model, `large-v3-turbo`, downloads on first
use from `mobiuslabsgmbh/faster-whisper-large-v3-turbo` on Hugging Face, where the
model is tagged MIT.

## Built page

`pnpm -C web build` copies or bundles these into `web/dist`, which is not part of
this repository. Keep their notices if you distribute a built page.

- [Silero VAD](https://github.com/snakers4/silero-vad) models, through
  [`@ricky0123/vad-web`](https://github.com/ricky0123/vad) (ISC). MIT License,
  Copyright (c) 2020-present Silero Team.
- [ONNX Runtime Web](https://github.com/microsoft/onnxruntime) (`onnxruntime-web`),
  MIT License.
- [Geist](https://github.com/vercel/geist-font) and
  [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) fonts, through
  `@fontsource-variable`, SIL Open Font License 1.1.
