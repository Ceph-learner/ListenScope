# Music & Audio Glossary

| Term | Definition |
|---|---|
| **Chroma** | A 12-element pitch-class energy distribution (`C, C#, D, ..., B`) folded across octaves, used for chord and key estimation. |
| **Key** | The tonal center and scale of a piece (e.g., `C major`, `A minor`), estimated by correlating Chroma against key profiles (such as Shaath or Temperley 1999). |
| **Chord Degree (Roman Numeral)** | Harmonic function relative to the detected key (`I`, `IV`, `V`, `vi`, etc.), useful for Capo transposition and ear training. |
| **Inversion / Slash Chord** | A chord whose lowest (bass) note differs from its root, written as `C/E` (C major triad with E in the bass). |
| **BPM (Beats Per Minute)** | Tempo measured in beats per minute. |
| **Half-time / Double-time** | Octave tempo ambiguity (e.g., `60 BPM` vs `120 BPM` vs `240 BPM`), disambiguated using a log-normal tempo prior. |
| **Cent** | Logarithmic pitch-deviation unit where 1 semitone = 100 cents; `-50 ~ +50 cents` shows tuning offset from equal temperament. |
| **RTF (Real-Time Factor)** | Processing time divided by audio duration; `RTF < 1.0` means faster-than-real-time processing. |
| **Stem Separation** | Splitting a stereo mix into isolated tracks (2-Stem: Vocals/Instrumental; 4-Stem: Vocals/Drums/Bass/Other) for focused transcription and mixing. |
