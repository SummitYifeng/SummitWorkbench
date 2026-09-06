import AppKit
import CryptoKit
import Foundation

private final class FakeDefaults: UpdateDefaults {
    var values: [String: Any] = [:]
    func object(forKey defaultName: String) -> Any? { values[defaultName] }
    func string(forKey defaultName: String) -> String? { values[defaultName] as? String }
    func set(_ value: Any?, forKey defaultName: String) { values[defaultName] = value }
}

private final class FakeNetworking: UpdateNetworking {
    var feedData = Data()
    var feedURL = URL(string: "https://updates.example.test/feed.json")!
    var feedResponseURL: URL?
    var feedError: Error?
    var downloadURL: URL?
    var downloadResponseURL = URL(string: "https://updates.example.test/app.dmg")!
    var downloadError: Error?
    var downloadCalls = 0

    func fetch(_ request: URLRequest, completion: @escaping (Data?, URLResponse?, Error?) -> Void) {
        completion(feedData, HTTPURLResponse(url: feedResponseURL ?? feedURL, statusCode: 200,
                                             httpVersion: nil, headerFields: nil), feedError)
    }

    func download(_ url: URL, completion: @escaping (URL?, URLResponse?, Error?) -> Void) {
        downloadCalls += 1
        let response = HTTPURLResponse(url: downloadResponseURL, statusCode: 200,
                                       httpVersion: nil, headerFields: nil)
        completion(downloadURL, response, downloadError)
    }
}

private final class FakeFileSystem: UpdateFileSystem {
    var downloadedData = Data()
    let temporaryURL = URL(fileURLWithPath: "/tmp/fixture.dmg")
    let supportURL = URL(fileURLWithPath: "/tmp/support")
    var createError: Error?
    var moveError: Error?
    var movedTo: URL?

    func data(at url: URL) throws -> Data { downloadedData }
    func applicationSupportDirectory() throws -> URL { supportURL }
    func createDirectory(at url: URL) throws {
        if let createError { throw createError }
    }
    func removeItem(at url: URL) throws {}
    func moveItem(at source: URL, to destination: URL) throws {
        if let moveError { throw moveError }
        movedTo = destination
    }
}

private final class FakeOpener: UpdateAppOpener {
    var opened: [URL] = []
    var result = true
    @discardableResult func open(_ url: URL) -> Bool {
        opened.append(url)
        return result
    }
}

private final class StatusBox {
    var values: [UpdateStatus] = []
}

private enum FixtureError: Error { case interrupted, diskFull }

private func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    let passed = condition()
    if !passed { fputs(message + "\n", stderr) }
    precondition(passed, message)
}

private struct FeedFixture {
    let feed: Data
    let publicKey: String
    let artifactData: Data
    let downloadURL: URL
}

private func fixture(
    version: String = "0.4.2",
    build: String = "108",
    architecture: String = "arm64",
    minimumMacOS: String = "13.0",
    downloadURL: URL = URL(string: "https://updates.example.test/app.dmg")!,
    artifactData: Data = Data("valid-dmg".utf8),
    workspaceSchemaVersion: Int = 2,
    workspaceMinimumReader: String = "0.4.1",
    workspaceMinimumWriter: String = "0.4.1",
    tamperSignature: Bool = false
) throws -> FeedFixture {
    let key = Curve25519.Signing.PrivateKey()
    let digest = SHA256.hash(data: artifactData).map { String(format: "%02x", $0) }.joined()
    let schema = [
        "schema_version": workspaceSchemaVersion,
        "min_reader_version": workspaceMinimumReader,
        "min_writer_version": workspaceMinimumWriter,
    ] as [String: Any]
    var artifact: [String: Any] = [
        "version": version, "build": build, "architecture": architecture,
        "minimum_macos": minimumMacOS, "download_url": downloadURL.absoluteString,
        "sha256": digest, "size": artifactData.count, "release_notes": "fixture",
        "workspace_schema": schema,
    ]
    let fields = [
        panelProductID, version, build, architecture, minimumMacOS, downloadURL.absoluteString,
        digest, String(artifactData.count), "fixture", String(workspaceSchemaVersion),
        workspaceMinimumReader, workspaceMinimumWriter,
    ].joined(separator: "\n")
    var signature = try key.signature(for: Data(fields.utf8)).base64EncodedString()
    if tamperSignature { signature = Data("tampered".utf8).base64EncodedString() }
    artifact["signature"] = signature
    let payload: [String: Any] = [
        "schema_version": 1, "product_id": panelProductID, "artifacts": [artifact],
    ]
    return FeedFixture(
        feed: try JSONSerialization.data(withJSONObject: payload),
        publicKey: key.publicKey.rawRepresentation.base64EncodedString(),
        artifactData: artifactData,
        downloadURL: downloadURL
    )
}

