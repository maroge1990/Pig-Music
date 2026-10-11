#if os(iOS)
  import CryptoKit
  import Foundation
  import Security
  import PigDomain

  /// Resume data can contain the original Authorization header. Only encrypted bytes reach disk.
  struct BackgroundResumeVault {
    let account: String
    private func key() throws -> SymmetricKey {
      let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "PigMusicBackgroundResume", kSecAttrAccount as String: account,
      ]
      var found: CFTypeRef?
      let status = SecItemCopyMatching(
        (query.merging([
          kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne,
        ]) { _, new in new }) as CFDictionary, &found)
      if status == errSecSuccess, let data = found as? Data, data.count == 32 {
        return SymmetricKey(data: data)
      }
      guard status == errSecItemNotFound else { throw OfflineFailure.unsafeResponse }
      let value = SymmetricKey(size: .bits256)
      let data = value.withUnsafeBytes { Data($0) }
      let added = SecItemAdd(
        query.merging([
          kSecValueData as String: data,
          kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]) { _, new in new } as CFDictionary, nil)
      guard added == errSecSuccess else { throw OfflineFailure.unsafeResponse }
      return value
    }
    func seal(_ data: Data, at url: URL) throws {
      guard data.count <= 2 * 1024 * 1024 else { throw OfflineFailure.unsafeResponse }
      guard
        let bytes = try AES.GCM.seal(data, using: key(), authenticating: Data(account.utf8))
          .combined
      else { throw OfflineFailure.unsafeResponse }
      try bytes.write(
        to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }
    func open(_ url: URL) -> Data? {
      guard let data = try? Data(contentsOf: url), data.count <= 2 * 1024 * 1024 + 100 else {
        return nil
      }
      return try? AES.GCM.open(
        AES.GCM.SealedBox(combined: data), using: key(), authenticating: Data(account.utf8))
    }
    func clear() {
      SecItemDelete(
        [
          kSecClass as String: kSecClassGenericPassword,
          kSecAttrService as String: "PigMusicBackgroundResume", kSecAttrAccount as String: account,
        ] as CFDictionary)
    }
  }
#endif
