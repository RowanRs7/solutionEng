---
title: MCP、单 Agent 与多 Agent 的边界
slug: mcp-and-single-vs-multi-agent
module: ai-solutions
stage: design
type: core
difficulty: intermediate
duration: 55m
prerequisites:
  - session-and-memory
outcomes:
  - 说明 MCP 中 host、client、server 的职责与工具发现调用流程
  - 判断一次集成该用 MCP、内部函数调用还是人工流程
  - 用成本、隔离性与错误传播三个维度评估多 Agent 方案
last_reviewed: 2026-10-19
---

# MCP、单 Agent 与多 Agent 的边界

## 为什么需要学习

晴空商城的售后助手需要接入三类系统：订单（自建）、物流（第三方）、发票（财务 SaaS）。第一次接模型时，团队为每个系统手写了工具定义与适配代码；换模型供应商时，三套代码几乎重写了一遍。与此同时，另一个团队为了“更专业”，把售后拆成订单 agent、政策 agent、金额 agent、审批 agent、回复 agent 五个角色，结果单次会话的模型调用从 3 次涨到 12 次，错误还会在角色之间传递。

两件事常被混为一谈：*MCP*（Model Context Protocol，模型上下文协议）解决“工具怎么被标准化地发现与调用”；*单 Agent 还是多 Agent* 解决“由几个决策者分工”。前者是接口问题，后者是架构问题。

> **核心结论：** MCP 降低集成的重复劳动，但不降低自主性风险；多 Agent 增加的是并行能力，代价是上下文重复与错误传播。

## 学习目标

完成本课后，你能够：

- 画出一次 MCP 交互的报文序列：初始化、工具列举、工具调用、结果返回。
- 判断一个集成场景该用 MCP 服务器、应用内函数还是保留人工操作。
- 用三个维度评估多 Agent 方案是否值得，并说明替代方案。
- 指出接入第三方 MCP 服务器时的信任边界与叠加风险。

## 前置知识

- 回看上一课：[会话状态、短期记忆与长期记忆](07-session-and-memory.md)。
- 了解 JSON-RPC 2.0 的基本形态：`jsonrpc`、`id`、`method`、`params`、`result`。
- 了解进程间通信与 HTTP 传输的差异（本地子进程 vs 远程服务）。

## 业务场景

小陈的工单需要同时查订单、查物流、算退款。订单系统由商城团队维护，物流由第三方承运商提供 API，发票由财务 SaaS 提供。

三个系统的接入诉求不同：订单接口变化频繁但完全可控；物流接口由外部维护、变更不可预期；发票系统有严格审计要求，任何开票动作都要留痕。团队还要决定：这些能力由一个 agent 统一编排，还是拆成多个 agent。

## 核心概念

| 术语 | 含义 | 在本场景中的体现 |
| --- | --- | --- |
| *MCP* | 用 JSON-RPC 标准化“向模型应用暴露上下文与工具”的开放协议 | 三个系统统一成 MCP 服务器 |
| *host* | 发起连接的模型应用，负责用户同意与权限 | 售后助手后端 |
| *client* | host 内与某个服务器一一对应的连接器 | 订单连接器、物流连接器 |
| *server* | 提供资源、提示与工具的服务 | 订单 MCP 服务器 |
| *资源*（resources） | 供模型或用户读取的上下文数据 | 售后政策文档 |
| *提示*（prompts） | 可复用的模板化消息或工作流 | “标准退款话术”模板 |
| *工具*（tools） | 模型可请求执行的函数 | `get_order`、`create_refund` |
| *能力协商* | 初始化时双方声明支持的特性 | 服务器声明 `tools.listChanged` |

协议明确规定：工具是 model-controlled 的，模型可以发现并调用；但实现方**应当**始终保留人的否决能力。MCP 规范也点明，除非服务器可信，工具的行为描述与注解都应视为不可信。

单 Agent 与多 Agent 的差别可以用三张表看清：

| 维度 | 单 Agent | 多 Agent |
| --- | --- | --- |
| 上下文 | 一份历史，工具全可见 | 每角色一份历史，重复注入 |
| 权限 | 一套权限，靠工具裁剪 | 可按角色收敛，但需跨角色传递主体 |
| 错误传播 | 在同一循环内可见 | 经角色输出传递，难定位 |
| 成本 | 单次调用链 | 角色数 × 轮数，通常显著更高 |
| 适用 | 工具数量可控、流程清晰 | 子任务可隔离、需要不同工具集或模型 |

## 工作原理

一次 MCP 交互的生命周期：

1. **建立连接。** host 按配置启动或连接服务器。本地常用标准输入输出（stdio）传输，远程常用可流式 HTTP 传输。
2. **初始化与协商。** client 发送 `initialize`，声明协议版本与能力；服务器返回自己的版本、能力与身份。版本不匹配时按规范回退或断开。
3. **确认就绪。** client 发送 `notifications/initialized` 通知，此消息无需响应。
4. **发现工具。** client 调用 `tools/list`，拿到工具名、描述与 `inputSchema`。服务器支持变更通知时，工具增删会主动告知。
5. **调用工具。** 模型决定调用后，host 把请求转成 `tools/call`，带工具名与参数。服务器执行并返回 `content`（文本、图片、资源链接等），出错时返回错误对象。
6. **结果回填。** host 把结果转成模型可读的消息，继续推理。审计与权限控制都发生在 host 这一侧。