private func makeCoordinator(
    fixture: FeedFixture,
    network: FakeNetworking,
    fileSystem: FakeFileSystem,
    opener: FakeOpener,
    defaults: FakeDefaults = FakeDefaults(),
    decision: @escaping (UpdateArtifactInfo) -> UpdateDecision = { _ in .download },
    workspace: @escaping () -> UpdateWorkspaceCompatibility? = { nil },
    osVersion: OperatingSystemVersion = OperatingSystemVersion(majorVersion: 14, minorVersion: 0, patchVersion: 0),
    statusBox: StatusBox
) -> UpdateCoordinator {
    network.feedData = fixture.feed
    network.downloadURL = fileSystem.temporaryURL
    fileSystem.downloadedData = fixture.artifactData
    return UpdateCoordinator(
        logger: StructuredLogger(appBuild: "test"),
        feedURL: network.feedURL,
        publicKeyBase64: fixture.publicKey,
        currentVersion: "0.4.1",
        currentBuild: "107",
        defaults: defaults,
        networking: network,
        fileSystem: fileSystem,
        appOpener: opener,
        workspaceCompatibility: workspace,
        operatingSystemVersion: osVersion,
        schedule: { $0() },
        prompt: decision,
        statusHandler: { statusBox.values.append($0) }
    )
}

