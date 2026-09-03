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
    let port: Int

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case productID = "product_id"
        case frontendBuild = "frontend_build"
        case port
    }

    func validate() throws {
        guard schemaVersion == 1, productID == panelProductID,
              !frontendBuild.isEmpty, (1...65535).contains(port) else {
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

    var panelURL: URL {
        URL(string: "http://127.0.0.1:\(manifest.port)/?build=\(manifest.frontendBuild)")!
    }

    static func load() throws -> AppConfiguration {
        let manifest = try BuildManifest.load()
        let environment = ProcessInfo.processInfo.environment
        let workRoot = environment["WORK_ROOT"] ?? (NSHomeDirectory() + "/Documents/Work")
        let wbBinary = environment["WB_BIN"] ?? "__WB_BIN__"
        return AppConfiguration(manifest: manifest, mode: .current,
                                workRoot: workRoot, wbBinary: wbBinary)
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

    enum CodingKeys: String, CodingKey {
        case productID = "product_id"
        case apiProtocol = "api_protocol"
        case frontendBuild = "frontend_build"
        case serverVersion = "server_version"
        case serverInstance = "server_instance"
        case startedAt = "started_at"
        case mode
    }

    var isCompatible: Bool {
        productID == panelProductID && apiProtocol >= panelAPIProtocol &&
        !frontendBuild.isEmpty && !serverInstance.isEmpty
    }
}

enum NativeMessage {
    case clientReady(build: String, serverInstance: String)
    case quit
    case copyDiagnostics
    case openExternal(URL)

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
        case "openExternal":
            guard let raw = dictionary["url"] as? String, raw.count <= 2048,
                  let url = URL(string: raw), ["http", "https"].contains(url.scheme?.lowercased()) else { return nil }
            self = .openExternal(url)
        default: return nil
        }
    }
}

enum SupervisorState: String {
    case idle, probing, starting, ready, degraded, restarting, crashLoop, conflict, stopping, stopped
}

