import Foundation
import Darwin

struct RuntimeRecord: Codable {
    let schemaVersion: Int
    let productID: String
    let apiProtocol: Int
    let frontendBuild: String
    let serverInstance: String
    let workspaceID: String?
    let deviceID: String?
    let pid: Int32
    let port: Int
    let startedAt: Date

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version", productID = "product_id",
             apiProtocol = "api_protocol", frontendBuild = "frontend_build",
             serverInstance = "server_instance", workspaceID = "workspace_id",
             deviceID = "device_id", pid, port, startedAt = "started_at"
    }

    static var url: URL {
        URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Library/Application Support/SummitWorkbench/runtime.json")
    }

    static var candidateURLs: [URL] {
        let root = url.deletingLastPathComponent()
        let profileRoot = root.appendingPathComponent("profiles")
        let profileRecords = (FileManager.default.enumerator(at: profileRoot, includingPropertiesForKeys: nil)?.allObjects as? [URL] ?? [])
            .filter { $0.lastPathComponent == "runtime.json" }
        return [url] + profileRecords
    }

    private static func locatedRecords() -> [(record: RuntimeRecord, url: URL)] {
        candidateURLs.compactMap { candidate in
            guard let data = try? Data(contentsOf: candidate) else { return nil }
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            guard let record = try? decoder.decode(RuntimeRecord.self, from: data) else { return nil }
            return (record, candidate)
        }
    }

    static func load() -> RuntimeRecord? {
        locatedRecords()
            .map(\.record)
            .sorted { $0.startedAt > $1.startedAt }
            .first
    }

    static func load(forPID pid: Int32) -> RuntimeRecord? {
        locatedRecords().first { $0.record.pid == pid }?.record
    }

    static func loadOwned(serverExecutable: String) -> RuntimeRecord? {
        locatedRecords()
            .map(\.record)
            .filter { $0.productID == panelProductID && $0.ownsServer(at: serverExecutable) }
            .sorted { $0.startedAt > $1.startedAt }
            .first
    }

    static func remove(forPID pid: Int32) {
        for item in locatedRecords() where item.record.pid == pid {
            try? FileManager.default.removeItem(at: item.url)
        }
    }

    func owns(_ process: Process) -> Bool {
        guard process.processIdentifier == pid,
              process.isRunning,
              kill(pid, 0) == 0 else { return false }
        return true
    }

    /// A newly launched App may inherit a live server after the previous App
    /// process was force-closed. Only identify it as ours when the runtime
    /// record and the exact bundled executable both match; never adopt or kill
    /// an arbitrary process by port, PID age, or product name alone.
    func ownsServer(at serverExecutable: String) -> Bool {
        guard productID == panelProductID,
              pid != getpid(),
              kill(pid, 0) == 0,
              let actual = executablePath(for: pid) else { return false }
        let expectedPath = URL(fileURLWithPath: serverExecutable).standardizedFileURL.path
        let actualPath = URL(fileURLWithPath: actual).standardizedFileURL.path
        return actualPath == expectedPath
    }

    @discardableResult
    func terminateOwnedServer(at serverExecutable: String) -> Bool {
        guard ownsServer(at: serverExecutable) else { return false }
        return kill(pid, SIGTERM) == 0
    }

    private func executablePath(for pid: Int32) -> String? {
        commandOutput(arguments: ["-p", String(pid), "-o", "comm="])?.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func commandOutput(arguments: [String]) -> String? {
        let process = Process()
        let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: "/bin/ps")
        process.arguments = arguments
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        try? process.run()
        process.waitUntilExit()
        return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)
    }
}
