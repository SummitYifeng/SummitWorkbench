import AppKit
import CryptoKit
import Foundation

protocol UpdateNetworking {
    func fetch(_ request: URLRequest, completion: @escaping (Data?, URLResponse?, Error?) -> Void)
    func download(_ url: URL, completion: @escaping (URL?, URLResponse?, Error?) -> Void)
}

final class URLSessionUpdateNetworking: UpdateNetworking {
    func fetch(_ request: URLRequest, completion: @escaping (Data?, URLResponse?, Error?) -> Void) {
        URLSession.shared.dataTask(with: request, completionHandler: completion).resume()
    }

    func download(_ url: URL, completion: @escaping (URL?, URLResponse?, Error?) -> Void) {
        URLSession.shared.downloadTask(with: url) { temporaryURL, response, error in
            completion(temporaryURL, response, error)
        }.resume()
    }
}

protocol UpdateFileSystem {
    func data(at url: URL) throws -> Data
    func applicationSupportDirectory() throws -> URL
    func createDirectory(at url: URL) throws
    func removeItem(at url: URL) throws
    func moveItem(at source: URL, to destination: URL) throws
}

final class LocalUpdateFileSystem: UpdateFileSystem {
    private let fileManager = FileManager.default

    func data(at url: URL) throws -> Data { try Data(contentsOf: url) }

    func applicationSupportDirectory() throws -> URL {
        try fileManager.url(for: .applicationSupportDirectory, in: .userDomainMask,
                            appropriateFor: nil, create: true)
    }

    func createDirectory(at url: URL) throws {
        try fileManager.createDirectory(at: url, withIntermediateDirectories: true)
    }

    func removeItem(at url: URL) throws { try fileManager.removeItem(at: url) }

    func moveItem(at source: URL, to destination: URL) throws {
        try fileManager.moveItem(at: source, to: destination)
    }
}

protocol UpdateDefaults {
    func object(forKey defaultName: String) -> Any?
    func string(forKey defaultName: String) -> String?
    func set(_ value: Any?, forKey defaultName: String)
}

extension UserDefaults: UpdateDefaults {}

protocol UpdateAppOpener {
    @discardableResult func open(_ url: URL) -> Bool
}

final class WorkspaceUpdateAppOpener: UpdateAppOpener {
    @discardableResult func open(_ destination: URL) -> Bool { NSWorkspace.shared.open(destination) }
}

enum UpdateDecision { case download, later, skip }

enum UpdateStatus: Equatable {
    case checking
    case unavailable
    case current
    case available(version: String)
    case failed(code: String)
    case downloadFailed(code: String)
}

private struct UpdateFeed: Decodable {
    let schemaVersion: Int
    let productID: String
    let artifacts: [UpdateArtifact]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case productID = "product_id"
        case artifacts
    }
}

private struct UpdateWorkspaceSchema: Decodable {
    let schemaVersion: Int
    let minimumReaderVersion: String
    let minimumWriterVersion: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case minimumReaderVersion = "min_reader_version"
        case minimumWriterVersion = "min_writer_version"
    }
}

struct UpdateArtifactInfo {
    let version: String
    let build: String
    let releaseNotes: String
}

private struct UpdateArtifact: Decodable {
    let version: String
    let build: String
    let architecture: String
    let minimumMacOS: String
    let downloadURL: String
    let sha256: String
    let size: Int
    let releaseNotes: String
    let signature: String
    let workspaceSchema: UpdateWorkspaceSchema?

    enum CodingKeys: String, CodingKey {
        case version, build, architecture
        case minimumMacOS = "minimum_macos"
        case downloadURL = "download_url"
        case sha256, size
        case releaseNotes = "release_notes"
        case signature
        case workspaceSchema = "workspace_schema"
    }

    var info: UpdateArtifactInfo {
        UpdateArtifactInfo(version: version, build: build, releaseNotes: releaseNotes)
    }
}

/// P1-07C 的安全更新入口：所有外部依赖可替换，下载只会落到本机临时更新目录，
/// 不会自动替换 App、写入 vault/profile 或发布 partial latest。
final class UpdateCoordinator {
    private let logger: StructuredLogger
    private let feedURL: URL?
    private let publicKey: Curve25519.Signing.PublicKey?
    private let currentVersion: String
    private let currentBuild: Int
    private let architecture: String
    private let defaults: UpdateDefaults
    private let networking: UpdateNetworking
    private let fileSystem: UpdateFileSystem
    private let appOpener: UpdateAppOpener
    private let workspaceCompatibility: () -> UpdateWorkspaceCompatibility?
    private let operatingSystemVersion: OperatingSystemVersion
    private let now: () -> Date
    private let schedule: (@escaping () -> Void) -> Void
    private let prompt: (UpdateArtifactInfo) -> UpdateDecision
    var statusHandler: (UpdateStatus) -> Void

