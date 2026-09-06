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
    let passed = condition()
    if !passed { fputs(message + "\n", stderr) }
    precondition(passed, message)
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

        let diagnosticText = PrivacyRedactor.text(
            "canary-secret-token Authorization: Bearer abc123 " +
            "Cookie: session=secret-value meeting body: unreleased plan " +
            "/Users/alice/Library/Logs/panel.log"
        )
        expect(!diagnosticText.contains("canary-secret-token"), "Swift diagnostics must redact canary")
        expect(!diagnosticText.contains("abc123"), "Swift diagnostics must redact bearer token")
        expect(!diagnosticText.contains("secret-value"), "Swift diagnostics must redact cookie")
        expect(!diagnosticText.contains("unreleased plan"), "Swift diagnostics must redact meeting body")
        expect(!diagnosticText.contains("/Users/alice"), "Swift diagnostics must redact home path")
        expect(PrivacyRedactor.text("provider_token_invalid") == "provider_token_invalid",
               "Swift diagnostics must preserve error code")
        print("native automation service manager tests passed")
    }
}
