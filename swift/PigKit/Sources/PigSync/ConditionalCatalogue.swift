import Foundation
import PigDomain
import PigStore

/// A server answer to a conditional request.
public enum Conditional<Value: Sendable>: Sendable {
  case fresh(Value, etag: String?)
  /// `304`: the copy saved with the sent ETag is current.
  case notModified
}

/// Catalogue answers saved on this device with their ETag. A revisit sends the
/// ETag as `If-None-Match`, and a `304` reuses the saved copy instead of
/// downloading the same body again.
public struct ConditionalCatalogue: Sendable {
  let store: LibraryStore
  public init(store: LibraryStore) { self.store = store }

  public func load<T: Codable & Sendable>(
    key: String, fetch: @Sendable (_ etag: String?) async throws -> Conditional<T>
  ) async throws -> T {
    let saved = try? await store.cached("catalogue:" + key, as: T.self)
    let etag =
      saved == nil ? nil : (try? await store.cached("catalogue-etag:" + key, as: String.self))
    switch try await fetch(etag.flatMap { $0.isEmpty ? nil : $0 }) {
    case .fresh(let value, let tag):
      await save(value, etag: tag, key: key)
      return value
    case .notModified:
      if let saved { return saved }
      // The saved copy went away meanwhile: ask again without a validator.
      guard case .fresh(let value, let tag) = try await fetch(nil) else {
        throw NativeFailure.unavailable("This page is unavailable. Try again shortly.")
      }
      await save(value, etag: tag, key: key)
      return value
    }
  }
  /// The ETag is cleared before the body changes, so a failed write never
  /// pairs a new validator with an old body.
  private func save<T: Codable & Sendable>(_ value: T, etag: String?, key: String) async {
    try? await store.cache("", key: "catalogue-etag:" + key)
    guard (try? await store.cache(value, key: "catalogue:" + key)) != nil, let etag else { return }
    try? await store.cache(etag, key: "catalogue-etag:" + key)
  }
}