    private let lastCheckKey = "wb.update.last-check-at"
    private let skippedVersionKey = "wb.update.skipped-version"
    private let remindUntilKey = "wb.update.remind-until"
    private let autoCheckKey = "wb.update.auto-check"

    init(
        logger: StructuredLogger,
        feedURL: URL?,
        publicKeyBase64: String?,
        currentVersion: String,
        currentBuild: String,
        architecture: String = "arm64",
        defaults: UpdateDefaults = UserDefaults.standard,
        networking: UpdateNetworking = URLSessionUpdateNetworking(),
        fileSystem: UpdateFileSystem = LocalUpdateFileSystem(),
        appOpener: UpdateAppOpener = WorkspaceUpdateAppOpener(),
        workspaceCompatibility: @escaping () -> UpdateWorkspaceCompatibility? = { nil },
        operatingSystemVersion: OperatingSystemVersion = ProcessInfo.processInfo.operatingSystemVersion,
        now: @escaping () -> Date = Date.init,
        schedule: @escaping (@escaping () -> Void) -> Void = { work in DispatchQueue.main.async(execute: work) },
        prompt: @escaping (UpdateArtifactInfo) -> UpdateDecision = UpdateCoordinator.defaultPrompt,
        statusHandler: @escaping (UpdateStatus) -> Void = { _ in }
    ) {
        self.logger = logger
        self.feedURL = feedURL
        if let raw = publicKeyBase64, let data = Data(base64Encoded: raw) {
            self.publicKey = try? Curve25519.Signing.PublicKey(rawRepresentation: data)
        } else {
            self.publicKey = nil
        }
        self.currentVersion = currentVersion
        self.currentBuild = Int(currentBuild) ?? 0
        self.architecture = architecture
        self.defaults = defaults
        self.networking = networking
        self.fileSystem = fileSystem
        self.appOpener = appOpener
        self.workspaceCompatibility = workspaceCompatibility
        self.operatingSystemVersion = operatingSystemVersion
        self.now = now
        self.schedule = schedule
        self.prompt = prompt
        self.statusHandler = statusHandler
    }

    func checkIfDue() {
        guard defaults.object(forKey: autoCheckKey) as? Bool ?? true else { return }
        if let last = defaults.object(forKey: lastCheckKey) as? Date,
           now().timeIntervalSince(last) < 24 * 60 * 60 { return }
        check(manual: false)
    }

    func setAutomaticChecksEnabled(_ enabled: Bool) {
        defaults.set(enabled, forKey: autoCheckKey)
        logger.log("update_auto_check_changed", fields: ["enabled": enabled ? "true" : "false"])
    }

    func check(manual: Bool) {
        guard let feedURL else {
            if manual {
                logger.log("update_check_unavailable", fields: ["reason": "feed_not_configured"])
                statusHandler(.unavailable)
            }
            return
        }
        guard feedURL.scheme?.lowercased() == "https" else {
            fail(.failed(code: UpdateError.insecureFeedURL.rawValue), event: "update_feed_rejected")
            return
        }
        defaults.set(now(), forKey: lastCheckKey)
        statusHandler(.checking)
        logger.log("update_check_started", fields: ["manual": manual ? "true" : "false"])
        let request = URLRequest(url: feedURL, cachePolicy: .reloadIgnoringLocalCacheData)
        networking.fetch(request) { [weak self] data, response, error in
            guard let self else { return }
            self.schedule {
                if let error {
                    self.fail(.failed(code: UpdateError.network.rawValue), event: "update_check_failed",
                              message: error.localizedDescription)
                    return
                }
                guard let http = response as? HTTPURLResponse,
                      (200..<300).contains(http.statusCode),
                      http.url?.scheme?.lowercased() == "https",
                      let data else {
                    self.fail(.failed(code: UpdateError.httpOrRedirect.rawValue), event: "update_check_failed")
                    return
                }
                self.consume(data: data, manual: manual)
            }
        }
    }

