import Foundation

public enum ServerAddress {
  public enum Invalid: Error, LocalizedError {
    case secureURLRequired
    public var errorDescription: String? {
      "Enter your server's HTTPS address, without a password, query or page path."
    }
  }
  /// A server origin, never a URL containing embedded credentials or tokens.
  public static func validate(_ value: String) throws -> URL {
    guard let url = URL(string: value.trimmingCharacters(in: .whitespacesAndNewlines)),
      url.scheme == "https", let host = url.host, !host.isEmpty,
      url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
      url.path.isEmpty || url.path == "/"
    else {
      throw Invalid.secureURLRequired
    }
    guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
      throw Invalid.secureURLRequired
    }
    components.host = host.lowercased()
    components.path = ""
    if components.port == 443 { components.port = nil }
    guard let origin = components.url else { throw Invalid.secureURLRequired }
    return origin
  }
}