多 Agent 的运行机制则是把第 5 步变成“调用另一个 agent”。差别在于被调用方有自己的上下文与决策权：编排者给出子任务，工作者返回结论，中间过程对编排者不可见。这种*上下文隔离*既是优点（减少干扰）也是缺点（编排者无法判断结论怎么来的）。

## 架构与选型

| 集成方式 | 适用 | 代价 |
| --- | --- | --- |
| 应用内函数（直接调用 SDK） | 单一应用、工具稳定、权限边界清晰 | 每个模型接入都要适配一次 |
| 自建 MCP 服务器 | 多应用共享能力、需要生态复用 | 需要维护协议层、鉴权与版本 |
| 接入第三方 MCP 服务器 | 快速获得外部能力 | 信任边界外移，描述与注解不可信 |
| 保留人工操作 | 高影响、低频、规则不清 | 效率低，但风险可控 |

多 Agent 的选型问题可以简化为三问：**子任务能否独立完成？共享状态是否很少？每个角色是否有不同的工具或权限？** 三个都肯定，多 Agent 才有意义；如果只是“想看起来更专业”，单 Agent 加工具路由更便宜也更好调。

工具数量增长时的经验做法：单 Agent 的工具超过十几个后，选择准确率通常下降，此时先用**分组 + 路由**（先判定诉求，再只暴露该组工具），而不是直接拆 agent。路由是代码，agent 是决策者，前者的可控性高得多。

## 最小示例

下面用报文演示 MCP 的三步交互，并校验请求与响应的 `id` 配对。运行环境 Python 3.9+。

```python
import json

# 1) 客户端发出的报文：注意通知消息没有 id，也不期待响应
REQUESTS = [
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"after-sales-agent","version":"0.1.0"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized"}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}',
    '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_order","arguments":{"order_id":"SO-2026-0001"}}}',
]

# 2) 服务器的响应（真实环境由服务器返回，此处固定用于演示）
RESPONSES = [
    {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18",
     "capabilities": {"tools": {"listChanged": True}},
     "serverInfo": {"name": "after-sales-tools", "version": "1.2.0"}}},
    {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "get_order",
     "description": "按订单号查询状态", "inputSchema": {"type": "object",
     "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}]}},
    {"jsonrpc": "2.0", "id": 99, "result": {"content": [{"type": "text",
     "text": "{\"status\":\"delivered\"}"}]}},
]

def parse(line):
    msg = json.loads(line)
    if msg.get("jsonrpc") != "2.0":        # 3) 版本字段缺失说明对端不是 MCP
        raise ValueError("不是 JSON-RPC 2.0 报文")
    return msg

pending = {}
for line in REQUESTS:
    msg = parse(line)
    if "id" in msg:                        # 4) 有 id 才需要配对响应
        pending[msg["id"]] = msg["method"]
    else:
        print(f"通知 {msg['method']}: 无需响应")

for resp in RESPONSES:
    rid = resp.get("id")
    if rid in pending:                     # 5) id 配对成功，取出结果交给模型
        print(f"响应 id={rid} 配对 {pending.pop(rid)}")
    else:
        print(f"响应 id={rid} 无对应请求 -> 丢弃（可能是超时后的迟到响应）")

print("仍未响应:", pending)                # 6) 未响应的请求必须触发超时处理
```

预期输出：

```text
通知 notifications/initialized: 无需响应
响应 id=1 配对 initialize
响应 id=2 配对 tools/list
响应 id=99 无对应请求 -> 丢弃（可能是超时后的迟到响应）
仍未响应: {3: 'tools/call'}
```

现实读法：`tools/call` 没有响应就是一次悬空调用，必须由 host 超时、重试或转人工；`id=99` 的迟到响应不能因为“形状对”就被塞进上下文，否则模型会把旧结果当新结果。

## 动手实验

**前置条件**：Python 3.9+，保存为 `mcp_msgs.py`。

**步骤**：

1. 运行并核对输出。
2. 给 `tools/call` 伪造一条响应 `id=3`，观察配对成功后的处理路径。
3. 给服务器加一个 `error` 响应（`{"jsonrpc":"2.0","id":3,"error":{"code":-32602,"message":"Invalid params"}}`），验证客户端是否能区分协议错误与业务失败。
4. 写一个 `tools/list` 结果的裁剪函数：只保留 `name`、`description`、`inputSchema`，丢弃服务器附带的额外字段。

**预期结果**：步骤 2 中 `pending` 清空；步骤 3 中能打印错误码而不抛异常；步骤 4 输出的工具定义可直接用于模型请求。

**验证方法**：断言每个请求都有“响应到达 / 超时 / 错误”三种终局之一；对协议错误码做映射表测试。

