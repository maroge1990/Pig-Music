import Foundation

/// A parsed `https://<origin>/#/join?code=<CODE>` invitation link.
public struct Invite: Equatable, Sendable {
    public enum Failure: Error, Equatable, Sendable {
        case notAnInvite
        case insecureServer
        case invalidCode
    }

    public static let codeAlphabet = Set("23456789ABCDEFGHJKLMNPQRSTUVWXYZ")
    public static let codeLengths = 8...64

    public let server: URL
    public let code: String

    public init(server: URL, code: String) {
        self.server = server
        self.code = code
    }

    public static func parse(_ text: String) throws -> Invite {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let components = URLComponents(string: trimmed), let scheme = components.scheme?.lowercased() else {
            throw Failure.notAnInvite
        }
        guard scheme == "https" else {
            if scheme == "http" { throw Failure.insecureServer }
            throw Failure.notAnInvite
        }
        guard let host = components.host, !host.isEmpty,
              components.user == nil, components.password == nil,
              components.query == nil,
              components.path.isEmpty || components.path == "/",
              let fragment = components.fragment else {
            throw Failure.notAnInvite
        }
        let prefix = "/join?"
        guard fragment.hasPrefix(prefix) else { throw Failure.notAnInvite }
        let pairs = fragment.dropFirst(prefix.count).split(separator: "&", omittingEmptySubsequences: true)
        var rawCode: String?
        for pair in pairs {
            let parts = pair.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            if parts.count == 2, parts[0] == "code" {
                rawCode = String(parts[1])
                break
            }
        }
        guard let rawCode else { throw Failure.notAnInvite }
        let code = rawCode.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard codeLengths.contains(code.count), code.allSatisfy({ codeAlphabet.contains($0) }) else {
            throw Failure.invalidCode
        }
        var origin = URLComponents()
        origin.scheme = "https"
        origin.host = host.lowercased()
        origin.port = components.port
        guard let originString = origin.string,
              let server = try? ServerAddress.canonical(originString) else { throw Failure.notAnInvite }
        return Invite(server: server, code: code)
    }
}

extension ServerAddress {
    /// Validated origin without a trailing slash, so it is stable as a Keychain account and settings key.
    public static func canonical(_ value: String) throws -> URL {
        let url = try validate(value)
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { throw Invalid.secureURLRequired }
        components.path = ""
        components.host = components.host?.lowercased()
        guard let result = components.url else { throw Invalid.secureURLRequired }
        return result
    }
}
