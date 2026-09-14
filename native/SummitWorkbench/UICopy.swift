import Foundation

/// 面向使用者的界面文案（纯函数集中一处，便于 `scripts/test-native-automation.sh` 单测）。
///
/// 为什么单独成文件：
/// 1. 这两处文案都真出过错——更新提示写成 `"发现可用更新 (version)"`（`(version)` 是字面量，
///    实际版本号压根没显示）；服务状态直接插 `SupervisorState.rawValue`（使用者看到
///    「状态：crashLoop」这种内部标识）。
/// 2. 它们基本都是**短中文字面量（≤15 UTF-8 字节）**，Swift 会做 small-string 优化
///    **内联进代码而不是放进数据段** ⇒ `strings` / 原始字节搜索**都查不到**
///    （用同样存在于代码里的「关闭」「确定」「取消」校准过：0 命中；而 18 字节的
///    「复制诊断信息」能查到）。所以这类文案**只能靠功能单测守**，不能靠二进制取证。
enum UICopy {
    static let updateChecking = "正在检查更新…"
    static let updateUnavailable = "更新源未配置"
    static let updateCurrent = "当前已是最新版本"
    static let updateFailed = "更新检查失败，可重试"
    static let updateDownloadFailed = "更新下载失败，可重试"

    /// 「发现可用更新」：必须带上实际版本号；版本号为空时退化成不带冒号的短句。
    static func updateAvailable(version: String) -> String {
        let trimmed = version.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "发现可用更新" : "发现可用更新：\(trimmed)"
    }

    /// 服务状态的中文名。
    ///
    /// `SupervisorState.rawValue` 是内部标识（`crashLoop` / `degraded`…），
    /// **不进给使用者看的弹窗**（2026-09-14 原生壳文案扫描发现这里直接贴了 rawValue）。
    static func supervisorState(_ state: SupervisorState?) -> String {
        switch state {
        case .idle: return "空闲"
        case .probing: return "正在探测服务"
        case .starting: return "正在启动"
        case .ready: return "已就绪"
        case .degraded: return "降级运行"
        case .restarting: return "正在重启"
        case .crashLoop: return "反复启动失败"
        case .conflict: return "端口被占用"
        case .stopping: return "正在停止"
        case .stopped: return "已停止"
        case nil: return "未知"
        }
    }
}
