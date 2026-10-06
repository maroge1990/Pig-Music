import SwiftUI
import AVFoundation

@main
struct PigMusicWatchSpikeApp: App {
    var body: some Scene {
        WindowGroup { WatchProbeView() }
    }
}

struct WatchProbeView: View {
    @State private var server = ""
    @State private var result = "Connect Bluetooth headphones for the local audio test."
    @State private var player: AVPlayer?

    var body: some View {
        ScrollView {
            VStack {
                Text("Pig Music spike").font(.headline)
                TextField("HTTPS server URL", text: $server)
                Button("Check connection") {
                    Task {
                        do {
                            _ = try await HealthProbe.check(server: server)
                            result = "Connected. Record phone and Wi-Fi conditions."
                        } catch {
                            result = "Connection failed. Record phone and Wi-Fi conditions."
                        }
                    }
                }
                Button("Play local test tone") {
                    do {
                        try AVAudioSession.sharedInstance().setCategory(
                            .playback, mode: .default, policy: .longFormAudio
                        )
                        try AVAudioSession.sharedInstance().setActive(true)
                        guard let url = Bundle.main.url(forResource: "test-tone", withExtension: "m4a") else {
                            result = "Test audio missing."
                            return
                        }
                        player = AVPlayer(url: url)
                        player?.volume = 0.15
                        player?.play()
                        result = "Local test started. Confirm audio in Bluetooth headphones."
                    } catch {
                        result = "Audio session failed. Check the headphone route."
                    }
                }
                Button("Stop audio") { player?.pause() }
                Text(result).font(.body)
            }
        }
    }
}
