# Native audio: bounded decoding and engine capture

11 October 2026. N01 software prototype, not production live playback acceptance. The connected app still uses AVPlayer; no claim is made for progressive network decoding, realtime output, locked-device transitions or household media.

## Implemented

`PCMFileDecoder` reads local files through AVAudioFile and AVAudioConverter in bounded blocks. Mono/stereo inputs normalize to one configured stereo PCM clock. Conversion drains once, without replaying input buffers, and output is limited to the decoded file's normalized frame count. Mutable AVAudioPCMBuffer stays inside its owner; immutable PCMBlock values cross the decoder actor boundary.

`PCMTransitionStream` holds a circular outgoing tail and incoming head, then emits ordinary blocks or a complementary linear crossfade. Storage depends on configured fade/block sizes, not song length. At the default 48 kHz clock, three-second overlap and 2,048-frame blocks, ring storage is about 2.2 MiB, plus bounded decoder, scratch and output buffers. Supported prototype clocks are 44.1/48/96 kHz and overlap is limited to 12 seconds.

`BoundedAudioEngineProbe` feeds the blocks through AVAudioPlayerNode and captures actual AVAudioEngine manual-rendering output. Scheduled PCM is capped at 8,192 frames with the default block size. The nonblocking callback-form scheduling method is intentional: awaiting completion before manually rendering would prevent the queued audio from progressing. Output paths cannot alias either input through normalized paths/symlinks.

Album-order policy uses stable album identity and sequential track/disc numbers; repeats and shuffled numbering are not treated as sequential albums. This is an engineering policy helper, not a delivered production crossfade preference. The proposed on/off UX and listening-tested duration remain open.

The conversion and timeline choices follow Apple's [sample-rate conversion guidance](https://developer.apple.com/documentation/technotes/tn3136-avaudioconverter-performing-sample-rate-conversions) and [AVAudioPlayerNode scheduling/timeline documentation](https://developer.apple.com/documentation/avfaudio/avaudioplayernode). Core behavior is verified by output capture rather than inferred from those APIs.

## Evidence

At this prototype milestone, the native suite had **27 passing tests**, with real-fixture journeys enabled: 5 XCTest and 22 Swift Testing cases. Six new cases cover:

- Exact 88,200-sample continuity for a unique stereo ramp split at a 44.1 kHz album boundary. Maximum permitted output error is below 0.0000001; the test examines every sample, so inserted/dropped/duplicated samples are detectable.
- A 48 kHz direct join and crossfade envelope across multiple scheduled blocks, with independently checked channel values and frame totals.
- 44.1 kHz mono → 48 kHz stereo followed by 96 kHz stereo → 48 kHz, with exact total duration and channel mapping.
- A 60-second track plus a four-second track with a three-second fade: 2,928,000 output frames, 144,000 overlap frames, held frames bounded by 290,048. This is an allocation regression, not a phone battery/throughput benchmark.
- Cancellation, refusal of HTTP input and preservation of source bytes when output aliases input.
- Album/disc-order decisions versus repeats, changed releases and shuffled numbering.

Unsigned iPhone/iPad compilation passes. The SDK suggests the async scheduling overload; the explicit callback form remains necessary for this manual renderer. No app UI/player substitution was made by this slice.

The opt-in `scripts/probe_native_audio.py` generated one-second stereo tones using local FFmpeg 9.0.2 and ran actual engine captures on **macOS 27.0.1 arm64**. WAV, AIFF, AAC/M4A, ALAC/M4A, MP3, FLAC and Opus/Ogg rendered 96,000 frames for two joined files and 84,000 for a 0.25-second overlap at 48 kHz. This is evidence for these generated files on this OS, not all encoders or older iOS versions.

Vorbis/Ogg also rendered. This Mac's FFmpeg has no libvorbis encoder, so the fixture uses its explicitly recorded experimental native Vorbis encoder. That file contains **44,160 source frames** according to ffprobe, rather than the generated WAV's 44,100; each file normalizes to 48,065 frames. Joined output is 96,130; fade output is 84,130. The discrepancy is already present in encoded input duration. Do not remove those frames blindly or present this as a proven Apple decoder defect. Correctly trimmed production-encoder fixtures remain a format acceptance gate.

Full output metadata, encoder arguments, binary hash and observations live in ignored `swift/build/AudioMatrix/report.json`; source/output media are synthetic. No provider requests, household files, third-party decoder dependency, server implementation changes or deployments are involved.

## Architecture direction and remaining gates

The preferred candidate for saved/downloaded transitions is block-based native PCM scheduling on AVAudioEngine, rather than assuming that two AVPlayers or AVQueuePlayer provide sample continuity. This prototype passes the software sample-scheduling gate. Final adoption still needs realtime deadline/underrun tests, device route/audio-session handling, seek/skip/queue cancellation, encoder trimming across supported fixtures and network source readiness.

Preserve an album's native sample clock where feasible. The exact continuity test covers an unchanged 44.1 kHz clock; mixed-rate tests prove mapping/duration, not equivalence to resampling an entire continuous album through one uninterrupted filter. Converter history at resampled album boundaries needs its own capture test before a guarantee is published.

The next player package must provide bounded source readiness for signed saved media, then a realtime queue scheduler using these blocks and an explicit fallback when the next source is unavailable. It must handle stale signed URLs, source revisions, revocation, cancellation and transient media separately from offline downloads. Experimental provider URLs must not receive device credentials or acquire music implicitly. Integration with app controls/system metadata comes after those lifecycle tests.

Run the bounded tool with `PigAudioProbe --bounded first second output.wav overlap-seconds`. Use `python scripts/probe_native_audio.py` from the repository root after building the executable, with FFmpeg/ffprobe installed. The tool produces files only; it does not play sound through the Mac's speakers.
