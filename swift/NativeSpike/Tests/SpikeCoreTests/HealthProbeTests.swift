import Foundation
import Testing
@testable import SpikeCore

@Test func acceptsPrivateHTTPSRoot() throws {
    #expect(try HealthProbe.endpoint(server: "https://pig-music.example.ts.net/").absoluteString
            == "https://pig-music.example.ts.net/api/health")
}

@Test(arguments: ["http://localhost:8765", "http://192.168.1.203:8765",
                  "https://user:password@example.ts.net", "https://example.ts.net?token=x",
                  "https://example.ts.net/api", "not a URL"])
func rejectsUnsafeOrAmbiguousURLs(server: String) {
    #expect(throws: ProbeError.invalidServerURL) { try HealthProbe.endpoint(server: server) }
}

@Test func healthRequiresSuccessfulStatusAndPayload() throws {
    let good = Data(#"{"status":"ok","storage_available":true}"#.utf8)
    #expect(try HealthProbe.decode(data: good, statusCode: 200).status == "ok")
    #expect(throws: ProbeError.unexpectedResponse(401)) {
        try HealthProbe.decode(data: good, statusCode: 401)
    }
    #expect(throws: ProbeError.unhealthy) {
        try HealthProbe.decode(data: Data(#"{"status":"failed"}"#.utf8), statusCode: 200)
    }
}
