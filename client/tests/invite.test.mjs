import assert from "node:assert/strict";
import test from "node:test";
const {
  readInvite,
  captureInvite,
  pendingInvite,
  clearInvite,
  expiryText,
  qrPath,
  setupErrorMessage,
} = await import("../src/invite.ts");

test("readInvite accepts and normalises a join link", () => {
  assert.equal(readInvite("#/join?code=ABCD2345EFGH6789"), "ABCD2345EFGH6789");
  assert.equal(readInvite("#/join?code=%20abcd2345%20"), "ABCD2345");
  assert.equal(readInvite("#/join?x=1&code=abc"), "ABC");
});

test("readInvite rejects missing, empty, oversized and other routes", () => {
  assert.equal(readInvite("#/join"), null);
  assert.equal(readInvite("#/join?x=1"), null);
  assert.equal(readInvite("#/join?code="), null);
  assert.equal(readInvite("#/join?code=%20%20"), null);
  assert.equal(readInvite("#/join?code=" + "A".repeat(65)), null);
  assert.equal(readInvite("#/join?code=" + "A".repeat(64)), "A".repeat(64));
  assert.equal(readInvite("#/home?code=ABC"), null);
  assert.equal(readInvite("#/setup?code=ABC"), null);
  assert.equal(readInvite(""), null);
});

test("captureInvite keeps the code in memory and scrubs the URL", () => {
  const calls = [];
  const past = { replaceState: (...args) => calls.push(args) };
  const where = { hash: "#/join?code=abc", pathname: "/", search: "" };
  assert.equal(captureInvite(where, past), "ABC");
  assert.deepEqual(calls, [[null, "", "/#/join"]]);
  assert.equal(pendingInvite(), "ABC");
  clearInvite();
  assert.equal(pendingInvite(), null);
});

test("captureInvite leaves other routes alone and scrubs a bad join link", () => {
  const calls = [];
  const past = { replaceState: (...args) => calls.push(args) };
  assert.equal(
    captureInvite({ hash: "#/home", pathname: "/", search: "" }, past),
    null,
  );
  assert.equal(calls.length, 0);
  assert.equal(
    captureInvite({ hash: "#/join?code=", pathname: "/", search: "" }, past),
    null,
  );
  assert.equal(calls.length, 1);
  assert.equal(pendingInvite(), null);
});

test("expiryText is readable at each scale", () => {
  assert.equal(expiryText(1000 + 86400, 1000), "Expires in 24 hours");
  assert.equal(expiryText(1000 + 3600, 1000), "Expires in 1 hour");
  assert.equal(expiryText(1000 + 600, 1000), "Expires in 10 minutes");
  assert.equal(expiryText(1000 + 10, 1000), "Expires in 1 minute");
  assert.equal(expiryText(1000, 1000), "Expired");
});

test("qrPath offsets modules by the quiet zone", () => {
  const { size, d } = qrPath(
    [
      [true, false],
      [false, true],
    ],
    4,
  );
  assert.equal(size, 10);
  assert.equal(d, "M4 4h1v1h-1zM5 5h1v1h-1z");
  assert.equal(qrPath([[false]]).size, 9);
});

test("setup errors use friendly wording", () => {
  assert.match(
    setupErrorMessage("invalid_setup_code", "x"),
    /expired or was already used/,
  );
  assert.match(setupErrorMessage("rate_limited", "x"), /Too many attempts/);
  assert.equal(
    setupErrorMessage("password_not_accepted", ""),
    "Choose a longer, less common password.",
  );
  assert.equal(
    setupErrorMessage("password_not_accepted", "Too common"),
    "Too common",
  );
  assert.equal(setupErrorMessage("other", "Boom"), "Boom");
});
