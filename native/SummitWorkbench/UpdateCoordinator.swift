import AppKit
import CryptoKit
import Foundation

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

    enum CodingKeys: String, CodingKey {
        case version, build, architecture
        case minimumMacOS = "minimum_macos"
        case downloadURL = "download_url"
        case sha256, size
        case releaseNotes = "release_notes"
        case signature
    }
}

/// P1-07 的安全更新入口：只检查和打开已验证下载地址，不自动写入 vault 或安装 App。
final class UpdateCoordinator {
    private let logger: StructuredLogger
    private let feedURL: URL?
    private let publicKey: Curve25519.Signing.PublicKey?
    private let currentVersion: String
    private let currentBuild: Int
    private let architecture: String
    private let defaults: UserDefaults
    private let now: () -> Date

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
        defaults: UserDefaults = .standard,
        now: @escaping () -> Date = Date.init
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
        self.now = now
    }

    func checkIfDue() {
        guard defaults.object(forKey: autoCheckKey) as? Bool ?? true else { return }
        if let last = defaults.object(forKey: lastCheckKey) as? Date,
           now().timeIntervalSince(last) < 24 * 60 * 60 { return }
        check(manual: false)
    }

    func check(manual: Bool) {
        guard let feedURL else {
            if manual { logger.log("update_check_unavailable", fields: ["reason": "feed_not_configured"]) }
            return
        }
        guard feedURL.scheme?.lowercased() == "https" else {
            logger.log("update_feed_rejected", level: "error", fields: ["error_code": "insecure_feed_url"])
            return
        }
        defaults.set(now(), forKey: lastCheckKey)
        logger.log("update_check_started", fields: ["manual": manual ? "true" : "false"])
        URLSession.shared.dataTask(with: URLRequest(url: feedURL, cachePolicy: .reloadIgnoringLocalCacheData)) {
            [weak self] data, response, error in
            DispatchQueue.main.async {
                guard let self else { return }
                if let error {
                    self.logger.log("update_check_failed", level: "error", fields: ["error_code": "network", "message": error.localizedDescription])
                    return
                }
                guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode), let data else {
                    self.logger.log("update_check_failed", level: "error", fields: ["error_code": "http"])
                    return
                }
                self.consume(data: data, manual: manual)
            }
        }.resume()
    }

    private func consume(data: Data, manual: Bool) {
        do {
            let feed = try JSONDecoder().decode(UpdateFeed.self, from: data)
            guard feed.schemaVersion == 1, feed.productID == panelProductID else { throw UpdateError.invalidFeed }
            guard let artifact = compatibleArtifact(feed.artifacts) else {
                if manual { logger.log("update_check_current", fields: ["reason": "no_compatible_update"]) }
                return
            }
            guard verify(artifact) else { throw UpdateError.invalidSignature }
            guard let url = URL(string: artifact.downloadURL), url.scheme?.lowercased() == "https" else {
                throw UpdateError.invalidDownloadURL
            }
            logger.log("update_available", fields: ["version": artifact.version, "build": artifact.build])
            guard shouldPresent(version: artifact.version) else { return }
            present(artifact: artifact, url: url)
        } catch let error as UpdateError {
            logger.log("update_feed_rejected", level: "error", fields: ["error_code": error.rawValue])
        } catch {
            logger.log("update_feed_rejected", level: "error", fields: ["error_code": "invalid_json"])
        }
    }

    private func compatibleArtifact(_ artifacts: [UpdateArtifact]) -> UpdateArtifact? {
        let system = ProcessInfo.processInfo.operatingSystemVersion
        let currentOS = [system.majorVersion, system.minorVersion, system.patchVersion]
        return artifacts.filter { artifact in
            guard artifact.architecture == architecture,
                  let build = Int(artifact.build), build > currentBuild,
                  isVersion(artifact.version), isVersion(artifact.minimumMacOS),
                  isAtLeast(currentOS, versionParts(artifact.minimumMacOS)),
                  isAtLeast(versionParts(artifact.version), currentVersionParts),
                  artifact.size > 0, isSHA256(artifact.sha256),
                  !artifact.signature.isEmpty else { return false }
            return artifact.downloadURL.hasPrefix("https://")
        }.max { left, right in
            let leftVersion = versionParts(left.version)
            let rightVersion = versionParts(right.version)
            if leftVersion != rightVersion { return isAtLeast(rightVersion, leftVersion) }
            return (Int(left.build) ?? 0) < (Int(right.build) ?? 0)
        }
    }

    private func verify(_ artifact: UpdateArtifact) -> Bool {
        guard let publicKey, let signature = Data(base64Encoded: artifact.signature) else { return false }
        let fields = [
            panelProductID, artifact.version, artifact.build, artifact.architecture,
            artifact.minimumMacOS, artifact.downloadURL, artifact.sha256,
            String(artifact.size), artifact.releaseNotes,
        ].joined(separator: "\n")
        return publicKey.isValidSignature(signature, for: Data(fields.utf8))
    }

    private func shouldPresent(version: String) -> Bool {
        if defaults.string(forKey: skippedVersionKey) == version { return false }
        if let until = defaults.object(forKey: remindUntilKey) as? Date, until > now() { return false }
        return true
    }

    private func present(artifact: UpdateArtifact, url: URL) {
        let alert = NSAlert()
        alert.alertStyle = .informational
        alert.messageText = "SummitWorkbench 有可用更新 \(artifact.version)"
        alert.informativeText = artifact.releaseNotes.isEmpty ? "更新已通过签名和本机架构检查。" : artifact.releaseNotes
        alert.addButton(withTitle: "下载并打开")
        alert.addButton(withTitle: "稍后提醒")
        alert.addButton(withTitle: "跳过此版本")
        switch alert.runModal() {
        case .alertFirstButtonReturn:
            downloadAndOpen(artifact: artifact, url: url)
        case .alertSecondButtonReturn:
            defaults.set(now().addingTimeInterval(24 * 60 * 60), forKey: remindUntilKey)
            logger.log("update_reminded_later", fields: ["version": artifact.version])
        default:
            defaults.set(artifact.version, forKey: skippedVersionKey)
            logger.log("update_skipped", fields: ["version": artifact.version])
        }
    }

    private func downloadAndOpen(artifact: UpdateArtifact, url: URL) {
        logger.log("update_download_started", fields: ["version": artifact.version])
        URLSession.shared.downloadTask(with: url) { [weak self] temporaryURL, _, error in
            DispatchQueue.main.async {
                guard let self else { return }
                do {
                    if let error { throw error }
                    guard let temporaryURL else { throw UpdateError.downloadFailed }
                    let data = try Data(contentsOf: temporaryURL)
                    guard data.count == artifact.size, self.sha256Hex(data) == artifact.sha256 else {
                        throw UpdateError.downloadChecksumMismatch
                    }
                    let directory = try FileManager.default.url(
                        for: .applicationSupportDirectory,
                        in: .userDomainMask,
                        appropriateFor: nil,
                        create: true
                    ).appendingPathComponent("SummitWorkbench/updates", isDirectory: true)
                    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                    let destination = directory.appendingPathComponent(
                        "SummitWorkbench-\(artifact.version)-\(artifact.build).dmg"
                    )
                    try? FileManager.default.removeItem(at: destination)
                    try FileManager.default.moveItem(at: temporaryURL, to: destination)
                    NSWorkspace.shared.open(destination)
                    self.logger.log("update_download_verified", fields: ["version": artifact.version])
                } catch let error as UpdateError {
                    self.logger.log("update_download_failed", level: "error", fields: ["error_code": error.rawValue])
                } catch {
                    self.logger.log("update_download_failed", level: "error", fields: ["error_code": "download_failed"])
                }
            }
        }.resume()
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
}

private enum UpdateError: String, Error {
    case invalidFeed = "invalid_feed"
    case invalidSignature = "invalid_signature"
    case invalidDownloadURL = "invalid_download_url"
    case downloadFailed = "download_failed"
    case downloadChecksumMismatch = "download_checksum_mismatch"
}
