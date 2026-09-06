import Foundation

let panelProductID = "com.summitworkbench.panel"
let panelAPIProtocol = 2

enum PanelMode: String {
    case production
    case developmentManaged = "development-managed"
    case developmentExternal = "development-external"

    static var current: PanelMode {
        PanelMode(rawValue: ProcessInfo.processInfo.environment["WB_PANEL_MODE"] ?? "") ?? .production
    }
}

struct BuildManifest: Decodable {
    let schemaVersion: Int
    let productID: String
    let frontendBuild: String
    let apiProtocol: Int

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case productID = "product_id"
        case frontendBuild = "frontend_build"
        case apiProtocol = "api_protocol"
    }

    func validate() throws {
        guard schemaVersion == 2, productID == panelProductID,
              apiProtocol >= panelAPIProtocol, !frontendBuild.isEmpty else {
            throw NSError(domain: "SummitWorkbench.Manifest", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "build manifest 字段无效"])
        }
    }

    static func load(bundle: Bundle = .main) throws -> BuildManifest {
        guard let url = bundle.url(forResource: "build-manifest", withExtension: "json") else {
            throw NSError(domain: "SummitWorkbench.Manifest", code: 2,
                          userInfo: [NSLocalizedDescriptionKey: "缺少 Resources/build-manifest.json"])
        }
        let manifest = try JSONDecoder().decode(BuildManifest.self, from: Data(contentsOf: url))
        try manifest.validate()
        return manifest
    }
}

struct AppConfiguration {
    let manifest: BuildManifest
    let mode: PanelMode
    let workRoot: String
    let wbBinary: String
    let staticDirectory: String?
    let promptsDirectory: String?

    func panelURL(for frontendBuild: String, port: Int) -> URL {
        var components = URLComponents()
        components.scheme = "http"
        components.host = "127.0.0.1"
        components.port = port
        components.path = "/"
        components.queryItems = [URLQueryItem(name: "build", value: frontendBuild)]
        return components.url!
    }

    var serverArguments: [String] {
        if URL(fileURLWithPath: wbBinary).lastPathComponent == "SummitWorkbenchServer" {
            return ["--host", "127.0.0.1", "--port", "0",
                    "--work-root", workRoot, "--static-dir", staticDirectory ?? ""]
        }
        return ["web", "--host", "127.0.0.1", "--port", "0"]
    }

    static func load() throws -> AppConfiguration {
        let manifest = try BuildManifest.load()
        let environment = ProcessInfo.processInfo.environment
        let workRoot = environment["WORK_ROOT"] ?? (NSHomeDirectory() + "/Documents/Work")
        let resources = Bundle.main.resourceURL
        let bundledServer = resources?.appendingPathComponent("server/SummitWorkbenchServer").path
        let bundledStatic = resources?.appendingPathComponent("web/static").path
        let bundledPrompts = resources?.appendingPathComponent("prompts").path
        guard let wbBinary = environment["WB_SERVER_BINARY"] ?? bundledServer else {
            throw NSError(domain: "SummitWorkbench.Configuration", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "无法定位 bundle server"])
        }
        if PanelMode.current != .developmentExternal,
           !FileManager.default.isExecutableFile(atPath: wbBinary) {
            throw NSError(domain: "SummitWorkbench.Configuration", code: 2,
                          userInfo: [NSLocalizedDescriptionKey: "bundle server 不存在或不可执行：\(wbBinary)"])
        }
        let staticDirectory = environment["WB_STATIC_DIR"] ?? bundledStatic
        let promptsDirectory = environment["WB_PROMPTS_DIR"] ?? bundledPrompts
        return AppConfiguration(manifest: manifest, mode: .current, workRoot: workRoot,
                                wbBinary: wbBinary, staticDirectory: staticDirectory,
                                promptsDirectory: promptsDirectory)
    }
}

struct ServiceIdentity: Decodable {
    let productID: String
    let apiProtocol: Int
    let frontendBuild: String
    let serverVersion: String
    let serverInstance: String
    let startedAt: String
    let mode: String
    let workspaceID: String?
    let deviceID: String?
    let port: Int?

    enum CodingKeys: String, CodingKey {
        case productID = "product_id"
        case apiProtocol = "api_protocol"
        case frontendBuild = "frontend_build"
        case serverVersion = "server_version"
        case serverInstance = "server_instance"
        case startedAt = "started_at"
        case mode
        case workspaceID = "workspace_id"
        case deviceID = "device_id"
        case port
    }

    var isCompatible: Bool {
        productID == panelProductID && apiProtocol >= panelAPIProtocol &&
        !frontendBuild.isEmpty && !serverInstance.isEmpty && (port ?? 0) > 0
    }
}

enum NativeMessage {
    case clientReady(build: String, serverInstance: String)
    case quit
    case copyDiagnostics
    case openLogDirectory
    case openExternal(URL)
    case saveTextFile(filename: String, content: String)
    case automationSettingsChanged(enabled: Bool)

    init?(body: Any) {
        guard let dictionary = body as? [String: Any],
              let type = dictionary["type"] as? String, type.count <= 32 else { return nil }
        switch type {
        case "clientReady":
            guard let build = dictionary["clientBuild"] as? String,
                  let server = dictionary["serverInstance"] as? String,
                  !build.isEmpty, build.count <= 200, !server.isEmpty, server.count <= 200 else { return nil }
            self = .clientReady(build: build, serverInstance: server)
        case "quit": self = .quit
        case "copyDiagnostics": self = .copyDiagnostics
        case "openLogDirectory": self = .openLogDirectory
        case "openExternal":
            guard let raw = dictionary["url"] as? String, raw.count <= 2048,
                  let url = URL(string: raw), ["http", "https"].contains(url.scheme?.lowercased()) else { return nil }
            self = .openExternal(url)
        case "saveTextFile":
            guard let filename = dictionary["filename"] as? String,
                  let content = dictionary["content"] as? String,
                  !filename.isEmpty, filename.count <= 200,
                  !filename.contains("/"), !filename.contains("\\"),
                  content.count <= 2_000_000 else { return nil }
            self = .saveTextFile(filename: filename, content: content)
        case "automationSettingsChanged":
            guard let enabled = dictionary["enabled"] as? Bool else { return nil }
            self = .automationSettingsChanged(enabled: enabled)
        default: return nil
        }
    }
}

enum SupervisorState: String {
    case idle, probing, starting, ready, degraded, restarting, crashLoop, conflict, stopping, stopped
}
