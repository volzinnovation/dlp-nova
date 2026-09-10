import Foundation
import CDLP

public struct DLPError: Error, CustomStringConvertible {
    public let description: String
}

public struct DLPFact: Equatable, Sendable {
    public let predicate: UInt64
    public let arguments: [UInt64]
}

public struct DLPStats: Sendable {
    public let rounds: UInt64
    public let facts: UInt64
    public let terms: UInt64
    public let violations: UInt64
    public let complete: Bool
}

/// A minimal ABI adapter. Calls on each handle are serialized, including close.
/// IDs and the compiled rule/term dictionary belong to the host application.
/// Run substantial inference on an application worker, away from its UI thread.
public final class DLPRuntime: @unchecked Sendable {
    private let lock = NSLock()
    private var handle: OpaquePointer?

    public init(eq: UInt64, neq: UInt64, top: UInt64, seed: UInt64,
                maxRounds: UInt64 = 1000, maxFacts: UInt64 = 1_000_000,
                maxTerms: UInt64 = 1_000_000, maxDepth: UInt64 = 32) throws {
        guard dlp_runtime_abi_version() == 1 && dlp_domain_abi_version() == 1 else {
            throw DLPError(description: "Unsupported DLP native ABI")
        }
        var limits = dlp_runtime_limits(max_rounds: maxRounds, max_facts: maxFacts,
                                       max_terms: maxTerms, max_depth: maxDepth)
        var created: OpaquePointer?
        try Self.check(dlp_runtime_new(eq, neq, top, seed, &limits, &created))
        handle = created
    }

    deinit { close() }

    public func close() {
        lock.lock()
        defer { lock.unlock() }
        if let pointer = handle { dlp_runtime_free(pointer); handle = nil }
    }

    private static func check(_ status: Int32) throws {
        if status != 0 {
            throw DLPError(description: String(cString: dlp_runtime_error()))
        }
    }

    private func withHandle<T>(_ work: (OpaquePointer) throws -> T) throws -> T {
        lock.lock()
        defer { lock.unlock() }
        guard let pointer = handle else { throw DLPError(description: "DLP runtime is closed") }
        return try work(pointer)
    }

    public func addTerm(_ id: UInt64, category: UInt32 = 0,
                        orderKey: String, literalGroup: UInt64 = 0) throws {
        guard orderKey.utf8.count <= 1_048_576 && !orderKey.utf8.contains(0) else {
            throw DLPError(description: "Order key exceeds 1 MiB or contains NUL")
        }
        try withHandle { pointer in
            try orderKey.withCString { key in
                try Self.check(dlp_runtime_add_term(pointer, id, category, key, literalGroup))
            }
        }
    }

    public func addFact(_ predicate: UInt64, arguments: [UInt64]) throws {
        guard arguments.count <= 4096 else { throw DLPError(description: "Fact arity exceeds 4096") }
        try withHandle { pointer in
            try arguments.withUnsafeBufferPointer { buffer in
                try Self.check(dlp_runtime_add_fact(pointer, predicate, buffer.baseAddress, buffer.count))
            }
        }
    }

    /// Convenience for one positive unary inclusion. The C ABI supports full Horn IR.
    public func addUnaryRule(head: UInt64, body: UInt64) throws {
        try withHandle { pointer in
            var variable = dlp_runtime_expr(kind: 1, reserved: 0, reference: 0, arity: 0, arguments: nil)
            try withUnsafePointer(to: &variable) { expression in
                var conclusion = dlp_runtime_atom(predicate: head, arity: 1, arguments: expression)
                var premise = dlp_runtime_atom(predicate: body, arity: 1, arguments: expression)
                try "Swift unary inclusion".withCString { label in
                    try Self.check(dlp_runtime_add_rule(pointer, &conclusion, &premise, 1, 1, label))
                }
            }
        }
    }

    public func materialize() throws -> DLPStats {
        try withHandle { pointer in
            try Self.check(dlp_runtime_materialize(pointer))
            var stats = dlp_runtime_stats()
            try Self.check(dlp_runtime_get_stats(pointer, &stats))
            return DLPStats(rounds: stats.rounds, facts: stats.facts, terms: stats.terms,
                            violations: stats.violations, complete: stats.complete != 0)
        }
    }

    /// Copies at most limit facts and at most maxArity arguments per fact.
    /// The result is a bounded prefix; callers can page using offset.
    public func facts(offset: UInt64 = 0, limit: Int = 256, maxArity: Int = 64) throws -> [DLPFact] {
        guard (0...4096).contains(limit), (0...4096).contains(maxArity), offset <= UInt64(Int.max) else {
            throw DLPError(description: "Invalid fact page limits")
        }
        return try withHandle { pointer in
            var stats = dlp_runtime_stats()
            try Self.check(dlp_runtime_get_stats(pointer, &stats))
            guard stats.complete != 0 else { throw DLPError(description: "Runtime has no complete result") }
            guard offset <= stats.facts else { throw DLPError(description: "Fact offset out of range") }
            let count = Int(min(UInt64(limit), stats.facts - offset))
            guard offset <= UInt64(Int.max - count) else { throw DLPError(description: "Fact offset too large") }
            var result: [DLPFact] = []
            var cells = 0
            for index in 0..<count {
                var predicate: UInt64 = 0
                var arity = 0
                try Self.check(dlp_runtime_fact(pointer, Int(offset) + index, &predicate, nil, 0, &arity))
                guard arity <= maxArity else { throw DLPError(description: "Fact exceeds maxArity") }
                cells += arity + 1
                guard cells <= 1_000_000 else { throw DLPError(description: "Fact page exceeds argument budget") }
                var arguments = [UInt64](repeating: 0, count: arity)
                try arguments.withUnsafeMutableBufferPointer { buffer in
                    try Self.check(dlp_runtime_fact(pointer, Int(offset) + index, &predicate,
                                                    buffer.baseAddress, buffer.count, &arity))
                }
                result.append(DLPFact(predicate: predicate, arguments: arguments))
            }
            return result
        }
    }

    /// Ellipsoidal WGS84 point distance, metres; input order is longitude, latitude.
    public static func wgs84Distance(longitude1: Double, latitude1: Double,
                                     longitude2: Double, latitude2: Double) throws -> Double {
        var a = dlp_domain_value(), b = dlp_domain_value(), output = dlp_domain_value()
        a.tag = 9; a.x = longitude1; a.y = latitude1
        b.tag = 9; b.x = longitude2; b.y = latitude2
        var status: Int32 = -1
        let code = [a, b].withUnsafeBufferPointer { input in
            dlp_domain_evaluate(41, input.baseAddress, 1, 2, &output, &status)
        }
        guard code == 0 && status == 0 else {
            throw DLPError(description: "WGS84 distance failed (status \(status)): \(String(cString: dlp_domain_last_error()))")
        }
        return output.x
    }
}
