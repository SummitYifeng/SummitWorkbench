import Foundation
import ServiceManagement

/// 可注入的 SMAppService 状态，供原生状态机单测使用。
enum AutomationServiceStatus: Equatable {
    case notRegistered
    case enabled
    case requiresApproval
    case notFound
}

protocol AutomationServiceControlling {
    var status: AutomationServiceStatus { get }
    func register() throws
    func unregister() throws
}

/// 生产环境对 SMAppService 的最小适配层，状态机本身不直接依赖系统对象。
final class SMAppServiceController: AutomationServiceControlling {
    private let service = SMAppService.loginItem(identifier: "com.summitworkbench.panel.automation")

    var status: AutomationServiceStatus {
        switch service.status {
        case .notRegistered: return .notRegistered
        case .enabled: return .enabled
        case .requiresApproval: return .requiresApproval
        case .notFound: return .notFound
        @unknown default: return .notFound
        }
    }

    func register() throws { try service.register() }
    func unregister() throws { try service.unregister() }
}
