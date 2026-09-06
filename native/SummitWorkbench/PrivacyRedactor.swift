import Foundation

enum PrivacyRedactor {
    static func text(_ value: String) -> String {
        var result = value
        result = replace(result, pattern: #"(?i)(authorization|cookie|set-cookie|x-wb-session-token)\s*[:=]\s*[^,\n]+"#, with: "$1: [redacted]")
        result = replace(result, pattern: #"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"#, with: "Bearer [redacted]")
        result = replace(result, pattern: #"(?i)(https?://)[^/\s:@]+:[^@\s]+@"#, with: "$1[redacted]@")
        result = replace(result, pattern: #"(?i)\b(?:canary[-_][a-z0-9_-]+|(?:secret|token|pat|api[_-]?key)=[^\s,;]+)\b"#, with: "[redacted]")
        result = replace(result, pattern: #"(?is)\b(?:meeting|transcript|prompt|model response)\s+body\s*[:=]\s*[^\n]+"#, with: "[redacted body]")
        return replace(result, pattern: #"/Users/[^/\s]+(?:/[^\s]*)?"#, with: "~/[redacted]")
    }

    static func fields(_ fields: [String: String]) -> [String: String] {
        fields.reduce(into: [String: String]()) { result, entry in
            let key = entry.key.lowercased()
            if ["secret", "token", "password", "authorization", "cookie", "credential",
                "api_key", "api-key", "prompt", "response", "body"].contains(where: key.contains) {
                result[entry.key] = "[redacted]"
            } else {
                result[entry.key] = text(entry.value)
            }
        }
    }

    private static func replace(_ value: String, pattern: String, with replacement: String) -> String {
        guard let expression = try? NSRegularExpression(pattern: pattern) else { return value }
        let range = NSRange(value.startIndex..<value.endIndex, in: value)
        return expression.stringByReplacingMatches(in: value, range: range, withTemplate: replacement)
    }
}
