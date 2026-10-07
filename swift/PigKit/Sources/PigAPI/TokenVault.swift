import Foundation
import Security

public protocol DeviceTokenStore: Sendable {
    func read() async throws -> String?
    func save(_ token: String) async throws
    func clear() async throws
}

/// Passwords never enter this vault. It stores only the opaque device token.
public actor TokenVault: DeviceTokenStore {
    public enum Failure: Error { case keychain(OSStatus) }
    private let service: String
    private let account: String
    public init(service: String = "au.com.pig.music.device-token", account: String) {
        self.service = service
        self.account = account
    }
    private var query: [String: Any] {
        [kSecClass as String:kSecClassGenericPassword, kSecAttrService as String:service, kSecAttrAccount as String:account]
    }
    public func read() throws -> String? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &item)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = item as? Data else { throw Failure.keychain(status) }
        return String(data:data,encoding:.utf8)
    }
    public func save(_ token: String) throws {
        let values: [String:Any] = [kSecValueData as String:Data(token.utf8), kSecAttrAccessible as String:kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        let status = SecItemUpdate(query as CFDictionary, values as CFDictionary)
        if status == errSecItemNotFound {
            let insert = SecItemAdd(query.merging(values){_,new in new} as CFDictionary,nil)
            guard insert == errSecSuccess else { throw Failure.keychain(insert) }
        } else if status != errSecSuccess { throw Failure.keychain(status) }
    }
    public func clear() throws {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw Failure.keychain(status) }
    }
}
