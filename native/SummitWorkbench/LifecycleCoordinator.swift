import AppKit
import Foundation
import UniformTypeIdentifiers

final class LifecycleCoordinator {
    private var configuration: AppConfiguration?
    private var logger: StructuredLogger?
    private var supervisor: ServiceSupervisor?
    private var panel: PanelWindowController?
    private var automationService: AutomationServiceManager?
    private var updateCoordinator: UpdateCoordinator?
    private var currentClientBuild: String?
    private var currentClientServerInstance: String?
    private var startInFlight = false
    private var recoveryAttempts = 0

    func start(reason: String) {
        guard !startInFlight else {
            logger?.log("reopen_coalesced")
            return
        }
        startInFlight = true
        do {
            if configuration == nil {
                let config = try AppConfiguration.load()
                configuration = config
                let log = StructuredLogger(appBuild: config.manifest.frontendBuild)
                logger = log
                automationService = AutomationServiceManager(logger: log)
                updateCoordinator = UpdateCoordinator(
                    logger: log,
                    feedURL: config.updateFeedURL,
                    publicKeyBase64: config.updatePublicKey,
                    currentVersion: config.manifest.version ?? "0.0.0",
                    currentBuild: config.manifest.build ?? "0",
                    architecture: config.manifest.architecture ?? "arm64",
                    workspaceCompatibility: config.updateWorkspaceCompatibility,
                    statusHandler: { [weak self] status in self?.handleUpdateStatus(status) }
                )
                log.log("app_started", fields: ["reason": reason, "mode": config.mode.rawValue])
                log.log("manifest_loaded", fields: ["frontend_build": config.manifest.frontendBuild])
                let window = PanelWindowController(logger: log)
                window.configurationPort = 0
                panel = window
                let service = ServiceSupervisor(configuration: config, logger: log)
                supervisor = service
                service.onStateChange = { [weak self] state in self?.handleState(state) }
                service.onIdentityChange = { [weak self] identity in self?.identityBecameReady(identity) }
                window.onMessage = { [weak self] message in self?.handle(message) }
                window.onNavigationFailure = { [weak self] error in self?.navigationFailed(error) }
                window.onContentProcessTerminated = { [weak self] in self?.contentProcessTerminated() }
            } else {
                logger?.log("reopen_received", fields: ["reason": reason])
            }
            guard let service = supervisor, let window = panel else {
                throw NSError(domain: "SummitWorkbench.Lifecycle", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "生命周期组件初始化失败"])
            }
            window.showStatus("正在启动 SummitWorkbench…")
            service.ensureReady { [weak self] identity in
                self?.startInFlight = false
                guard let self, let identity else {
                    self?.presentFailure()
                    return
                }
                self.loadReadyService(identity)
            }
        } catch {
            startInFlight = false
            logger?.log("manifest_invalid", level: "error", fields: ["message": error.localizedDescription])
            presentError("无法启动 SummitWorkbench", detail: error.localizedDescription)
        }
    }

    func reopen() {
        logger?.log("reopen_received")
        if startInFlight {
            logger?.log("reopen_coalesced")
            return
        }
        guard let supervisor, let panel else {
            start(reason: "reopen")
            return
        }
        startInFlight = true
        panel.showStatus("正在检查服务…")
        supervisor.ensureReady { [weak self] identity in
            guard let self else { return }
            self.startInFlight = false
            guard let identity else { self.presentFailure(); return }
            if self.currentClientBuild != identity.frontendBuild ||
                self.currentClientServerInstance != identity.serverInstance {
                self.loadReadyService(identity)
            } else {
                panel.hideStatus()
                panel.show()
                self.logger?.log("version_match")
            }
        }
    }

    func applicationTerminating() {
        logger?.log("app_terminated")
        supervisor?.shutdownForApplicationTermination()
    }

    private func loadReadyService(_ identity: ServiceIdentity) {
        guard let config = configuration, let panel, let logger else { return }
        currentClientBuild = nil
        currentClientServerInstance = nil
        panel.showStatus("正在加载工作台…")
        logger.log("navigation_started", fields: ["frontend_build": identity.frontendBuild])
        guard let port = identity.port else { return }
        panel.configurationPort = port
        panel.load(config.panelURL(for: identity.frontendBuild, port: port), sessionToken: supervisor?.sessionToken ?? "")
    }

    private func handle(_ message: NativeMessage) {
        switch message {
        case .clientReady(let build, let serverInstance):
            guard let identity = supervisor?.identity else { return }
            guard build == identity.frontendBuild, serverInstance == identity.serverInstance else {
                logger?.log("version_mismatch", level: "error")
                panel?.showStatus("版本不一致，正在重新加载…")
                loadReadyService(identity)
                return
            }
            currentClientBuild = build
            currentClientServerInstance = serverInstance
            recoveryAttempts = 0
            panel?.hideStatus()
            logger?.log("client_ready", fields: ["server_instance": serverInstance])
            logger?.log("version_match")
            updateCoordinator?.checkIfDue()
        case .quit:
            logger?.log("user_quit_requested")
            panel?.showStatus("正在退出…")
            supervisor?.stop { [weak self] in
                self?.panel?.close()
                NSApp.terminate(nil)
            }
        case .restartService:
            guard let supervisor else { return }
            startInFlight = true
            panel?.showStatus("正在切换到完整工作台…")
            logger?.log("service_restart_requested", fields: ["reason": "workspace_changed"])
            supervisor.restartForWorkspaceChange { [weak self] identity in
                guard let self else { return }
                self.startInFlight = false
                guard let identity else { self.presentFailure(); return }
                self.loadReadyService(identity)
            }
        case .copyDiagnostics:
            copyDiagnostics()
        case .openLogDirectory:
            let logs = URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Logs")
            NSWorkspace.shared.open(logs)
            logger?.log("log_directory_opened")
        case .openExternal(let url):
            NSWorkspace.shared.open(url)
        case .saveTextFile(let filename, let content):
            saveTextFile(filename: filename, content: content)
        case .automationSettingsChanged(let enabled):
            automationService?.setEnabled(enabled)
        case .updateAutoCheckChanged(let enabled):
            updateCoordinator?.setAutomaticChecksEnabled(enabled)
        case .checkForUpdates:
            updateCoordinator?.check(manual: true)
        }
    }

    private func handleUpdateStatus(_ status: UpdateStatus) {
        let message: String
        switch status {
        case .checking: message = "正在检查更新…"
        case .unavailable: message = "更新源未配置"
        case .current: message = "当前已是最新版本"
        case .available(let version): message = "发现可用更新 (version)"
        case .failed: message = "更新检查失败，可重试"
        case .downloadFailed: message = "更新下载失败，可重试"
        }
        panel?.showStatus(message)
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in
            self?.panel?.hideStatus()
        }
    }

    private func saveTextFile(filename: String, content: String) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = filename
        panel.canCreateDirectories = true
        panel.allowedContentTypes = [.json]
        panel.message = "保存 SummitWorkbench 本机同步状态副本"
        panel.begin { [weak self] response in
            guard response == .OK, let url = panel.url else { return }
            do {
                try content.write(to: url, atomically: true, encoding: .utf8)
                self?.logger?.log("sync_snapshot_exported")
            } catch {
                self?.logger?.log(
                    "sync_snapshot_export_failed",
                    level: "error",
                    fields: ["message": error.localizedDescription]
                )
            }
        }
    }

    private func handleState(_ state: SupervisorState) {
        switch state {
        case .ready: break
        case .starting, .probing: panel?.showStatus("正在启动 SummitWorkbench…")
        case .restarting: panel?.showStatus("服务异常，正在自动恢复…")
        case .degraded: panel?.showStatus("正在等待开发服务…")
        case .crashLoop: presentError("服务反复启动失败", detail: "请点击重试，或复制诊断信息查看最近生命周期事件。")
        case .conflict: presentError("端口被其他服务占用", detail: "未识别到可由当前 App 管理的 SummitWorkbench 服务；未终止未知进程。")
        default: break
        }
    }

    private func identityBecameReady(_ identity: ServiceIdentity) {
        guard !startInFlight else { return }
        if currentClientBuild != identity.frontendBuild ||
            currentClientServerInstance != identity.serverInstance {
            logger?.log("service_recovered", fields: ["server_instance": identity.serverInstance])
            loadReadyService(identity)
        }
    }

    private func navigationFailed(_ error: Error) {
        logger?.log("navigation_failed", level: "error", fields: ["message": error.localizedDescription])
        recoverPanel(message: "页面加载失败，正在自动恢复…")
    }

    private func contentProcessTerminated() {
        guard recoveryAttempts < 3 else {
            presentError("页面进程已停止", detail: "自动恢复次数已用尽，请重新打开 App 或复制诊断信息。")
            return
        }
        logger?.log("web_content_process_terminated", fields: ["attempt": String(recoveryAttempts + 1)])
        recoverPanel(message: "页面进程已停止，正在自动恢复…")
    }

    private func recoverPanel(message: String) {
        guard !startInFlight else { return }
        guard recoveryAttempts < 3 else {
            presentError("页面恢复失败", detail: "自动恢复次数已用尽，请重试或复制诊断信息。")
            return
        }
        recoveryAttempts += 1
        startInFlight = true
        panel?.showStatus(message)
        supervisor?.ensureReady { [weak self] identity in
            guard let self else { return }
            self.startInFlight = false
            guard let identity else { self.presentFailure(); return }
            self.loadReadyService(identity)
        }
    }

    private func presentFailure() {
        let state = supervisor?.state.rawValue ?? "unknown"
        let detail = state == SupervisorState.conflict.rawValue
            ? "端口被其他服务占用，未终止未知进程。"
            : "服务尚未就绪（状态：\(state)）。"
        presentError("SummitWorkbench 暂时无法启动", detail: detail)
    }

    private func presentError(_ title: String, detail: String) {
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = title
        alert.informativeText = detail
        alert.addButton(withTitle: "重试")
        alert.addButton(withTitle: "复制诊断信息")
        alert.addButton(withTitle: "关闭")
        let response = alert.runModal()
        if response == .alertFirstButtonReturn { start(reason: "user_retry") }
        else if response == .alertSecondButtonReturn { copyDiagnostics() }
    }

    private func copyDiagnostics() {
        guard let config = configuration else { return }
        let identity = supervisor?.identity
        let text = [
            "App frontend build: \(config.manifest.frontendBuild)",
            "Frontend client build: \(currentClientBuild ?? "unknown")",
            "Served frontend build: \(identity?.frontendBuild ?? "unknown")",
            "Server version/instance: \(identity?.serverVersion ?? "unknown")/\(identity?.serverInstance ?? "unknown")",
            "Panel mode: \(config.mode.rawValue)",
            "Port: \(supervisor?.identity?.port ?? 0)",
            "Service state: \(supervisor?.state.rawValue ?? "unknown")",
            "Recent lifecycle events:",
        ] + (logger?.recentEvents() ?? []) + [
            "Log: ~/Library/Logs/summitworkbench-panel.log",
        ]
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text.joined(separator: "\n"), forType: .string)
        logger?.log("diagnostics_copied")
    }
}
