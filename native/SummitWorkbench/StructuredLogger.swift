import Foundation

final class StructuredLogger {
    private let fileURL: URL
    private let session: String
    private let appBuild: String
    private var recent: [String] = []
    private let queue = DispatchQueue(label: "com.summitworkbench.logger")

    init(appBuild: String) {
        self.fileURL = URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Library/Logs/summitworkbench-panel.log")
        self.session = UUID().uuidString
        self.appBuild = appBuild
    }

    func log(_ event: String, level: String = "info", fields: [String: String] = [:]) {
        var object: [String: Any] = [
            "ts": ISO8601DateFormatter().string(from: Date()),
            "level": level,
            "component": "launcher",
            "event": event,
            "launch_session": session,
            "app_build": appBuild,
        ]
        fields.forEach { object[$0.key] = $0.value }
        guard let data = try? JSONSerialization.data(withJSONObject: object),
              let line = String(data: data, encoding: .utf8) else { return }
        queue.async { [weak self] in
            guard let self else { return }
            let rendered = line + "\n"
            self.recent.append(rendered.trimmingCharacters(in: .newlines))
            if self.recent.count > 10 { self.recent.removeFirst(self.recent.count - 10) }
            self.write(rendered)
        }
    }

    func recentEvents() -> [String] {
        queue.sync { recent }
    }

    private func write(_ line: String) {
        let fm = FileManager.default
        try? fm.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if let attrs = try? fm.attributesOfItem(atPath: fileURL.path),
           let size = attrs[.size] as? NSNumber, size.intValue >= 5 * 1024 * 1024 {
            rotate()
        }
        if !fm.fileExists(atPath: fileURL.path) { fm.createFile(atPath: fileURL.path, contents: nil) }
        guard let handle = try? FileHandle(forWritingTo: fileURL) else { return }
        handle.seekToEndOfFile()
        try? handle.write(contentsOf: Data(line.utf8))
        try? handle.close()
    }

    private func rotate() {
        let fm = FileManager.default
        for index in stride(from: 3, through: 1, by: -1) {
            let old = URL(fileURLWithPath: fileURL.path + ".\(index)")
            let newer = index == 1 ? fileURL : URL(fileURLWithPath: fileURL.path + ".\(index - 1)")
            if fm.fileExists(atPath: old.path) { try? fm.removeItem(at: old) }
            if fm.fileExists(atPath: newer.path) { try? fm.moveItem(at: newer, to: old) }
        }
    }
}
