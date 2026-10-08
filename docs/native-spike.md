# S00 native feasibility: preparation and device evidence

6 October 2026. **Preparation implemented; actual-device feasibility remains unverified.** This is a disposable connectivity/audio spike, not the P01 production client. Branding was approved on 7 October; the disposable spike retains system presentation.

## Owner-provided inventory and signing

| Person / device | Inventory | OS |
| --- | --- | --- |
| First iPhone | iPhone 16 Pro Max | Owner reports latest; exact version/build to record on device |
| Second iPhone | iPhone 12 | Owner reports latest; exact version/build to record on device |
| First Watch | Apple Watch Ultra 3 | Owner reports latest; exact version/build to record on device |
| Second Watch | Apple Watch Series 7 | Owner reports latest; exact version/build to record on device |

The owner chose a **free Apple account with Sideloadly**. Paid membership is not assumed. S00 must establish app-ID counts, actual installed-app limits, expiry/refresh behaviour and Watch installation before W01 proceeds. iOS 18 / watchOS 11 are provisional minimum build settings; confirm against the recorded device versions. Do not raise minimums just because this Mac has newer SDKs.

## What is prepared

`swift/NativeSpike/PigMusicNativeSpike.xcodeproj` has an iPhone app with an embedded single-target Watch app and shared HTTPS health-probe code. It uses Swift 6 strict concurrency and standard system presentation. There are no product icons, generated brand tokens, App Groups, shared-Keychain capabilities, widgets or production sign-in code.

- iPhone: enter a private HTTPS server URL, then explicitly check `/api/health`.
- Watch: perform the same foreground check and explicitly play/stop a bundled three-second AAC test tone via a long-form audio session. Connect Bluetooth headphones first. No server audio is fetched.
- Shared probe rejects HTTP, embedded credentials, query/fragment tokens and non-root server URLs. No private server URL, token, password or Apple account is stored in the project.
- Spike bundle IDs are `au.com.pig.music.spike` and `au.com.pig.music.spike.watchkitapp`; they are temporary, not final production IDs.
- `Package.swift` exercises the shared probe URL/error handling independently with Swift Testing.

Local toolchain: Xcode 27.0 (27A266a), Swift 6.4. The global selection is CommandLineTools; commands use `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` without changing it. Shared core tests pass (3 tests, including 6 URL validation cases). The unsigned iPhone simulator build, including its embedded Watch app, passes. These results prove compilation only, not Sideloadly installation, physical playback or networking.

## Build and install preparation

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  swift test --package-path swift/NativeSpike

DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  xcodebuild -project swift/NativeSpike/PigMusicNativeSpike.xcodeproj \
  -scheme PigMusicNativeSpike -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath swift/build/DerivedData CODE_SIGNING_ALLOWED=NO build
```

Open the project in Xcode for actual-device signing/archive work. Use the selected free account only in Xcode/Sideloadly's secure UI, and do not commit team/account credentials. Produce the install package with Sideloadly's required procedure and record whether it installs and refreshes both targets. Simulator output is not an installable device IPA. Do not overwrite production bundle IDs during spike testing.

## Unsigned physical-device package, 7 October 2026

A generic iOS device archive completed successfully with signing disabled. The packaged IPA includes iPhone arm64 and embedded Watch arm64/arm64_32 executables with provisional minimum OS 18/11 and the matching companion ID. ZIP integrity passed. This local test artifact requires signing before installation; it proves neither free-account distribution nor Watch installation.

Reproduce the archive with the project/scheme above, `-destination 'generic/platform=iOS' -archivePath swift/build/PigMusicNativeSpike.xcarchive CODE_SIGNING_ALLOWED=NO archive`. Package the archived iPhone app under `Payload/` using `ditto`; keep artifacts outside Git. The prepared local output is `outputs/native-spike-20261007/PigMusicNativeSpike-unsigned.ipa` in the project workspace.

## Outstanding evidence

Record each result as passed, failed or not run, with device/OS/build and conditions:

1. Sideloadly install on each iPhone; whether the embedded Watch app installs automatically or via the Watch app's Install control.
2. App-ID/installed-app count and a refresh cycle on the free account. Confirm data and Watch app remain usable. Leave widgets/App Groups out until proven necessary and supported.
3. iPhone HTTPS health on home LAN and cellular with Tailscale. The private HTTPS endpoint is now https://passyflix.tail6d1471.ts.net:10000/. Connect the iPhone to Tailscale before testing.
4. Watch health with the phone nearby; with Bluetooth disabled; and with the phone off while the Watch uses home Wi-Fi. Do not assume Watch traffic traverses the phone's VPN.
5. Watch local AAC playback to Bluetooth headphones without the phone nearby, including interruption/resume behaviour.
6. Add a background URLSession transfer probe and paired-phone file transfer once the basic installation/networking path is established. Those probes are not implemented yet.
7. Only add App Group/Keychain-sharing capability tests if needed, and verify whether Sideloadly re-signing preserves them.

If Sideloadly cannot install/refresh the Watch app, record that failure before evaluating direct Xcode installation or a paid-account alternative with the owner. No Watch production work depends on an unproven distribution path.

The first production client milestone remains secure sign-in plus synced library browsing after the account/API foundations. This spike never signs in against the current unauthenticated API.

## Device status, 7 October 2026

The owner reports that the prepared IPA has not yet been installed. Installation, refresh, phone networking and Watch headphones playback remain **not run**. Production Watch implementation remains gated on this evidence.

## Joining a server (invite flow)

The iOS spike app now links `PigKit` (`PigAPI`) and can sign in two ways:

- **Join with an invite**: scan the owner's QR code (VisionKit) or paste the link
  `https://<server>/#/join?code=<CODE>`. `Invite.parse` accepts only a bare HTTPS origin plus the
  `/join` fragment. The app asks for a password (12+ characters), calls `POST /api/v1/setup` to
  activate the account, then `POST /api/v1/auth/device` with the returned username and the same
  password. Only the device token is stored (Keychain, account = server origin); the password is
  never persisted. If activation succeeds but sign-in fails the app says so, because the invite is
  already used.
- **Add my server**: server URL, username and password go straight to `POST /api/v1/auth/device`.

The server origin, username and display name are kept in `UserDefaults` (`SavedServer`). "Sign out
of this server" clears the token and that record.

Not verified on a device yet: the camera permission prompt and QR scanning (the simulator has no
camera), Keychain behaviour across reinstall, and the join against a real server over Tailscale or
a public domain. Unit tests cover link parsing, request order and bodies, error mapping and
persistence with a fake transport only.
