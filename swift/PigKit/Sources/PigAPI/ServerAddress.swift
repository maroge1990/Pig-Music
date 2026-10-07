import Foundation

public enum ServerAddress {
    public enum Invalid: Error { case secureURLRequired }
    /// A server origin, never a URL containing embedded credentials or tokens.
    public static func validate(_ value: String) throws -> URL {
        guard let url = URL(string: value.trimmingCharacters(in: .whitespacesAndNewlines)),
              url.scheme == "https", let host = url.host, !host.isEmpty,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              url.path.isEmpty || url.path == "/" else {
            throw Invalid.secureURLRequired
        }
        return url
    }
}
