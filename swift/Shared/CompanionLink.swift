import Foundation
import Observation
import PigCompanion
import WatchConnectivity

/// WatchConnectivity owns delivery scheduling. File ownership is taken synchronously in its delegate.
@MainActor @Observable final class CompanionLink: NSObject, WCSessionDelegate {
  private nonisolated let deliveries = DeliveryCounter()
  var reachable = false
  var available = false
  var error: String?
  @ObservationIgnored var onContext: (@MainActor (CompanionContext) async -> Void)?
  @ObservationIgnored var onFile: (@MainActor (URL, Data) async -> Void)?
  @ObservationIgnored var onMessage: (@MainActor (Data) async -> Void)?
  @ObservationIgnored var onRequest: (@MainActor (Data) async -> Data)?
  @ObservationIgnored var onActivated: (@MainActor () async -> Void)?
  @ObservationIgnored nonisolated let inbox: URL
  @ObservationIgnored private let session: WCSession?
  init(inbox: URL) throws {
    self.inbox = inbox
    try FileManager.default.createDirectory(at: inbox, withIntermediateDirectories: true)
    session = WCSession.isSupported() ? .default : nil
    super.init()
    session?.delegate = self
    session?.activate()
  }
  var supported: Bool { session != nil }
  func publish(_ context: CompanionContext) throws {
    guard let session, session.activationState == .activated else { return }
    try session.updateApplicationContext(["context": try JSONEncoder().encode(context)])
  }
  func publishReceipt(_ receipt: CompanionAcknowledgement) throws {
    guard let session, session.activationState == .activated else { return }
    try session.updateApplicationContext(["receipt": try JSONEncoder().encode(receipt)])
  }
  func transfer(_ file: URL, metadata: Data) {
    guard let session, session.activationState == .activated else { return }
    session.transferFile(file, metadata: ["envelope": metadata])
  }
  var outstanding: [Data] {
    session?.outstandingFileTransfers.compactMap { $0.file.metadata?["envelope"] as? Data } ?? []
  }
  func cancelTransfers() {
    for transfer in session?.outstandingFileTransfers ?? [] { transfer.cancel() }
  }
  func message(_ data: Data) {
    guard let session, session.activationState == .activated else { return }
    guard
      !session.outstandingUserInfoTransfers.contains(where: {
        ($0.userInfo["payload"] as? Data) == data
      })
    else { return }
    session.transferUserInfo(["payload": data])
  }
  func request(_ data: Data) async throws -> Data {
    guard let session, session.isReachable else { throw CompanionFailure.stale }
    return try await withCheckedThrowingContinuation { continuation in
      session.sendMessageData(
        data, replyHandler: { continuation.resume(returning: $0) },
        errorHandler: { continuation.resume(throwing: $0) })
    }
  }
  func finishBackgroundDelivery() async {
    let deadline = ContinuousClock.now + .seconds(20)
    while !Task.isCancelled, ContinuousClock.now < deadline {
      if session?.activationState == .activated, session?.hasContentPending != true {
        await recoverInbox()
        // Give already dispatched delegate callbacks a chance to finish their actor work.
        await Task.yield()
        if session?.hasContentPending != true, deliveries.isEmpty { return }
      }
      try? await Task.sleep(for: .milliseconds(100))
    }
  }
  func recoverInbox() async {
    guard let onFile else { return }
    for envelope
      in (try? FileManager.default.contentsOfDirectory(at: inbox, includingPropertiesForKeys: nil))
      ?? [] where envelope.pathExtension == "json"
    {
      guard let metadata = try? Data(contentsOf: envelope) else { continue }
      let file = envelope.deletingPathExtension().appendingPathExtension("transfer")
      if FileManager.default.fileExists(atPath: file.path) { await onFile(file, metadata) }
    }
  }
  nonisolated func session(
    _ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState,
    error: (any Error)?
  ) {
    let text = error?.localizedDescription
    let reachable = session.isReachable
    #if os(iOS)
      let available = session.isPaired && session.isWatchAppInstalled
    #else
      let available = activationState == .activated
    #endif
    let context = session.receivedApplicationContext["context"] as? Data
    let receipt = session.receivedApplicationContext["receipt"] as? Data
    deliveries.begin()
    Task { @MainActor in
      defer { self.deliveries.end() }
      self.reachable = reachable
      self.available = available
      self.error = text
      if let context, let value = try? JSONDecoder().decode(CompanionContext.self, from: context) {
        await self.onContext?(value)
      }
      if let receipt { await self.onMessage?(receipt) }
      await self.onActivated?()
      await self.recoverInbox()
    }
  }
  nonisolated func sessionReachabilityDidChange(_ session: WCSession) {
    let reachable = session.isReachable
    deliveries.begin()
    Task { @MainActor in
      defer { self.deliveries.end() }
      self.reachable = reachable
      if reachable { await self.onActivated?() }
    }
  }
  nonisolated func session(
    _ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]
  ) {
    let data = applicationContext["context"] as? Data
    let receipt = applicationContext["receipt"] as? Data
    deliveries.begin()
    Task { @MainActor in
      defer { self.deliveries.end() }
      if let data, let context = try? JSONDecoder().decode(CompanionContext.self, from: data) {
        await self.onContext?(context)
        await self.recoverInbox()
      }
      if let receipt { await self.onMessage?(receipt) }
    }
  }

  nonisolated func session(_ session: WCSession, didReceive file: WCSessionFile) {
    guard let envelope = file.metadata?["envelope"] as? Data, envelope.count <= 65536 else {
      return
    }
    // The system deletes fileURL on delegate return. Move before starting asynchronous processing.
    let destination = inbox.appendingPathComponent(UUID().uuidString).appendingPathExtension(
      "transfer")
    do {
      let size = try file.fileURL.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
      let files = try FileManager.default.contentsOfDirectory(
        at: inbox, includingPropertiesForKeys: [.fileSizeKey])
      let used = files.reduce(0) {
        $0 + ((try? $1.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0)
      }
      guard size > 0, size <= 256 * 1024 * 1024, files.count < 80, used + size <= 512 * 1024 * 1024
      else { return }
      try FileManager.default.moveItem(at: file.fileURL, to: destination)
      try envelope.write(
        to: destination.deletingPathExtension().appendingPathExtension("json"), options: .atomic)
      deliveries.begin()
      Task { @MainActor in
        defer { self.deliveries.end() }
        await self.onFile?(destination, envelope)
      }
    } catch {
      try? FileManager.default.removeItem(at: destination)
      let message = error.localizedDescription
      deliveries.begin()
      Task { @MainActor in
        defer { self.deliveries.end() }
        self.error = message
      }
    }
  }
  nonisolated func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any]) {
    guard let data = userInfo["payload"] as? Data, data.count <= 65536 else { return }
    deliveries.begin()
    Task { @MainActor in
      defer { self.deliveries.end() }
      await self.onMessage?(data)
    }
  }
  nonisolated func session(
    _ session: WCSession, didReceiveMessageData messageData: Data,
    replyHandler: @escaping (Data) -> Void
  ) {
    guard messageData.count <= 65536 else {
      replyHandler(Data())
      return
    }
    let reply = ReplyBox(replyHandler)
    deliveries.begin()
    Task { @MainActor in
      defer { self.deliveries.end() }
      reply.send(await self.onRequest?(messageData) ?? Data())
    }
  }
  nonisolated func session(
    _ session: WCSession, didFinish fileTransfer: WCSessionFileTransfer, error: (any Error)?
  ) {
    let text = error?.localizedDescription
    deliveries.begin()
    Task { @MainActor in
      defer { self.deliveries.end() }
      self.error = text
    }
  }
  #if os(iOS)
    nonisolated func sessionDidBecomeInactive(_ session: WCSession) {
      deliveries.begin()
      Task { @MainActor in
        defer { self.deliveries.end() }
        self.available = false
      }
    }
    nonisolated func sessionDidDeactivate(_ session: WCSession) { session.activate() }
    nonisolated func sessionWatchStateDidChange(_ session: WCSession) {
      let available = session.isPaired && session.isWatchAppInstalled
      deliveries.begin()
      Task { @MainActor in
        defer { self.deliveries.end() }
        self.available = available
        await self.onActivated?()
      }
    }
  #endif
}
private final class ReplyBox: @unchecked Sendable {
  private let reply: (Data) -> Void
  init(_ reply: @escaping (Data) -> Void) { self.reply = reply }
  func send(_ data: Data) { reply(data) }
}

private final class DeliveryCounter: @unchecked Sendable {
  private let lock = NSLock()
  private var count = 0
  func begin() { lock.withLock { count += 1 } }
  func end() { lock.withLock { count -= 1 } }
  var isEmpty: Bool { lock.withLock { count == 0 } }
}
