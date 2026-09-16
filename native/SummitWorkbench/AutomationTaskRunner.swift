import Foundation

enum AutomationTaskResult {
    case completed
    case timedOut
    case failed
}

enum AutomationTaskRunner {
    static let maxTaskDuration: TimeInterval = 15 * 60
    static let gracefulStopDuration: TimeInterval = 5

    static func run(
        _ process: Process,
        workerURL: URL,
        timeout: TimeInterval = maxTaskDuration,
        gracefulTimeout: TimeInterval = gracefulStopDuration
    ) -> AutomationTaskResult {
        let done = DispatchSemaphore(value: 0)
        do {
            process.terminationHandler = { _ in done.signal() }
            try process.run()
        } catch {
            return .failed
        }
        if done.wait(timeout: .now() + timeout) == .success {
            return .completed
        }

        BoundedProcessTerminator.stop(
            process,
            owns: {
                process.isRunning &&
                    process.executableURL?.standardizedFileURL == workerURL.standardizedFileURL
            },
            gracefulTimeout: gracefulTimeout
        ) {
            done.signal()
        }
        _ = done.wait(timeout: .now() + gracefulTimeout + 1)
        return .timedOut
    }
}
