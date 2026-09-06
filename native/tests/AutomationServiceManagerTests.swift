import Foundation

private final class FakeAutomationService: AutomationServiceControlling {
    var status: AutomationServiceStatus
    var registerCalls = 0
    var unregisterCalls = 0

    init(status: AutomationServiceStatus) {
        self.status = status
    }

    func register() throws {
        registerCalls += 1
        status = .enabled
    }

    func unregister() throws {
        unregisterCalls += 1
        status = .notRegistered
    }
}

private func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    precondition(condition(), message)
}

@main
struct AutomationServiceManagerTests {
    static func main() {
        for initialStatus in [AutomationServiceStatus.notFound, .notRegistered] {
            let service = FakeAutomationService(status: initialStatus)
            let manager = AutomationServiceManager(
                logger: StructuredLogger(appBuild: "test"),
                service: service,
                helperValidator: {}
            )
            manager.setEnabled(true)
            expect(service.registerCalls == 1, "enabled must register from \(initialStatus)")
            expect(service.unregisterCalls == 0, "enabled must not unregister from \(initialStatus)")
        }

        for initialStatus in [AutomationServiceStatus.enabled, .requiresApproval] {
            let service = FakeAutomationService(status: initialStatus)
            let manager = AutomationServiceManager(
                logger: StructuredLogger(appBuild: "test"),
                service: service,
                helperValidator: {}
            )
            manager.setEnabled(true)
            expect(service.registerCalls == 0, "enabled must not re-register from \(initialStatus)")
        }

        for initialStatus in [AutomationServiceStatus.enabled, .requiresApproval] {
            let service = FakeAutomationService(status: initialStatus)
            let manager = AutomationServiceManager(
                logger: StructuredLogger(appBuild: "test"),
                service: service,
                helperValidator: {}
            )
            manager.setEnabled(false)
            expect(service.unregisterCalls == 1, "disabled must unregister from \(initialStatus)")
        }

        for initialStatus in [AutomationServiceStatus.notFound, .notRegistered] {
            let service = FakeAutomationService(status: initialStatus)
            let manager = AutomationServiceManager(
                logger: StructuredLogger(appBuild: "test"),
                service: service,
                helperValidator: {}
            )
            manager.setEnabled(false)
            expect(service.unregisterCalls == 0, "disabled must not unregister from \(initialStatus)")
        }
        print("native automation service manager tests passed")
    }
}
