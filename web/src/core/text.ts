/**
 * 长文本提交上限（与后端 Pydantic max_length 一致）。
 *
 * 超出时由 composition root 的 `rejectOversizeText()` 本地拦截并说明原因，
 * 避免直接发送后只得到笼统的 422。
 */
export const MAX_TEXT_CHARS = 100_000;