@main
struct UpdateCoordinatorTests {
    static func main() throws {
        let statuses = StatusBox()
        let valid = try fixture()
        let network = FakeNetworking()
        let fileSystem = FakeFileSystem()
        let opener = FakeOpener()
        let coordinator = makeCoordinator(fixture: valid, network: network, fileSystem: fileSystem,
                                          opener: opener, statusBox: statuses)
        coordinator.check(manual: true)
        expect(opener.opened.count == 1, "valid signature, size and hash must open the DMG")
        expect(statuses.values.contains(.available(version: "0.4.2")), "valid update must be reported")

        statuses.values.removeAll()
        let tampered = try fixture(tamperSignature: true)
        let tamperedOpener = FakeOpener()
        let tamperedCoordinator = makeCoordinator(fixture: tampered, network: FakeNetworking(),
                                                   fileSystem: FakeFileSystem(), opener: tamperedOpener,
                                                   statusBox: statuses)
        tamperedCoordinator.check(manual: true)
        expect(tamperedOpener.opened.isEmpty, "tampered signature must not open")
        expect(statuses.values.contains(.current) == false, "tampered signature is not current")

        for bad in [
            try fixture(architecture: "x86_64"),
            try fixture(minimumMacOS: "99.0"),
            try fixture(version: "0.4.0", build: "999"),
            try fixture(workspaceSchemaVersion: 1),
        ] {
            statuses.values.removeAll()
            let badOpener = FakeOpener()
            let badCoordinator = makeCoordinator(
                fixture: bad, network: FakeNetworking(), fileSystem: FakeFileSystem(), opener: badOpener,
                workspace: { UpdateWorkspaceCompatibility(schemaVersion: 2, minimumReaderVersion: "0.4.1", minimumWriterVersion: "0.4.1") },
                statusBox: statuses
            )
            badCoordinator.check(manual: true)
            expect(badOpener.opened.isEmpty, "incompatible candidate must not open")
            expect(statuses.values.contains(.current), "incompatible candidate must report current")
        }

        let redirectNetwork = FakeNetworking()
        redirectNetwork.feedResponseURL = URL(string: "http://updates.example.test/feed.json")!
        statuses.values.removeAll()
        let redirect = makeCoordinator(fixture: valid, network: redirectNetwork,
                                        fileSystem: FakeFileSystem(), opener: FakeOpener(), statusBox: statuses)
        redirect.check(manual: true)
        expect(statuses.values.contains(.failed(code: "http_or_redirect")), "HTTP feed redirect must fail closed")

        for brokenData in [Data("wrong".utf8), Data("valid-dmg-but-different".utf8)] {
            statuses.values.removeAll()
            let brokenFS = FakeFileSystem()
            let brokenNetwork = FakeNetworking()
            let broken = makeCoordinator(fixture: valid, network: brokenNetwork, fileSystem: brokenFS,
                                          opener: FakeOpener(), statusBox: statuses)
            brokenFS.downloadedData = brokenData
            broken.check(manual: true)
            expect(statuses.values.contains(.downloadFailed(code: "download_checksum_mismatch")),
                   "size/hash mismatch must fail closed")
        }

        let interruptedNetwork = FakeNetworking()
        interruptedNetwork.downloadError = FixtureError.interrupted
        statuses.values.removeAll()
        let interrupted = makeCoordinator(fixture: valid, network: interruptedNetwork,
                                          fileSystem: FakeFileSystem(), opener: FakeOpener(), statusBox: statuses)
        interrupted.check(manual: true)
        expect(statuses.values.contains(.downloadFailed(code: "download_failed")), "interrupted download must be retryable")

        for diskFailure in [true, false] {
            statuses.values.removeAll()
            let diskFS = FakeFileSystem()
            if diskFailure { diskFS.createError = FixtureError.diskFull }
            else { diskFS.moveError = FixtureError.diskFull }
            let disk = makeCoordinator(fixture: valid, network: FakeNetworking(), fileSystem: diskFS,
                                       opener: FakeOpener(), statusBox: statuses)
            disk.check(manual: true)
            expect(statuses.values.contains(.downloadFailed(code: "download_failed")), "disk exhaustion must fail closed")
        }

        let laterDefaults = FakeDefaults()
        statuses.values.removeAll()
        let later = makeCoordinator(fixture: valid, network: FakeNetworking(), fileSystem: FakeFileSystem(),
                                    opener: FakeOpener(), defaults: laterDefaults,
                                    decision: { _ in .later }, statusBox: statuses)
        later.check(manual: true)
        expect(laterDefaults.object(forKey: "wb.update.remind-until") != nil, "later must persist reminder")

        let skipDefaults = FakeDefaults()
        let skip = makeCoordinator(fixture: valid, network: FakeNetworking(), fileSystem: FakeFileSystem(),
                                   opener: FakeOpener(), defaults: skipDefaults,
                                   decision: { _ in .skip }, statusBox: statuses)
        skip.check(manual: true)
        expect(skipDefaults.string(forKey: "wb.update.skipped-version") == "0.4.2", "skip must persist version")

        let disabledDefaults = FakeDefaults()
        disabledDefaults.set(false, forKey: "wb.update.auto-check")
        let disabledNetwork = FakeNetworking()
        let disabled = makeCoordinator(fixture: valid, network: disabledNetwork, fileSystem: FakeFileSystem(),
                                       opener: FakeOpener(), defaults: disabledDefaults, statusBox: statuses)
        disabled.checkIfDue()
        expect(disabledNetwork.downloadCalls == 0, "disabled automatic checking must not fetch")

        let retryNetwork = FakeNetworking()
        retryNetwork.downloadError = FixtureError.interrupted
        let retryFS = FakeFileSystem()
        let retryOpener = FakeOpener()
        let retryDefaults = FakeDefaults()
        let retry = makeCoordinator(fixture: valid, network: retryNetwork, fileSystem: retryFS,
                                    opener: retryOpener, defaults: retryDefaults, statusBox: statuses)
        retry.check(manual: true)
        retryNetwork.downloadError = nil
        retry.check(manual: true)
        expect(retryOpener.opened.count == 1, "manual retry after failure must work")

        print("native update coordinator behavior tests passed")
    }
}
