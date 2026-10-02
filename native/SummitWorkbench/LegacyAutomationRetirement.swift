import Foundation

/// Stops the two legacy user launch agents that could write after the App exits.
enum LegacyAutomationRetirement {
    static func retire() {
        let uid = getuid()
        let home = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true)
        let directory = home.appendingPathComponent("Library/LaunchAgents", isDirectory: true)
        for label in ["com.summitworkbench.brief", "com.summitworkbench.weekly"] {
            let plist = directory.appendingPathComponent(label + ".plist")
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/launchctl")
            process.arguments = ["bootout", "gui/\(uid)/\(label)"]
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            try? process.run()
            process.waitUntilExit()
            if FileManager.default.fileExists(atPath: plist.path) {
                try? FileManager.default.removeItem(at: plist)
            }
        }
    }
}
