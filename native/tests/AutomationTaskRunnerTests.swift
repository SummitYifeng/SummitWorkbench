import Foundation

private func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    let passed = condition()
    if !passed { fputs(message + "\n", stderr) }
    precondition(passed, message)
}

private func process(command: String) -> Process {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/bin/sh")
    process.arguments = ["-c", command]
    return process
}

@main
struct AutomationTaskRunnerTests {
    static func main() {
        let normal = process(command: "sleep 0.05")
        expect(
            AutomationTaskRunner.run(
                normal,
                workerURL: URL(fileURLWithPath: "/bin/sh"),
                timeout: 1,
                gracefulTimeout: 0.1
            ) == .completed,
            "normal worker must complete"
        )

        let stuck = process(command: "trap '' TERM; while :; do :; done")
        let started = Date()
        let result = AutomationTaskRunner.run(
            stuck,
            workerURL: URL(fileURLWithPath: "/bin/sh"),
            timeout: 0.1,
            gracefulTimeout: 0.1
        )
        expect(result == .timedOut, "stuck worker must report timeout")
        expect(Date().timeIntervalSince(started) < 2, "stuck worker must have bounded shutdown")
        expect(!stuck.isRunning, "timed out worker must not remain alive")
        print("native automation task timeout tests passed")
    }
}