    private func consume(data: Data, manual: Bool) {
        do {
            let feed = try JSONDecoder().decode(UpdateFeed.self, from: data)
            guard feed.schemaVersion == 1, feed.productID == panelProductID else {
                throw UpdateError.invalidFeed
            }
            guard let artifact = compatibleArtifact(feed.artifacts) else {
                if manual {
                    logger.log("update_check_current", fields: ["reason": "no_compatible_update"])
                    statusHandler(.current)
                }
                return
            }
            guard verify(artifact) else { throw UpdateError.invalidSignature }
            guard let url = URL(string: artifact.downloadURL),
                  url.scheme?.lowercased() == "https" else {
                throw UpdateError.invalidDownloadURL
            }
            statusHandler(.available(version: artifact.version))
            logger.log("update_available", fields: ["version": artifact.version, "build": artifact.build])
            guard shouldPresent(version: artifact.version) else { return }
            switch prompt(artifact.info) {
            case .download: downloadAndOpen(artifact: artifact, url: url)
            case .later:
                defaults.set(now().addingTimeInterval(24 * 60 * 60), forKey: remindUntilKey)
                logger.log("update_reminded_later", fields: ["version": artifact.version])
            case .skip:
                defaults.set(artifact.version, forKey: skippedVersionKey)
                logger.log("update_skipped", fields: ["version": artifact.version])
            }
        } catch let error as UpdateError {
            fail(.failed(code: error.rawValue), event: "update_feed_rejected")
        } catch {
            fail(.failed(code: UpdateError.invalidJSON.rawValue), event: "update_feed_rejected")
        }
    }

    private func compatibleArtifact(_ artifacts: [UpdateArtifact]) -> UpdateArtifact? {
        let currentOS = [operatingSystemVersion.majorVersion, operatingSystemVersion.minorVersion,
                         operatingSystemVersion.patchVersion]
        return artifacts.filter { artifact in
            guard artifact.architecture == architecture,
                  let build = Int(artifact.build), build > currentBuild,
                  isVersion(artifact.version), isVersion(artifact.minimumMacOS),
                  isAtLeast(currentOS, versionParts(artifact.minimumMacOS)),
                  isAtLeast(versionParts(artifact.version), currentVersionParts),
                  artifact.size > 0, isSHA256(artifact.sha256),
                  !artifact.signature.isEmpty,
                  workspaceIsCompatible(artifact.workspaceSchema, targetVersion: artifact.version) else { return false }
            return URL(string: artifact.downloadURL)?.scheme?.lowercased() == "https"
        }.max { left, right in
            let leftVersion = versionParts(left.version)
            let rightVersion = versionParts(right.version)
            if leftVersion != rightVersion { return isAtLeast(rightVersion, leftVersion) }
            return (Int(left.build) ?? 0) < (Int(right.build) ?? 0)
        }
    }

    private func workspaceIsCompatible(_ target: UpdateWorkspaceSchema?, targetVersion: String) -> Bool {
        guard let current = workspaceCompatibility() else { return true }
        guard let target else { return false }
        guard target.schemaVersion >= current.schemaVersion,
              isVersion(target.minimumReaderVersion), isVersion(target.minimumWriterVersion) else {
            return false
        }
        // 升级后的 App 必须能继续读写当前 workspace；不能把设备升级到只读/不可打开状态。
        return isAtLeast(versionParts(targetVersion), versionParts(current.minimumReaderVersion)) &&
            isAtLeast(versionParts(targetVersion), versionParts(current.minimumWriterVersion)) &&
            isAtLeast(versionParts(targetVersion), versionParts(target.minimumReaderVersion)) &&
            isAtLeast(versionParts(targetVersion), versionParts(target.minimumWriterVersion))
    }

    private func verify(_ artifact: UpdateArtifact) -> Bool {
        guard let publicKey, let signature = Data(base64Encoded: artifact.signature) else { return false }
        var fields = [
            panelProductID, artifact.version, artifact.build, artifact.architecture,
            artifact.minimumMacOS, artifact.downloadURL, artifact.sha256,
            String(artifact.size), artifact.releaseNotes,
        ]
        if let schema = artifact.workspaceSchema {
            fields += [String(schema.schemaVersion), schema.minimumReaderVersion, schema.minimumWriterVersion]
        }
        return publicKey.isValidSignature(signature, for: Data(fields.joined(separator: "\n").utf8))
    }

    private func shouldPresent(version: String) -> Bool {
        if defaults.string(forKey: skippedVersionKey) == version { return false }
        if let until = defaults.object(forKey: remindUntilKey) as? Date, until > now() { return false }
        return true
    }

