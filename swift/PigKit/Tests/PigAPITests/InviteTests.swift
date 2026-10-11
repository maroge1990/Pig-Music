import XCTest
@testable import PigAPI

final class InviteTests: XCTestCase {
    private let code = "K7M2ABCDEFGHJKLM"

    func testValidLinks() throws {
        let cases: [(String, String, String)] = [
            ("https://music.markrogers.au/#/join?code=K7M2ABCDEFGHJKLM", "https://music.markrogers.au", code),
            ("https://passyflix.tail6d1471.ts.net:10000/#/join?code=K7M2ABCDEFGHJKLM", "https://passyflix.tail6d1471.ts.net:10000", code),
            ("https://music.markrogers.au/#/join?code=K7M2ABCDEFGHJKLM", "https://music.markrogers.au", code),
            ("https://music.markrogers.au#/join?code=K7M2ABCDEFGHJKLM", "https://music.markrogers.au", code),
            ("  https://music.markrogers.au/#/join?code=k7m2abcdefghjklm\n", "https://music.markrogers.au", code),
            ("https://Music.MarkRogers.au/#/join?utm=x&code=K7M2ABCDEFGHJKLM&other=1", "https://music.markrogers.au", code),
            ("HTTPS://music.markrogers.au/#/join?code=23456789", "https://music.markrogers.au", "23456789")
        ]
        for (text, server, expected) in cases {
            let invite = try Invite.parse(text)
            XCTAssertEqual(invite.server.absoluteString, server, text)
            XCTAssertEqual(invite.code, expected, text)
        }
    }

    func testRejections() {
        let cases: [(String, Invite.Failure)] = [
            ("http://music.markrogers.au/#/join?code=K7M2ABCDEFGHJKLM", .insecureServer),
            ("https://user:pw@music.markrogers.au/#/join?code=K7M2ABCDEFGHJKLM", .notAnInvite),
            ("https://user@music.markrogers.au/#/join?code=K7M2ABCDEFGHJKLM", .notAnInvite),
            ("https://music.markrogers.au/app/#/join?code=K7M2ABCDEFGHJKLM", .notAnInvite),
            ("https://music.markrogers.au/?x=1#/join?code=K7M2ABCDEFGHJKLM", .notAnInvite),
            ("https://music.markrogers.au/#/join", .notAnInvite),
            ("https://music.markrogers.au/#/join?other=1", .notAnInvite),
            ("https://music.markrogers.au/#/join?code=", .invalidCode),
            ("https://music.markrogers.au/#/join?code=K7M2ABCD0OIL1234", .invalidCode),
            ("https://music.markrogers.au/#/join?code=K7M2ABC", .invalidCode),
            ("https://music.markrogers.au/#/join?code=" + String(repeating: "A", count: 65), .invalidCode),
            ("https://music.markrogers.au/#/login?code=K7M2ABCDEFGHJKLM", .notAnInvite),
            ("https://music.markrogers.au/", .notAnInvite),
            ("hello world", .notAnInvite),
            ("", .notAnInvite),
            ("ftp://music.markrogers.au/#/join?code=K7M2ABCDEFGHJKLM", .notAnInvite),
            ("see https://music.markrogers.au/#/join?code=K7M2ABCDEFGHJKLM please", .notAnInvite)
        ]
        for (text, failure) in cases {
            XCTAssertThrowsError(try Invite.parse(text), text) { XCTAssertEqual($0 as? Invite.Failure, failure, text) }
        }
    }
}
