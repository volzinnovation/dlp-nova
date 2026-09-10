import Foundation
import CDLP

/// Opaque, immutable application payloads; the host owns their typed encoding.
public struct DLPWindowEvent: Sendable {
    public let id: Data
    public let key: Data
    public let payload: Data
    public let time: Int64
    public let revision: Int64

    public init(id: Data, key: Data, payload: Data, time: Int64, revision: Int64 = 0) {
        self.id = id; self.key = key; self.payload = payload; self.time = time; self.revision = revision
    }
}

public struct DLPWindowChange: Sendable {
    public let revision: UInt64
    public let added: [DLPWindowEvent]
    public let removed: [DLPWindowEvent]
    public let historyAdded: [DLPWindowEvent]
    public let historyRemoved: [DLPWindowEvent]
}

/// Serialized native window owner. Clocks are explicit signed microseconds.
public final class DLPWindowStore: @unchecked Sendable {
    private let lock = NSLock()
    private var handle: OpaquePointer?

    private init(adopting pointer: OpaquePointer) { handle = pointer }

    public init(width: Int64, allowedLateness: Int64 = 0, end: Int64 = 0,
                watermark: Int64? = nil, maxEvents: UInt64 = 10_000,
                maxBytes: UInt64 = 16 * 1024 * 1024, maxKeys: UInt64 = 1000,
                retainPredecessor: Bool = true, allowOffsetGaps: Bool = false,
                context: Data = Data()) throws {
        guard dlp_windows_abi() == 1 else { throw DLPError(description: "Unsupported window ABI") }
        var config = dlp_window_config(width: width, lateness: allowedLateness, end: end,
                                      watermark: watermark ?? end, max_events: maxEvents, max_bytes: maxBytes,
                                      max_keys: maxKeys, predecessors: retainPredecessor ? 1 : 0,
                                      allow_gaps: allowOffsetGaps ? 1 : 0)
        var created: OpaquePointer?
        try Self.withBytes(context) { bytes in
            try Self.check(dlp_windows_new(&config, bytes, &created))
        }
        handle = created
    }

    deinit { close() }

    public func close() {
        lock.lock(); defer { lock.unlock() }
        if let pointer = handle { dlp_windows_free(pointer); handle = nil }
    }

    private static func check(_ result: Int32) throws {
        if result != 0 { throw DLPError(description: String(cString: dlp_windows_error())) }
    }

    private func withHandle<T>(_ work: (OpaquePointer) throws -> T) throws -> T {
        lock.lock(); defer { lock.unlock() }
        guard let pointer = handle else { throw DLPError(description: "Native window store is closed") }
        return try work(pointer)
    }

    private static func withBytes<T>(_ data: Data, _ work: (dlp_window_bytes) throws -> T) rethrows -> T {
        try data.withUnsafeBytes { buffer in
            try work(dlp_window_bytes(data: buffer.baseAddress, size: buffer.count))
        }
    }

    private static func copy(_ value: dlp_window_bytes) -> Data {
        value.size == 0 ? Data() : Data(bytes: value.data!, count: value.size)
    }

    private static func event(_ value: dlp_window_event) -> DLPWindowEvent {
        DLPWindowEvent(id: copy(value.id), key: copy(value.key), payload: copy(value.row),
                       time: value.time, revision: value.revision)
    }

    private static func change(_ pointer: OpaquePointer) throws -> DLPWindowChange {
        defer { dlp_windows_change_free(pointer) }
        var revision: UInt64 = 0
        try check(dlp_windows_change_revision(pointer, &revision))
        var streams: [[DLPWindowEvent]] = []
        for mode: UInt32 in 0..<4 {
            var values: [DLPWindowEvent] = [], buffer = [dlp_window_event](repeating: dlp_window_event(), count: 128)
            var count = 0, done: Int32 = 0
            while done == 0 {
                try buffer.withUnsafeMutableBufferPointer { array in
                    try check(dlp_windows_change_next(pointer, mode, array.baseAddress, array.count, &count, &done))
                }
                values.append(contentsOf: buffer.prefix(count).map(event))
            }
            streams.append(values)
        }
        return DLPWindowChange(revision: revision, added: streams[0], removed: streams[1],
                              historyAdded: streams[2], historyRemoved: streams[3])
    }

    public func upsert(_ event: DLPWindowEvent, source: Data? = nil, offset: Int64? = nil) throws -> DLPWindowChange {
        guard (source == nil) == (offset == nil), source == nil || !source!.isEmpty else {
            throw DLPError(description: "Source and offset must be supplied together")
        }
        return try withHandle { pointer in
            try Self.withBytes(event.id) { id in try Self.withBytes(event.key) { key in
                try Self.withBytes(event.payload) { payload in try Self.withBytes(source ?? Data()) { sourceBytes in
                    var input = dlp_window_event(id: id, key: key, row: payload, time: event.time, revision: event.revision)
                    var publication: OpaquePointer?
                    try Self.check(dlp_windows_upsert(pointer, &input, sourceBytes, offset ?? -1, &publication))
                    return try Self.change(publication!)
                }}
            }}
        }
    }

    public func advance(to end: Int64, watermark: Int64? = nil) throws -> DLPWindowChange {
        try withHandle { pointer in
            var publication: OpaquePointer?
            try Self.check(dlp_windows_advance(pointer, end, watermark ?? end, &publication))
            return try Self.change(publication!)
        }
    }

    public func checkpoint() throws -> Data {
        try withHandle { pointer in
            var size = 0
            try Self.check(dlp_windows_checkpoint(pointer, nil, 0, &size))
            var output = Data(count: size)
            try output.withUnsafeMutableBytes { buffer in
                try Self.check(dlp_windows_checkpoint(pointer, buffer.baseAddress, buffer.count, &size))
            }
            return output
        }
    }

    public static func restore(_ checkpoint: Data, expectedContext: Data? = nil,
                               maxCheckpointBytes: UInt64 = 64 * 1024 * 1024,
                               maxEvents: UInt64 = 10_000, maxBytes: UInt64 = 16 * 1024 * 1024,
                               maxKeys: UInt64 = 1000) throws -> DLPWindowStore {
        var result: OpaquePointer?
        try withBytes(expectedContext ?? Data()) { contextBytes in
            var expected = contextBytes
            try checkpoint.withUnsafeBytes { buffer in
                if expectedContext != nil {
                    try check(dlp_windows_restore(buffer.baseAddress, buffer.count, maxCheckpointBytes,
                                                   maxEvents, maxBytes, maxKeys, &expected, &result))
                } else {
                    try check(dlp_windows_restore(buffer.baseAddress, buffer.count, maxCheckpointBytes,
                                                   maxEvents, maxBytes, maxKeys, nil, &result))
                }
            }
        }
        return DLPWindowStore(adopting: result!)
    }
}
