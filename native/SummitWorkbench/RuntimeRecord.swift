import Foundation
import Darwin

struct RuntimeRecord: Codable {
    let schema: Int
    let productID: String
    let launcherPID: Int32
    let launcherStartedAt: Date
    let servicePID: Int32
    let serviceStartedAt: Date
    let launchSession: String
    let frontendBuild: String
    let serverExecutable: String
    let port: Int

    enum CodingKeys: String, CodingKey {
        case schema, productID = "product_id", launcherPID = "launcher_pid",
             launcherStartedAt = "launcher_started_at", servicePID = "service_pid",
             serviceStartedAt = "service_started_at", launchSession = "launch_session",
             frontendBuild = "frontend_build", serverExecutable = "server_executable", port
    }

    static var url: URL {
        URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Library/Application Support/SummitWorkbench/runtime.json")
    }

    func writeAtomically() {
        let fm = FileManager.default
        let directory = Self.url.deletingLastPathComponent()
        try? fm.createDirectory(at: directory, withIntermediateDirectories: true)
        guard let data = try? JSONEncoder().encode(self) else { return }
        let temp = directory.appendingPathComponent(".runtime-\(UUID().uuidString).tmp")
        do {
            try data.write(to: temp, options: .atomic)
            _ = try fm.replaceItemAt(Self.url, withItemAt: temp, backupItemName: nil, options: .usingNewMetadataOnly)
        } catch {
            try? data.write(to: Self.url, options: .atomic)
            try? fm.removeItem(at: temp)
        }
    }

    static func load() -> RuntimeRecord? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(RuntimeRecord.self, from: data)
    }

    static func remove() { try? FileManager.default.removeItem(at: url) }

    func owns(_ process: Process) -> Bool {
        guard process.processIdentifier == servicePID,
              process.isRunning,
              kill(servicePID, 0) == 0 else { return false }
        return executablePath(for: servicePID) == serverExecutable &&
            processStartedAt(servicePID).map { abs($0.timeIntervalSince(serviceStartedAt)) < 2.0 } == true
    }

    private func executablePath(for pid: Int32) -> String? {
        commandOutput(arguments: ["-p", String(pid), "-o", "comm="])?.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func processStartedAt(_ pid: Int32) -> Date? {
        guard let value = commandOutput(arguments: ["-p", String(pid), "-o", "lstart="])?.trimmingCharacters(in: .whitespacesAndNewlines) else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "EEE MMM d HH:mm:ss yyyy"
        return formatter.date(from: value)
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
