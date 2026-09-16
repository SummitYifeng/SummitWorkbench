import Foundation
import Darwin

/// A bounded, identity-gated stop for one exact child process instance.
final class BoundedProcessTerminator {
    private static let lock = NSLock()
    private static var inFlight: Set<Int32> = []

    static func stop(
        _ process: Process,
        owns: @escaping () -> Bool,
        gracefulTimeout: TimeInterval = 5.0,
        completion: @escaping () -> Void
    ) {
        let pid = process.processIdentifier
        lock.lock()
        guard !inFlight.contains(pid) else {
            lock.unlock()
            return
        }
        inFlight.insert(pid)
        lock.unlock()

        var completed = false
        let finish: () -> Void = {
            lock.lock()
            inFlight.remove(pid)
            let shouldComplete = !completed
            completed = true
            lock.unlock()
            if shouldComplete { completion() }
        }

        guard process.isRunning else {
            finish()
            return
        }
        guard owns() else {
            // The PID is no longer proven to be this App's child.  Never send
            // a signal to an unverified process; let the caller preserve its
            // diagnostic record and still finish the App shutdown.
            finish()
            return
        }

        process.terminationHandler = { _ in finish() }
        process.terminate()
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + gracefulTimeout) {
            guard process.isRunning else { return }
            guard owns() else {
                finish()
                return
            }
            // Re-checking the exact Process instance and executable gate is
            // intentionally required before the final signal.
            kill(pid, SIGKILL)
            DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 0.25) {
                finish()
            }
        }
    }
}
