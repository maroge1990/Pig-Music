import Foundation
import XCTest
import HTTPTypes
import OpenAPIRuntime
@testable import PigAPI
private actor MemoryTokens: DeviceTokenStore {
    var token: String? = "fixture-token"
    func read() -> String? { token }
    func save(_ value: String) {token = value}
    func clear() { token = nil }
}
final class SessionMiddlewareTests: XCTestCase {
    func test401ClearsTokenAndNeverSendsItToAnotherOrigin() async throws {
        let vault = MemoryTokens()
        let url = URL(string:"https://private.ts.net:10000")!
        let middleware = try SessionMiddleware(vault:vault,origin:url)
        _ = try await middleware.intercept(.init(method:.get,scheme:"https",authority:"private.ts.net",path:"/api/v1/me"),body:nil,baseURL:url,operationID:"fixture") {request,_,_ in
            XCTAssertEqual(request.headerFields[.authorization],"Bearer fixture-token")
            return (.init(status:.unauthorized),nil)
        }
        let token = await vault.read()
        XCTAssertNil(token)
        do {
            _ = try await middleware.intercept(.init(method:.get,scheme:"https",authority:"other",path:"/"),body:nil,baseURL:URL(string:"https://other")!,operationID:"fixture") {_,_,_ in
                XCTFail("Must not send credentials to a different origin")
                return (.init(status:.ok),nil)
            }
            XCTFail("Expected secure-origin validation")
        } catch ServerAddress.Invalid.secureURLRequired { }
    }
}
