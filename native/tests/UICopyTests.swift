import Foundation

private func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    let passed = condition()
    if !passed { fputs(message + "\n", stderr) }
    precondition(passed, message)
}

/// 「给使用者看的文案」的功能单测。
///
/// 为什么必须有它：这些是**短中文字面量**，Swift 的 small-string 优化会把它们内联进代码，
/// 二进制里搜不到（见 `UICopy.swift` 的注释）⇒ 二进制取证这条路走不通，只能在这里守。
///
/// 覆盖两个真出过的问题：
/// - 更新提示曾写成 `"发现可用更新 (version)"`，版本号丢失；
/// - 服务状态曾直接插 `SupervisorState.rawValue`，把 `crashLoop` 给使用者看。
@main
struct UICopyTests {
    static func main() {
        // ---- 更新提示：必须带实际版本号 ----
        expect(UICopy.updateAvailable(version: "0.5.0") == "发现可用更新：0.5.0",
               "更新提示必须带上实际版本号")
        expect(!UICopy.updateAvailable(version: "0.5.0").contains("(version)"),
               "不许把 `(version)` 当字面量打出来")
        expect(UICopy.updateAvailable(version: "0.5.0-alpha.1") == "发现可用更新：0.5.0-alpha.1",
               "预发布版本号要原样保留")
        expect(UICopy.updateAvailable(version: "  0.5.1  ") == "发现可用更新：0.5.1",
               "版本号两侧空白要剥掉")
        expect(UICopy.updateAvailable(version: "") == "发现可用更新",
               "版本号为空时退化成短句，不留一个空冒号")
        expect(UICopy.updateAvailable(version: "   ") == "发现可用更新",
               "只有空白的版本号同样退化")

        // ---- 服务状态：十个状态（含 nil）都要有中文名，且不能是 rawValue ----
        let expected: [(SupervisorState?, String)] = [
            (.idle, "空闲"), (.probing, "正在探测服务"), (.starting, "正在启动"),
            (.ready, "已就绪"), (.degraded, "降级运行"), (.restarting, "正在重启"),
            (.crashLoop, "反复启动失败"), (.conflict, "端口被占用"),
            (.stopping, "正在停止"), (.stopped, "已停止"), (nil, "未知"),
        ]
        for (state, want) in expected {
            let got = UICopy.supervisorState(state)
            expect(got == want, "状态 \(state.map { $0.rawValue } ?? "nil") 的中文名应为「\(want)」，实际「\(got)」")
            // 中文名里不能出现 rawValue（`crashLoop` 这种内部标识）
            if let raw = state?.rawValue {
                expect(!got.contains(raw), "状态 \(raw) 的中文名泄漏了 rawValue：\(got)")
            }
            expect(got.contains(where: { $0.unicodeScalars.contains { $0.value >= 0x4E00 && $0.value <= 0x9FFF } }),
                   "状态 \(state.map { $0.rawValue } ?? "nil") 的中文名没有中文：\(got)")
        }

        // ---- 其余更新文案：非空且是中文 ----
        for copy in [UICopy.updateChecking, UICopy.updateUnavailable, UICopy.updateCurrent,
                     UICopy.updateFailed, UICopy.updateDownloadFailed] {
            expect(!copy.isEmpty, "更新文案不能为空")
            expect(copy.contains(where: { $0.unicodeScalars.contains { $0.value >= 0x4E00 && $0.value <= 0x9FFF } }),
                   "更新文案应为中文：\(copy)")
        }

        print("native UI copy tests passed")
    }
}
