import Foundation

private func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    let passed = condition()
    if !passed { fputs(message + "\n", stderr) }
    precondition(passed, message)
}

private func child(ignoresSIGTERM: Bool) throws -> Process {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/bin/sh")
    let body = ignoresSIGTERM
        ? "trap '' TERM; while :; do :; done"
        : "sleep 30"
    process.arguments = ["-c", body]
    try process.run()
    return process
}

@main
struct ServiceSupervisorTests {
    static func main() throws {
        let normal = try child(ignoresSIGTERM: false)
        let normalDone = DispatchSemaphore(value: 0)
        BoundedProcessTerminator.stop(
            normal,
            owns: { normal.isRunning },
            gracefulTimeout: 0.2
        ) {
            normalDone.signal()
        }
        expect(normalDone.wait(timeout: .now() + 2) == .success, "normal child must stop promptly")
        normal.waitUntilExit()

        let stuck = try child(ignoresSIGTERM: true)
        let stuckDone = DispatchSemaphore(value: 0)
        var completions = 0
        var cleanedBeforeCompletion = false
        BoundedProcessTerminator.stop(
            stuck,
            owns: { stuck.isRunning },
            gracefulTimeout: 0.2
        ) {
            completions += 1
            cleanedBeforeCompletion = !stuck.isRunning
            stuckDone.signal()
        }
        BoundedProcessTerminator.stop(
            stuck,
            owns: { stuck.isRunning },
            gracefulTimeout: 0.2
        ) {
            completions += 1
            stuckDone.signal()
        }
        expect(stuckDone.wait(timeout: .now() + 2) == .success, "stuck child must have a bounded completion")
        expect(stuckDone.wait(timeout: .now() + 0.2) == .timedOut, "duplicate stop must not complete twice")
        expect(completions == 1, "stop completion must be called exactly once")
        expect(cleanedBeforeCompletion, "restart may proceed only after the stuck child is terminated")
        if stuck.isRunning { kill(stuck.processIdentifier, SIGKILL) }
        stuck.waitUntilExit()

        let unowned = try child(ignoresSIGTERM: false)
        let unownedDone = DispatchSemaphore(value: 0)
        BoundedProcessTerminator.stop(
            unowned,
            owns: { false },
            gracefulTimeout: 0.2
        ) { unownedDone.signal() }
        expect(unownedDone.wait(timeout: .now() + 1) == .success, "identity mismatch must not block shutdown")
        expect(unowned.isRunning, "identity mismatch must never signal another process")
        kill(unowned.processIdentifier, SIGKILL)
        unowned.waitUntilExit()
        print("native service supervisor lifecycle tests passed")
    }
}
