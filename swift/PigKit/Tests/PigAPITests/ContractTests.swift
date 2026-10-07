import Foundation
import XCTest
import HTTPTypes
import OpenAPIRuntime
import OpenAPIURLSession
@testable import PigAPI

/// Test-only local proxy scheme; there is no production HTTP exception.
private struct FixtureHTTPS: ClientMiddleware {
    func intercept(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String,
                   next: (HTTPRequest, HTTPBody?, URL) async throws -> (HTTPResponse, HTTPBody?)) async throws -> (HTTPResponse, HTTPBody?) {
        var request = request
        request.headerFields[HTTPField.Name("X-Forwarded-Proto")!] = "https"
        request.headerFields[HTTPField.Name("X-Pig-Request")!] = "1"
        return try await next(request,body,baseURL)
    }
}
private struct FixtureBearer: ClientMiddleware {
    let token: String
    func intercept(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String,
                   next: (HTTPRequest, HTTPBody?, URL) async throws -> (HTTPResponse, HTTPBody?)) async throws -> (HTTPResponse, HTTPBody?) {
        var request = request
        request.headerFields[.authorization] = "Bearer " + token
        return try await next(request,body,baseURL)
    }
}
final class ContractTests: XCTestCase {
    func testGeneratedClientAgainstFixtureServer() async throws {
        guard let address = ProcessInfo.processInfo.environment["PIG_CONTRACT_SERVER"], let url = URL(string:address) else {
            throw XCTSkip("Set PIG_CONTRACT_SERVER to run the live fixture contract journey")
        }
        let anonymous = Client(serverURL:url,transport:URLSessionTransport(),middlewares:[FixtureHTTPS()])
        let login = try await anonymous.device_api_v1_auth_device_post(.init(body:.json(.init(device_name:"Swift contract fixture",password:"browser fixture password",platform:.ios,username:"member"))))
        guard case .ok(let success) = login else { return XCTFail("Fixture device sign-in failed") }
        let session = try success.body.json
        let client = Client(serverURL:url,transport:URLSessionTransport(),middlewares:[FixtureHTTPS(),FixtureBearer(token:session.token)])
        let me = try await client.me_api_v1_me_get(.init())
        guard case .ok(let person) = me else { return XCTFail("Fixture identity failed") }
        XCTAssertEqual(try person.body.json.username,"member")
        let page = try await client.tracks_api_v1_library_tracks_get(.init(query:.init(limit:1)))
        guard case .ok(let response) = page else { return XCTFail("Fixture library failed") }
        let first = try response.body.json
        XCTAssertEqual(first.total,2)
        XCTAssertEqual(first.items.count,1)
        XCTAssertNotNil(first.next_cursor)
        let second = try await client.tracks_api_v1_library_tracks_get(.init(query:.init(cursor:first.next_cursor,limit:1)))
        guard case .ok(let next) = second else { return XCTFail("Fixture pagination failed") }
        let secondBody = try next.body.json
        XCTAssertNotEqual(secondBody.items.first?.id,first.items.first?.id)
    }
}
