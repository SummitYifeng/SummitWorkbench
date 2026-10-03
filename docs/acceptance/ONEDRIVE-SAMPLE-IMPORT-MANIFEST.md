# OneDrive 样板材料清单

日期：2026-10-03  
目标库：`/Users/yifengair/Library/CloudStorage/OneDrive-个人/_vault`  
目标 `workspace_id`：`1d23ee36-0a9b-4255-b6dd-efdebe1d8496`  
来源快照：旧 `_vault` Git HEAD `6afe795280afb84746bcefa9c8910fe05aa71a81`（整理前工作树干净）

## 已选范围

使用者通过选择题选择 A+B+C：项目主页、杭州 1977 酒店、宿心集酒店、三期成本模型、两份来源记录和场地成本决定。酒店谈判清单不在范围内。用户补充的 2026/2027 档期、改造验收及 9 月结算情况单独记作手工来源。

| 旧库相对路径 | 新库相对路径 | 处理方式 |
| --- | --- | --- |
| `projects/huoman-logistics.md` | `projects/huoman-logistics.md` | 按已选事实重写当前状态、下一步、阻塞、成本摘要和排期；删除未选择的谈判清单链接与相关结论 |
| `huoman-logistics/hangzhou-1977-hotel.md` | `huoman-logistics/hangzhou-1977-hotel.md` | 保留旧来源的详细改造记录；明确是 2026-09-14 状态快照，并加入用户确认的逐步验收要求 |
| `huoman-logistics/sources/20260914-hangzhou-1977-hotel-progress.md` | 同路径 | 来源记录副本；省略旧电脑绝对路径，保留原件 SHA-256 前缀用于溯源；副本不是原页字节副本 |
| `huoman-logistics/su-xin-ji-hotel.md` | 同路径 | 更正旧页“无合作线”的历史描述；按用户确认记录双方已有合作细节、2026 年 1/5/9 月使用；具体条款不推断 |
| `huoman-logistics/venue-cost-model.md` | 同路径 | 精简为成本口径、三期历史基准、采购判断三块关键结论；9 月成本不计入已核对历史数据 |
| `huoman-logistics/sources/20260916-hic-venue-cost-review.md` | 同路径 | 来源记录副本；省略旧电脑绝对路径，保留原件 SHA-256 前缀用于溯源；副本不是原页字节副本 |
| `decisions/20260916-venue-per-student-cost-caliber.md` | 同路径 | 保留业务决定及理由；当前版本已由用户批准 |
| 对话确认（2026-10-03） | `huoman-logistics/sources/20261003-user-confirmation.md` | 以 `manual` 来源记录用户确认的酒店关系、使用期次、2027 排期和改造验收要求；不是逐字转录 |
| 用户确认的 2026-09-29 至 2026-10-05 活动 | `artifacts/20261003-september-venue-cost-reconciliation.md` | 建立成本核对草稿；金额、人数留待结算；当前草稿版本已由用户批准，补入结算数据后须重新批准 |

## 排除与状态

- `hotel-negotiation` 清单与其他无关项目内容不导入。
- 两份旧来源页面经过本机路径净化；旧 `_vault` 未编辑，旧 Git 历史未改写。
- 用户于 2026-10-03 批准六份正式内容的当前版本：项目主页、两家酒店页、成本模型、成本口径决定和 9 月成本核对草稿。各页均有当前内容匹配的 `approval` 证明；后续内容变更必须重新批准。
- 原件页面保持 `type: source`，不进入检索语料。
- 链接与区块检查：`wb vault check` 通过 11 篇；`kb_verify_links.py` 通过 37 条双链。2026-10-03 用户另行确认 OneDrive 客户端已完成同步；两台 Mac 的往返同步尚未验收。
