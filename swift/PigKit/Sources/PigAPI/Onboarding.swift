import Foundation
import OpenAPIRuntime
import OpenAPIURLSession

public enum OnboardingError: Error, Equatable, Sendable {
    case inviteExpiredOrUsed
    case passwordNotAccepted
    case invalidCredentials
    case rateLimited
    case insecureServer
    case unreachable
    /// The account exists but the follow-up device sign-in failed; the person should sign in manually.
    case accountCreatedSignInFailed(username: String)
    case unexpected(status: Int)
}

private struct NoToken: DeviceTokenStore {
    func read() async throws -> String? { nil }
    func save(_ token: String) async throws {}
    func clear() async throws {}
}

/// Joins a server with an invite, or signs in to an existing account, and stores only the device token.
public struct Onboarding: Sendable {
    public static let platform = "ios"
    private let transport: any ClientTransport
    private let tokens: @Sendable (URL) -> any DeviceTokenStore

    /// `tokens` returns the store for a server origin; production uses `TokenVault(account: origin)`.
    public init(transport: any ClientTransport = URLSessionTransport(),
                tokens: @escaping @Sendable (URL) -> any DeviceTokenStore = { TokenVault(account: $0.absoluteString) }) {
        self.transport = transport
        self.tokens = tokens
    }

    public func join(_ invite: Invite, password: String, deviceName: String) async throws -> SavedServer {
        let origin = try Self.origin(invite.server)
        // Activation is anonymous: never send, or clear on 401, a token this device already holds.
        let client = try makeClient(origin, store: NoToken())
        let username: String
        do {
            let output = try await client.activate_api_v1_setup_post(.init(body: .json(.init(code: invite.code, password: password))))
            switch output {
            case .ok(let ok): username = try ok.body.json.user.username
            case .unauthorized: throw OnboardingError.inviteExpiredOrUsed
            case .unprocessableContent: throw OnboardingError.passwordNotAccepted
            case .tooManyRequests: throw OnboardingError.rateLimited
            case .undocumented(let status, _): throw OnboardingError.unexpected(status: status)
            default: throw OnboardingError.unexpected(status: Self.statusCode(output))
            }
        } catch {
            throw Self.failure(error, Self.setupFailure)
        }
        do {
            return try await signIn(server: origin, username: username, password: password, deviceName: deviceName)
        } catch {
            throw OnboardingError.accountCreatedSignInFailed(username: username)
        }
    }

    public func signIn(server: URL, username: String, password: String, deviceName: String) async throws -> SavedServer {
        let origin = try Self.origin(server)
        let store = tokens(origin)
        let client = try makeClient(origin, store: store)
        do {
            let output = try await client.device_api_v1_auth_device_post(.init(body: .json(.init(
                device_name: String(deviceName.prefix(128)).isEmpty ? "iPhone" : String(deviceName.prefix(128)),
                password: password, platform: .ios, username: username))))
            switch output {
            case .ok(let ok):
                let session = try ok.body.json
                try await store.save(session.token)
                return SavedServer(origin: origin, username: session.user.username, displayName: session.user.display_name)
            case .unauthorized: throw OnboardingError.invalidCredentials
            case .tooManyRequests: throw OnboardingError.rateLimited
            case .undocumented(let status, _): throw OnboardingError.unexpected(status: status)
            default: throw OnboardingError.unexpected(status: Self.statusCode(output))
            }
        } catch {
            throw Self.failure(error, Self.signInFailure)
        }
    }

    /// Ends the session on the server when reachable, then always forgets it on this device.
    public func signOut(_ saved: SavedServer, defaults: UserDefaults = .standard) async throws {
        let store = tokens(saved.origin)
        if let client = try? makeClient(saved.origin, store: store) {
            _ = try? await client.logout_api_v1_auth_logout_post(.init())
        }
        try await saved.forget(tokens: store, defaults: defaults)
    }

    private static func origin(_ url: URL) throws -> URL {
        do { return try ServerAddress.canonical(url.absoluteString) } catch { throw OnboardingError.insecureServer }
    }

    private func makeClient(_ origin: URL, store: any DeviceTokenStore) throws -> Client {
        Client(serverURL: origin, transport: transport, middlewares: [try SessionMiddleware(vault: store, origin: origin)])
    }

    private static func statusCode(_ output: Operations.activate_api_v1_setup_post.Output) -> Int {
        switch output {
        case .ok: 200
        case .badRequest: 400
        case .unauthorized: 401
        case .forbidden: 403
        case .notFound: 404
        case .conflict: 409
        case .gone: 410
        case .unprocessableContent: 422
        case .tooManyRequests: 429
        case .serviceUnavailable: 503
        case .undocumented(let status, _): status
        }
    }

    private static func statusCode(_ output: Operations.device_api_v1_auth_device_post.Output) -> Int {
        switch output {
        case .ok: 200
        case .badRequest: 400
        case .unauthorized: 401
        case .forbidden: 403
        case .notFound: 404
        case .conflict: 409
        case .gone: 410
        case .unprocessableContent: 422
        case .tooManyRequests: 429
        case .serviceUnavailable: 503
        case .undocumented(let status, _): status
        }
    }

    private static func setupFailure(status: Int) -> OnboardingError {
        switch status {
        case 401: .inviteExpiredOrUsed
        case 422: .passwordNotAccepted
        case 429: .rateLimited
        default: .unexpected(status: status)
        }
    }

    private static func signInFailure(status: Int) -> OnboardingError {
        switch status {
        case 401: .invalidCredentials
        case 429: .rateLimited
        default: .unexpected(status: status)
        }
    }

    /// Status-only fallback for responses the generated client could not decode (for example an error body without `code`).
    private static func failure(_ error: Error, _ map: (Int) -> OnboardingError) -> OnboardingError {
        if let error = error as? OnboardingError { return error }
        if let status = (error as? ClientError)?.response?.status.code { return map(status) }
        return .unreachable
    }
}
