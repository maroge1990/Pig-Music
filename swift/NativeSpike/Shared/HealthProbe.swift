import Foundation

public enum ProbeError: Error, Equatable, Sendable {
    case invalidServerURL
    case unexpectedResponse(Int)
    case unhealthy
}

public struct HealthPayload: Decodable, Sendable {
    public let status: String
}

public enum HealthProbe {
    public static func endpoint(server: String) throws -> URL {
        guard let parts = URLComponents(string: server),
              parts.scheme?.lowercased() == "https",
              let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil,
              parts.query == nil, parts.fragment == nil,
              parts.path.isEmpty || parts.path == "/",
              let base = parts.url
        else { throw ProbeError.invalidServerURL }
        return base.appending(path: "api/health")
    }

    public static func decode(data: Data, statusCode: Int) throws -> HealthPayload {
        guard statusCode == 200 else { throw ProbeError.unexpectedResponse(statusCode) }
        let health = try JSONDecoder().decode(HealthPayload.self, from: data)
        guard health.status == "ok" else { throw ProbeError.unhealthy }
        return health
    }

    public static func check(server: String) async throws -> HealthPayload {
        var request = URLRequest(url: try endpoint(server: server))
        request.timeoutInterval = 15
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw ProbeError.unexpectedResponse(0)
        }
        return try decode(data: data, statusCode: http.statusCode)
    }
}
