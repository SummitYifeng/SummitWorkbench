/** 第二大脑（对话式问答）域的类型（从 legacy-main 抽出，Step 1）。 */

export interface AskMsg {
  role: 'user' | 'ai';
  /** user：原文（追问时回传）；ai：服务端渲染的答案 HTML */
  text: string;
  ts: string;
  /** ai 消息本次召回/引用的来源 id（追问时回传，让后端重新纳入候选） */
  sources: string[];
  /** ai 消息实际在事实/冲突中引用的来源；旧会话缺失时回退为空 */
  citedSources?: string[];
}
export interface AskThread {
  id: string;
  title: string;
  createdAt: string;
  messages: AskMsg[];
}
export interface AskHistoryTurn {
  question: string;
  sources: string[];
}
export interface AskResponse {
  ok: boolean;
  message?: string;
  answer_html?: string;
  source_ids?: string[];
  cited_source_ids?: string[];
  answer?: AskAnswer;
}

export interface AskFact {
  text: string;
  source_id: string;
}
export interface AskConflictSide {
  position: string;
  source_id: string;
}
export interface AskConflict {
  topic: string;
  sides: AskConflictSide[];
}
export interface AskAnswer {
  summary: string;
  facts: AskFact[];
  suggestions: string[];
  conflicts: AskConflict[];
  unanswerable: boolean;
}
export interface SourceReadPayload {
  ok: boolean;
  message?: string;
  source_id?: string;
  title?: string;
  date?: string | null;
  body?: string;
  truncated?: boolean;
}
