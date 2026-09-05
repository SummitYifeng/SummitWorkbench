import AppKit
import UniformTypeIdentifiers
import WebKit

final class PanelWindowController: NSWindowController, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler, NSWindowDelegate {
    let webView: WKWebView
    private let logger: StructuredLogger
    private let overlay = NSTextField(labelWithString: "正在启动 SummitWorkbench…")
    var onMessage: ((NativeMessage) -> Void)?
    var onNavigationFailure: ((Error) -> Void)?
    var onContentProcessTerminated: (() -> Void)?

    init(logger: StructuredLogger) {
        self.logger = logger
        let content = WKUserContentController()
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.userContentController = content
        self.webView = WKWebView(frame: .zero, configuration: configuration)
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable],
                              backing: .buffered, defer: false)
        window.title = "SummitWorkbench"
        window.minSize = NSSize(width: 960, height: 640)
        window.center()
        window.setFrameAutosaveName("SummitWorkbench.Panel")
        super.init(window: window)
        window.delegate = self
        webView.navigationDelegate = self
        webView.uiDelegate = self
        content.add(self, name: "wbLifecycle")
        webView.translatesAutoresizingMaskIntoConstraints = false
        overlay.alignment = .center
        overlay.font = NSFont.systemFont(ofSize: 18, weight: .medium)
        overlay.textColor = .secondaryLabelColor
        overlay.translatesAutoresizingMaskIntoConstraints = false
        let container = NSView()
        container.addSubview(webView)
        container.addSubview(overlay)
        NSLayoutConstraint.activate([
            webView.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            webView.topAnchor.constraint(equalTo: container.topAnchor),
            webView.bottomAnchor.constraint(equalTo: container.bottomAnchor),
            overlay.centerXAnchor.constraint(equalTo: container.centerXAnchor),
            overlay.centerYAnchor.constraint(equalTo: container.centerYAnchor),
        ])
        window.contentView = container
        logger.log("window_created")
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    deinit {
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "wbLifecycle")
    }

    func load(_ url: URL, sessionToken: String) {
        overlay.isHidden = false
        logger.log("navigation_started")
        let cookie = HTTPCookie(properties: [
            .domain: "127.0.0.1",
            .path: "/",
            .name: "wb_session",
            .value: sessionToken,
        ])!
        webView.configuration.websiteDataStore.httpCookieStore.setCookie(cookie) { [weak self] in
            DispatchQueue.main.async {
                self?.webView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
            }
        }
    }

    func show() {
        showWindow(nil)
        window?.makeKeyAndOrderFront(nil)
        window?.makeFirstResponder(webView)
        NSApp.activate(ignoringOtherApps: true)
        logger.log("window_presented")
    }

    func showStatus(_ text: String) {
        overlay.stringValue = text
        overlay.isHidden = false
        show()
    }

    func hideStatus() { overlay.isHidden = true }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "wbLifecycle" else { return }
        guard let native = NativeMessage(body: message.body) else {
            logger.log("native_message_ignored", fields: ["reason": "invalid_message"])
            return
        }
        onMessage?(native)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.cancel); return
        }
        if PanelNavigationPolicy.isInternal(url, port: configurationPort) {
            decisionHandler(.allow)
            return
        }
        if ["http", "https"].contains(url.scheme?.lowercased()) {
            NSWorkspace.shared.open(url)
        }
        logger.log("navigation_external", fields: ["scheme": url.scheme ?? "unknown"])
        decisionHandler(.cancel)
    }

    var configurationPort: Int = 0

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        logger.log("navigation_finished")
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        logger.log("navigation_failed", level: "error", fields: ["message": error.localizedDescription])
        onNavigationFailure?(error)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        logger.log("navigation_failed", level: "error", fields: ["message": error.localizedDescription])
        onNavigationFailure?(error)
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        logger.log("web_content_process_terminated", level: "error")
        onContentProcessTerminated?()
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptAlertPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping () -> Void
    ) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "好")
        alert.runModal()
        completionHandler()
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptConfirmPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping (Bool) -> Void
    ) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "确定")
        alert.addButton(withTitle: "取消")
        completionHandler(alert.runModal() == .alertFirstButtonReturn)
    }

    // LSUIElement（纯菜单栏应用）下系统默认文件面板不会自动弹出，
    // 必须自绘 NSOpenPanel 承接 <input type="file">（P3 存产物/导入本地文件）。
    func webView(
        _ webView: WKWebView,
        runOpenPanelWith parameters: WKOpenPanelParameters,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping ([URL]?) -> Void
    ) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.allowedContentTypes = [.item]  // 放行任意扩展名，前端按 .md/.txt 语义使用
        panel.message = "选择要读入工作台的文档（.md / .txt）"
        panel.begin { response in
            completionHandler(response == .OK ? panel.urls : nil)
        }
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        sender.orderOut(nil)
        return false
    }
}

enum PanelNavigationPolicy {
    static func isInternal(_ url: URL, port: Int) -> Bool {
        url.scheme?.lowercased() == "http" && url.host == "127.0.0.1" && url.port == port
    }
}