**清理方法**：删除脚本；未真实连接任何服务器，无凭据泄漏风险。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 工具列表为空 | 服务器未声明 `tools` 能力，或初始化未完成 | 抓 `initialize` 与 `tools/list` 报文 | 补能力协商，确认通知已发送 |
| 调用后长时间无响应 | 传输层卡住，host 未设超时 | 检查连接日志与超时配置 | 单次调用超时 + 取消通知 + 转人工 |
| 模型调用不存在的工具 | 工具已下线但 host 缓存未刷新 | 对比 `tools/list` 与请求中的工具名 | 订阅变更通知，缓存带版本号 |
| 第三方工具行为异常 | 服务器描述与实际行为不一致 | 用只读数据做验证调用 | 引入服务器白名单与行为测试 |
| 多 Agent 结论互相矛盾 | 无共享事实源，各角色各自推断 | 对比各角色输入与结论 | 关键事实由确定性服务提供，角色只做表达 |

## 安全与生产注意事项

**<u>第三方 MCP 服务器是不可信边界：它返回的描述、注解和内容都可能含指令。</u>** 规范要求把工具行为描述与注解视为不可信（除非服务器可信），并在调用前取得用户同意。生产上应做服务器白名单、最小权限令牌、出站网络限制，并对返回内容做长度与结构校验。

**<u>多 Agent 链路必须把原始用户身份与授权范围一路传下去，不能让下游只看到“某个服务”的身份。</u>** OWASP LLM03 特别提醒：在委派或多 Agent 流程中，要保留原始用户上下文与授权范围，而不是依赖调用方的服务身份。否则一个低权角色可以通过高权角色间接完成越权操作。

## 本课总结

- **MCP 标准化的是工具与上下文的暴露方式**，不改变权限、审批与终止责任——这些仍在 host 侧。
- JSON-RPC 的 `id` 配对、通知无响应、错误对象三类语义是排障的基础。
- 单 Agent 在工具数量可控时更便宜、更好调；工具变多先做分组路由。
- 多 Agent 的价值来自上下文隔离与差异化权限，代价是成本、延迟与错误传播。
- 第三方服务器与跨角色调用是两个独立的信任边界，都要单独设计控制。

## 思考题

订单与发票都需要“校验金额”这一步，目前两个 agent 各自实现，出现过金额不一致。你会让两边共享一个校验服务、把校验下沉到确定性代码，还是合并成一个 agent？请说明依据与迁移步骤。

参考思路：金额校验属于可判定的业务规则，应下沉为共享的确定性服务，两个 agent 只调用不重算——这同时消除重复实现与不一致。迁移上先抽出校验服务与接口契约，再逐个替换调用点，最后用对账任务验证一致率。合并 agent 反而扩大了权限与上下文耦合。

## 小测

1. MCP 中 host、client、server 的职责分别是什么？
2. 下列哪类报文不需要响应？  
   A. `initialize`　B. `tools/list`　C. `notifications/initialized`　D. `tools/call`
3. 为什么说“接入第三方 MCP 服务器”会把信任边界外移？
4. 单 Agent 工具数量过多时，为什么优先做路由而不是直接拆多 Agent？
5. 场景题：为提升专业性，团队把售后拆成五个 agent，成本涨 4 倍且错误率上升。请给出诊断顺序。

## 答案与解析

1. host 是发起连接的模型应用，负责用户同意、权限与审计；client 是 host 内与单个服务器对应的连接器；server 提供资源、提示与工具并执行调用。三者职责不能混：安全控制在 host，能力在 server。
2. **C。** 通知类消息没有 `id`，按 JSON-RPC 语义不需要响应。A、B、D 都带 `id`，必须收到结果或错误，否则就是悬空调用。
3. 因为工具描述、返回内容与执行行为都由外部方控制，你的应用只能做校验与限制，无法保证其真实意图。相应地需要服务器白名单、最小权限、内容校验与用户同意。
4. 因为路由是确定性代码，能收窄每次决策的工具集合与权限，成本与可测性都优于引入多个决策者；多 Agent 会带来上下文重复、错误传播与跨角色权限传递问题。
5. 先量化：统计各角色的调用次数、token、延迟与失败原因，确认成本来自轮数还是上下文重复；再检查结论冲突是否源于缺少共享事实源；然后验证角色权限是否被过度放大。多数情况下应收敛为“单 Agent + 工具路由 + 确定性校验服务”，仅在确有隔离需求处保留子 agent。

## 延伸阅读与下一课

- Model Context Protocol：[Specification 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18)（host/client/server、JSON-RPC、资源/提示/工具、安全与用户同意原则；截至 2026-10-19 复核）。
- Model Context Protocol：[Tools（2025-06-18）](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)（`tools/list`、`tools/call`、`inputSchema`/`outputSchema`、结构化内容与错误处理）。
- OWASP GenAI：[LLM03:2026 Excessive Agency](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/)（委派与多 Agent 场景下的身份与授权传递要求）。
- Anthropic Engineering：[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)（编排者-工作者模式与“优先选择最简单方案”的原则）。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[会话状态、短期记忆与长期记忆](07-session-and-memory.md)。
- 下一课：[工具超时、重试、沙箱、审计与失败模式](09-tool-reliability-sandbox-and-failure-modes.md)。
