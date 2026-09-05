import Foundation

enum VersionProbeResult {
    case valid(ServiceIdentity)
    case httpError(Int)
    case unavailable
}

final class ServiceClient {
    private(set) var port: Int
    let sessionToken: String

    init(port: Int, sessionToken: String) {
        self.port = port
        self.sessionToken = sessionToken
    }

    func update(port: Int) { self.port = port }

    var baseURL: URL { URL(string: "http://127.0.0.1:\(port)/")! }

    func probe(completion: @escaping (VersionProbeResult) -> Void) {
        var request = URLRequest(url: baseURL.appendingPathComponent("api/version"))
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 1.0
        request.setValue(sessionToken, forHTTPHeaderField: "X-WB-Session-Token")
        URLSession.shared.dataTask(with: request) { data, response, _ in
            guard let http = response as? HTTPURLResponse else {
                DispatchQueue.main.async { completion(.unavailable) }
                return
            }
            guard http.statusCode == 200 else {
                DispatchQueue.main.async { completion(.httpError(http.statusCode)) }
                return
            }
            guard let data, let identity = try? JSONDecoder().decode(ServiceIdentity.self, from: data),
                  identity.isCompatible else {
                DispatchQueue.main.async { completion(.httpError(http.statusCode)) }
                return
            }
            DispatchQueue.main.async { completion(.valid(identity)) }
        }.resume()
    }

    func isReady(completion: @escaping (ServiceIdentity?) -> Void) { probe { result in
        if case .valid(let identity) = result { completion(identity) } else { completion(nil) }
    }}
}
