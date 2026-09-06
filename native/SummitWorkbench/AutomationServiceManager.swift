import Foundation
import Security

/// 通过 SMAppService 管理随 App 安装的自动化 helper。
/// 不直接写 LaunchAgents/LaunchDaemons，由系统服务管理器负责生命周期。
final class AutomationServiceManager {
    private let logger: StructuredLogger
    private let service: AutomationServiceControlling
    private let helperValidator: (() throws -> Void)?

    init(
        logger: StructuredLogger,
        service: AutomationServiceControlling? = nil,
        helperValidator: (() throws -> Void)? = nil
    ) {
        self.logger = logger
        self.service = service ?? SMAppServiceController()
        self.helperValidator = helperValidator
    }

    func setEnabled(_ enabled: Bool) {
        guard PanelMode.current == .production else {
            logger.log("automation_registration_skipped", fields: ["reason": "development_mode"])
            return
        }
        do {
            let before = service.status
            logger.log(
                "automation_registration_requested",
                fields: ["enabled": String(enabled), "status": statusDescription(before)]
            )
            if enabled {
                if let helperValidator { try helperValidator() } else { try validateHelper() }
                switch before {
                case .notRegistered, .notFound:
                    try service.register()
                case .enabled:
                    break
                case .requiresApproval:
                    logger.log(
                        "automation_registration_waiting_approval",
                        fields: ["status": statusDescription(before)]
                    )
                @unknown default:
                    throw NSError(
                        domain: "SummitWorkbench.Automation",
                        code: 5,
                        userInfo: [NSLocalizedDescriptionKey: "系统返回未知 automation 服务状态"]
                    )
                }
                logger.log(
                    "automation_registered",
                    fields: ["status": statusDescription(service.status)]
                )
            } else {
                switch before {
                case .enabled, .requiresApproval:
                    try service.unregister()
                case .notRegistered, .notFound:
                    break
                @unknown default:
                    break
                }
                logger.log(
                    "automation_unregistered",
                    fields: ["status": statusDescription(service.status)]
                )
            }
        } catch {
            logger.log(
                "automation_registration_failed",
                level: "error",
                fields: [
                    "enabled": String(enabled),
                    "message": error.localizedDescription,
                    "domain": (error as NSError).domain,
                    "code": String((error as NSError).code),
                    "status": statusDescription(service.status),
                ]
            )
        }
    }

    private func statusDescription(_ status: AutomationServiceStatus) -> String {
        switch status {
        case .notRegistered: return "notRegistered"
        case .enabled: return "enabled"
        case .requiresApproval: return "requiresApproval"
        case .notFound: return "notFound"
        @unknown default: return "unknown"
        }
    }

    private func validateHelper() throws {
        let helperURL = Bundle.main.bundleURL
            .appendingPathComponent("Contents/Library/LoginItems/SummitWorkbenchAutomation.app")
        guard FileManager.default.fileExists(atPath: helperURL.path) else {
            throw NSError(
                domain: "SummitWorkbench.Automation",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "缺少 automation helper"]
            )
        }
        guard let helperBundle = Bundle(url: helperURL),
              let helperBuild = helperBundle.object(
            forInfoDictionaryKey: "CFBundleVersion"
        ) as? String, helperBuild == Bundle.main.object(
            forInfoDictionaryKey: "CFBundleVersion"
        ) as? String else {
            throw NSError(
                domain: "SummitWorkbench.Automation",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "automation helper 版本与 App 不一致"]
            )
        }
        guard let executableURL = helperBundle.executableURL,
              helperBundle.bundleIdentifier == "com.summitworkbench.panel.automation",
              FileManager.default.isExecutableFile(atPath: executableURL.path) else {
            throw NSError(
                domain: "SummitWorkbench.Automation",
                code: 6,
                userInfo: [NSLocalizedDescriptionKey: "automation helper 标识或可执行文件无效"]
            )
        }
        var staticCode: SecStaticCode?
        let createStatus = SecStaticCodeCreateWithPath(helperURL as CFURL, [], &staticCode)
        guard createStatus == errSecSuccess, let staticCode,
              SecStaticCodeCheckValidity(staticCode, [], nil) == errSecSuccess else {
            throw NSError(
                domain: "SummitWorkbench.Automation",
                code: 3,
                userInfo: [NSLocalizedDescriptionKey: "automation helper 签名校验失败"]
            )
        }
    }
}