    private func downloadAndOpen(artifact: UpdateArtifact, url: URL) {
        logger.log("update_download_started", fields: ["version": artifact.version])
        networking.download(url) { [weak self] temporaryURL, response, error in
            guard let self else { return }
            self.schedule {
                do {
                    if let error { throw UpdateError.downloadFailedUnderlying(error.localizedDescription) }
                    guard let temporaryURL,
                          (response as? HTTPURLResponse)?.url?.scheme?.lowercased() == "https" else {
                        throw UpdateError.httpOrRedirect
                    }
                    let data = try self.fileSystem.data(at: temporaryURL)
                    guard data.count == artifact.size, self.sha256Hex(data) == artifact.sha256 else {
                        throw UpdateError.downloadChecksumMismatch
                    }
                    let directory = try self.fileSystem.applicationSupportDirectory()
                        .appendingPathComponent("SummitWorkbench/updates", isDirectory: true)
                    try self.fileSystem.createDirectory(at: directory)
                    let destination = directory.appendingPathComponent(
                        "SummitWorkbench-\(artifact.version)-\(artifact.build).dmg"
                    )
                    try? self.fileSystem.removeItem(at: destination)
                    try self.fileSystem.moveItem(at: temporaryURL, to: destination)
                    guard self.appOpener.open(destination) else { throw UpdateError.openFailed }
                    self.statusHandler(.available(version: artifact.version))
                    self.logger.log("update_download_verified", fields: ["version": artifact.version])
                } catch let error as UpdateError {
                    self.fail(.downloadFailed(code: error.rawValue), event: "update_download_failed")
                } catch {
                    self.fail(.downloadFailed(code: UpdateError.downloadFailed.rawValue), event: "update_download_failed")
                }
            }
        }
    }

    private func fail(_ status: UpdateStatus, event: String, message: String? = nil) {
        statusHandler(status)
        var fields = ["error_code": status.errorCode]
        if let message { fields["message"] = message }
        logger.log(event, level: "error", fields: fields)
    }

    private func sha256Hex(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private var currentVersionParts: [Int] { versionParts(currentVersion) }

    private func isAtLeast(_ left: [Int], _ right: [Int]) -> Bool {
        for (leftPart, rightPart) in zip(left, right) {
            if leftPart != rightPart { return leftPart > rightPart }
        }
        return true
    }

    private func versionParts(_ value: String) -> [Int] {
        let formal = value.split(separator: "-", maxSplits: 1).first?.split(separator: "+", maxSplits: 1).first ?? "0"
        return Array((formal.split(separator: ".").compactMap { Int($0) } + [0, 0, 0]).prefix(3))
    }

    private func isVersion(_ value: String) -> Bool {
        let formal = value.split(separator: "-", maxSplits: 1).first?.split(separator: "+", maxSplits: 1).first ?? ""
        return !formal.isEmpty && formal.split(separator: ".").allSatisfy { Int($0) != nil }
    }

    private func isSHA256(_ value: String) -> Bool {
        value.count == 64 && value.allSatisfy { $0.isHexDigit && ($0.isNumber || $0.isLowercase) }
    }

    private static func defaultPrompt(_ artifact: UpdateArtifactInfo) -> UpdateDecision {
        let alert = NSAlert()
        alert.alertStyle = .informational
        alert.messageText = "SummitWorkbench 有可用更新 \(artifact.version)"
        alert.informativeText = artifact.releaseNotes.isEmpty ? "更新已通过签名和本机架构检查。" : artifact.releaseNotes
        alert.addButton(withTitle: "下载并打开")
        alert.addButton(withTitle: "稍后提醒")
        alert.addButton(withTitle: "跳过此版本")
        switch alert.runModal() {
        case .alertFirstButtonReturn: return .download
        case .alertSecondButtonReturn: return .later
        default: return .skip
        }
    }
}

private extension UpdateStatus {
    var errorCode: String {
        switch self {
        case .failed(let code), .downloadFailed(let code): return code
        default: return ""
        }
    }
}

private enum UpdateError: Error {
    case invalidFeed, invalidJSON, invalidSignature, invalidDownloadURL
    case insecureFeedURL, network, httpOrRedirect, downloadFailed
    case downloadFailedUnderlying(String), downloadChecksumMismatch, openFailed

    var rawValue: String {
        switch self {
        case .invalidFeed: return "invalid_feed"
        case .invalidJSON: return "invalid_json"
        case .invalidSignature: return "invalid_signature"
        case .invalidDownloadURL: return "invalid_download_url"
        case .insecureFeedURL: return "insecure_feed_url"
        case .network: return "network"
        case .httpOrRedirect: return "http_or_redirect"
        case .downloadFailed, .downloadFailedUnderlying: return "download_failed"
        case .downloadChecksumMismatch: return "download_checksum_mismatch"
        case .openFailed: return "open_failed"
        }
    }
}
