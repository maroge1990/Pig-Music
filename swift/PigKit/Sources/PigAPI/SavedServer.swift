import Foundation

/// Non-secret record of the server this device is signed in to. The device token lives in `TokenVault`.
public struct SavedServer: Codable, Equatable, Sendable {
    public static let defaultsKey = "au.com.pig.music.saved-server"

    public let origin: URL
    public let username: String
    public let displayName: String

    public init(origin: URL, username: String, displayName: String) {
        self.origin = origin
        self.username = username
        self.displayName = displayName
    }

    /// Keychain account for this server's device token.
    public var tokenAccount: String { origin.absoluteString }
    public var host: String { origin.host ?? origin.absoluteString }

    public func tokenVault() -> TokenVault { TokenVault(account: tokenAccount) }

    public static func load(from defaults: UserDefaults = .standard) -> SavedServer? {
        guard let data = defaults.data(forKey: defaultsKey) else { return nil }
        return try? JSONDecoder().decode(SavedServer.self, from: data)
    }

    public func save(to defaults: UserDefaults = .standard) throws {
        defaults.set(try JSONEncoder().encode(self), forKey: Self.defaultsKey)
    }

    /// Clears the device token and the saved record.
    public func forget(tokens: any DeviceTokenStore, defaults: UserDefaults = .standard) async throws {
        try await tokens.clear()
        defaults.removeObject(forKey: Self.defaultsKey)
    }

    public func forget(defaults: UserDefaults = .standard) async throws {
        try await forget(tokens: tokenVault(), defaults: defaults)
    }
}
