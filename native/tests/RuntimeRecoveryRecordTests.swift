import Foundation

private func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    let passed = condition()
    if !passed { fputs(message + "\n", stderr) }
    precondition(passed, message)
}

@main
struct RuntimeRecoveryRecordTests {
    static func main() {
        let record = UnfinishedOperationRecord(
            operationID: "service-1",
            executorID: "executor-1",
            kind: "service",
            startedAt: Date()
        )
        record.save()
        let loaded = UnfinishedOperationRecord.load()
        expect(loaded?.operationID == "service-1", "unfinished record must round-trip")
        expect(loaded?.executorID == "executor-1", "record must retain executor identity")
        expect(loaded?.kind == "service", "record must retain operation kind")
        UnfinishedOperationRecord.remove(ifOperationID: "other")
        expect(UnfinishedOperationRecord.load() != nil, "mismatched cleanup must preserve evidence")
        UnfinishedOperationRecord.remove(ifOperationID: "service-1")
        expect(UnfinishedOperationRecord.load() == nil, "matching cleanup must remove evidence")
        print("native runtime recovery record tests passed")
    }
}
