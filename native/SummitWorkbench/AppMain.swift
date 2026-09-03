import AppKit

/// 最小主菜单：LSUIElement（accessory）应用没有系统菜单，Cmd+C/V/X/A 等编辑快捷键
/// 必须经由主菜单的 Edit 菜单转发到第一响应者（WKWebView 内部编辑器），否则粘贴无效。
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
        NSApp.setActivationPolicy(.accessory)
        coordinator.start(reason: "cold_start")
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        coordinator.reopen()
        return false
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
