import Foundation

/// SMAppService login item：每分钟轮询一次本机任务配置。
/// 任务自身按本地时区与 last_run_at 做幂等判断，睡眠唤醒后不会重复写入。
@main
struct SummitWorkbenchAutomationHelper {
    static func main() {
        let worker = workerURL()
        guard FileManager.default.isExecutableFile(atPath: worker.path) else { return }
        while true {
            runJobs(worker: worker)
            RunLoop.current.run(until: Date(timeIntervalSinceNow: 60))
        }
    }

    private static func workerURL() -> URL {
        // .../SummitWorkbench.app/Contents/Library/LoginItems/Helper.app
        let app = Bundle.main.bundleURL
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        return app.appendingPathComponent("Contents/Helpers/SummitWorkbenchWorker")
    }

    private static func runJobs(worker: URL) {
        for job in ["brief", "weekly", "meeting-sync"] {
            let process = Process()
            process.executableURL = worker
            process.arguments = ["--job", job]
            process.environment = [
                "HOME": NSHomeDirectory(),
                "WB_PANEL_MODE": "production",
            ]
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            try? process.run()
            process.waitUntilExit()
        }
    }
}
