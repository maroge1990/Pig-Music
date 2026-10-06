# Pig Music native feasibility spike

Open `PigMusicNativeSpike.xcodeproj`. The iPhone scheme embeds the Watch app. The Watch scheme can also build independently.

This is an unbranded, disposable S00 probe. It checks a user-entered private HTTPS health endpoint and provides a bundled local Watch audio test. It is not the production client or a completed Sideloadly feasibility result.

See [device evidence and next checks](../../docs/native-spike.md). Shared core tests run with `swift test` from this directory. No network requests run in those tests. Build/signing output, device data and account details stay outside Git.
