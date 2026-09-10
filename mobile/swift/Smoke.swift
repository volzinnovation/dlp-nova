import Foundation

@main
struct DLPSmoke {
    static func main() throws {
        let runtime = try DLPRuntime(eq: 1, neq: 2, top: 3, seed: 1)
        defer { runtime.close() }
        try runtime.addTerm(1, orderKey: "urn:seed")
        try runtime.addTerm(2, orderKey: "urn:a:🛣️")
        try runtime.addFact(10, arguments: [2])
        try runtime.addUnaryRule(head: 11, body: 10)
        let stats = try runtime.materialize()
        guard stats.complete, try runtime.facts().contains(where: { $0.predicate == 11 && $0.arguments == [2] }) else {
            throw DLPError(description: "Missing inferred fact")
        }
        let distance = try DLPRuntime.wgs84Distance(longitude1: 0, latitude1: 0, longitude2: 1, latitude2: 0)
        guard abs(distance - 111319.49079327357) < 1e-6 else { throw DLPError(description: "Wrong WGS84 result") }
        runtime.close()
        do {
            _ = try runtime.materialize()
            throw DLPError(description: "Closed runtime accepted an operation")
        } catch let error as DLPError where error.description == "DLP runtime is closed" {}
        print("PASS Swift: native inference, Unicode term, bounded fact page, WGS84 distance, closed-handle rejection")
        let windows = try DLPWindowStore(width: 10, allowedLateness: 20, context: Data("map-v1".utf8))
        defer { windows.close() }
        _ = try windows.upsert(DLPWindowEvent(id: Data("a".utf8), key: Data("car".utf8), payload: Data([0]), time: 0))
        _ = try windows.upsert(DLPWindowEvent(id: Data("b".utf8), key: Data("car".utf8), payload: Data([1]), time: 5))
        let enteredWindow = try windows.advance(to: 10)
        guard enteredWindow.added.count == 2 else { throw DLPError(description: "Window publication differs") }
        let resumed = try DLPWindowStore.restore(windows.checkpoint(), expectedContext: Data("map-v1".utf8))
        defer { resumed.close() }
        let expired = try resumed.advance(to: 100)
        guard expired.removed.count == 2, expired.historyRemoved.count == 1 else {
            throw DLPError(description: "Window expiry/predecessor differs")
        }
        print("PASS Swift native windows: identified events, publication, checkpoint/resume, idle expiry, predecessor retention")
    }
}
