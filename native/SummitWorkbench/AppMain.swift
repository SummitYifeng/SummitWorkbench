import AppKit

/// 主菜单：常规 App（有 Dock 图标）与菜单栏模式（WB_DOCK_ICON=0）都需要它 ——
/// Cmd+C/V/X/A 等编辑快捷键必须经由主菜单的 Edit 菜单转发到第一响应者
/// （WKWebView 内部编辑器），否则粘贴无效。
private func buildMainMenu() -> NSMenu {
    let mainMenu = NSMenu()
    let appItem = NSMenuItem()
    mainMenu.addItem(appItem)
    let appMenu = NSMenu()
    appMenu.addItem(
        withTitle: "退出 SummitWorkbench",
        action: #selector(NSApplication.terminate(_:)),
        keyEquivalent: "q"
    )
    appItem.submenu = appMenu

    let editItem = NSMenuItem()
    mainMenu.addItem(editItem)
    let editMenu = NSMenu(title: "编辑")
    editMenu.addItem(withTitle: "撤销", action: Selector(("undo:")), keyEquivalent: "z")
    editMenu.addItem(withTitle: "重做", action: Selector(("redo:")), keyEquivalent: "Z")
    editMenu.addItem(.separator())
    editMenu.addItem(withTitle: "剪切", action: Selector(("cut:")), keyEquivalent: "x")
    editMenu.addItem(withTitle: "复制", action: Selector(("copy:")), keyEquivalent: "c")
    editMenu.addItem(withTitle: "粘贴", action: Selector(("paste:")), keyEquivalent: "v")
    editMenu.addItem(withTitle: "全选", action: Selector(("selectAll:")), keyEquivalent: "a")
    editItem.submenu = editMenu
    return mainMenu
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let coordinator = LifecycleCoordinator()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.mainMenu = buildMainMenu()
        // 常规 App：出现在 Dock 与 Cmd-Tab（2026-09-18 使用者反馈：安装后在「应用程序」
        // 里点启动，Dock 里没有图标）。仍保留菜单栏模式入口：WB_DOCK_ICON=0 退回 .accessory。
        let dockIconEnabled = ProcessInfo.processInfo.environment["WB_DOCK_ICON"] != "0"
        NSApp.setActivationPolicy(dockIconEnabled ? .regular : .accessory)
        if dockIconEnabled {
            NSApp.activate(ignoringOtherApps: true)
        }
        coordinator.start(reason: "cold_start")
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        coordinator.reopen()
        return false
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        coordinator.applicationShouldTerminate()
        return .terminateLater
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func applicationWillTerminate(_ notification: Notification) {
        coordinator.applicationTerminating()
    }
}

@main
struct SummitWorkbenchMain {
    static func main() {
        let application = NSApplication.shared
        let delegate = AppDelegate()
        application.delegate = delegate
        application.run()
    }
}
