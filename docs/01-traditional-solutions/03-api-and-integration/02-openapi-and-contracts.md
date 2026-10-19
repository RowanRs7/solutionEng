---
title: OpenAPI 与接口契约
slug: openapi-and-contracts
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 50m
prerequisites:
  - api-rest-and-resource-modeling
outcomes:
  - 指出 OpenAPI 3.1 文档中路径、操作、参数、请求体、响应与 $ref 组件的位置和作用
  - 为退款接口写出可校验的 OpenAPI 片段，并用脚本检查结构、引用和示例的一致性
  - 把一次契约变更分类为破坏性或兼容性变更，并给出评审、发布与弃用步骤
last_reviewed: 2026-10-19
---

# OpenAPI 与接口契约

## 为什么需要学习

晴空商城的退款能力有三份“接口说明”：前端仓库的 TypeScript 类型、后端框架生成的 `/docs` 页面、Wiki 上三个月前的表格附件。三者各说一套：金额在前端叫 `amount`（元），在后端叫 `amount_cents`（分）；状态在代码里是 `succeeded`，前端类型里写成 `success`；失败结构一处是字符串，一处是 `{"code","message"}`。

后果不是某个接口报错，而是联调最后一天才发现对不上：财务把 19.90 元记成 19.90 分，客服把成功显示成“未知”，支付商重复回调时又退了一次款。

> **核心结论：** 接口契约的价值不在于“把接口写清楚”，而在于让三方的不一致在合并代码之前被机器发现。

## 学习目标

完成本课后，你能够：

- 指出 OpenAPI 3.1 文档中 `paths`、`operationId`、`parameters`、`requestBody`、`responses` 与 `components` 的位置和作用。
- 为“创建退款”和“查询退款”写出可校验的 OpenAPI 片段，并用脚本检查结构、`$ref` 与示例的一致性。
- 把一次契约变更分类为破坏性变更或兼容性变更，并写出对应的评审、发布、弃用步骤。
- 区分契约文档版本与 API 主版本，说明两者分别该写在文档的哪个位置。

## 前置知识

- 回看上一课：[API、REST 与资源建模](01-api-rest-and-resource-modeling.md)。
- 知道 HTTP 方法与状态码的含义（`POST` 创建、`GET` 读取、`404` 不存在），可参考 [HTTP 请求与响应](../02-web-and-network/03-http-request-response.md)。
- 能读写 JSON 对象与数组，理解 `required` 这类约束不会自动生效，需某一方显式执行。
- 本机有 `python3`（3.8+），实验只使用标准库，不需要网络。

## 业务场景

退款能力由一个退款服务提供，消费方不止一个，而且发布节奏不同：

| 消费方 | 调用方式 | 硬约束 |
| --- | --- | --- |
| 客服工作台 | `POST /refunds` 创建，`GET /refunds/{refund_id}` 轮询 | 页面 2 秒内给出受理结果，错误要能直接展示给客服 |
| 财务对账 | 按时间窗批量拉取退款明细 | 金额精确到分；“退款成功”的定义与支付商一致 |
| 支付商回调 | 服务端接收事件后更新退款状态 | 重复回调必须幂等，字段缺失不能标成功 |
| 仓储退货 | 退款成功后生成退货单 | 只关心 `order_id` 与 `refund_id` |

上一课已把退款建模为资源：`/refunds` 是集合，`/refunds/{refund_id}` 是成员。本课的侧面是：四类消费方、四支团队，凭什么相信彼此面对的是同一个接口。

现状是“文档追着代码跑”：后端改完字段顺手更新 `/docs`，前端照自己的类型写，财务照旧附件写脚本。架构师的决定是改为契约先行：契约进仓库、进评审、进 CI，实现必须与它一致。

## 核心概念

- *接口契约*：对“请求、响应、失败长什么样”的机器可读约定，而不只是文字说明。
- *OpenAPI 文档*：描述 HTTP API 的标准格式，可用 YAML 或 JSON 书写；3.1 用 JSON Schema 2020-12 描述结构。
- *路径（path）与操作（operation）*：路径是资源地址，操作是“方法 + 路径”的组合，`operationId` 是生成客户端方法名的依据。
- *schema*：字段名、类型、必填、格式与取值范围的声明，也是契约里唯一能被自动校验的部分。
- *组件（components）与 `$ref`*：复用 schema、参数、响应、安全方案的位置；`$ref: "#/components/schemas/Refund"` 是文档内引用，不是文件路径。
- *契约优先（design-first）*：先评审契约再写实现；代码是实现契约的一种方式，而不是契约本身。
- *契约测试*：用契约校验真实请求与响应，而不是校验手写 Mock。
- *破坏性变更*：让已有消费方无法继续工作，例如删除或重命名字段、收紧类型与枚举、新增必填字段。

| 概念 | 在文档中的位置 | 退款示例 | 缺了会怎样 |
| --- | --- | --- | --- |
| 路径与操作 | `paths` | `/refunds/{refund_id}` 的 `get` | 客户端调错地址，网关无法限流 |
| 数据结构 | `components.schemas` | `Refund.required` | 缺字段的响应也“通过”，前端运行时崩 |
| 参数约束 | `parameters` 与 schema | `refund_id` 的 `pattern` | 非法 ID 透传到数据库 |
| 失败表达 | `responses` 的 4xx 段 | 400/404 复用统一错误体 | 每接口一套错误格式，客服无法展示 |
| 版本与地址 | `info.version`、`servers` | `1.3.0` 与 `/v1` | 变更无起点，回滚无依据 |
| 示例 | `content.*.example` | 201 响应的一个退款 | Mock 与线上行为分叉 |

**能不能被机器校验，是判断一份文档算不算契约的分界线。** <u>写在 Wiki 里、只能靠肉眼比对的“契约”，在评审时几乎不产生约束力。</u>

## 工作原理

契约先行的闭环是一条流水线：

1. **建模**：沿用上一课的资源模型：`/refunds` 是集合、`/refunds/{refund_id}` 是成员、取消退款是成员上的动作。
2. **写骨架**：声明 `openapi` 版本、`info`（标题与文档版本）、`servers`（环境基址）、`paths`（操作清单）。
3. **定义结构**：把重复出现的对象放进 `components.schemas`；先写 `required`、类型和枚举，再补说明与示例。
4. **定义失败**：为 400、404、409 指定统一错误结构；失败响应最常被消费方依赖，也最容易被漏写。
5. **本地校验**：检查三项——结构是否符合 OpenAPI、`$ref` 是否都能解析、示例是否满足 schema 的必填字段。
6. **评审变更**：与主干契约对比，把每个改动标为破坏性或兼容性，并指定受影响消费方确认。
7. **生成与测试**：生成服务端骨架、客户端 SDK 和 Mock，在 CI 中用真实响应做契约测试。
8. **发布与弃用**：破坏性变更走新主版本路径，旧版本给弃用期并逐个通知，到期下线。

文档结构记住四层即可：`paths` 按资源组织操作；`parameters` 的 `in` 只有 `path`、`query`、`header`、`cookie` 四种，其中路径参数必须 `required: true` 且名字与路径模板一致；`requestBody.content` 与 `responses` 按媒体类型分桶，`responses` 用状态码做键、`default` 兜底；`components` 下的 `schemas`、`parameters`、`responses`、`securitySchemes` 通过 `$ref` 复用。

3.1 与 3.0 的差别集中在 schema 语义：3.1 采用 JSON Schema 2020-12，取消 `nullable`，可空写成 `"type": ["string", "null"]`；`$ref` 旁允许并列 `description`；新增 `webhooks` 描述回调。

## 架构与选型

| 做法 | 适用场景 | 代价与风险 | 选它的判据 |
| --- | --- | --- | --- |
| 契约优先，手写并评审 | 多消费方、跨团队、对外、有合规要求 | 前期慢；契约可能分叉，需契约测试兜底 | 消费方两个以上或对外开放 |
| 代码优先，框架从类型注解生成 | 单团队内部，消费方就是自己前端 | 评审对象变成代码；契约随实现漂移；易暴露内部字段 | 只有一个消费方且同节奏发版 |
| 混合：代码生成 + 契约快照入库 + CI 差异闸门 | 已有服务想逐步收紧 | 需额外闸门；生成器会丢掉部分人工语义 | 迁移期，或团队中等 |
| 只写文字文档 | 一次性对接，对方只能读文档 | 无法校验，必然漂移 | 几乎不推荐，只能当临时补充 |

选型顺序：消费方数量 → 是否对外 → 变更频率 → 是否已有 CI；前两条通常已决定答案。工具链分四类：结构校验用 Redocly CLI 或 Spectral，差异用 oasdiff，生成用 OpenAPI Generator，接口测试用 Schemathesis。**工具不能替你决定什么是破坏性变更，只能把你写下的规则跑快。**

## 最小示例

问题：让“契约与示例不一致”在本地暴露，而不是等联调。环境：Python 3.8+，只用标准库，契约存为 JSON（YAML 更常见，但需第三方解析器）。输入：一份退款契约；输出：一行汇总和逐条问题，退出码供 CI 判断。

先写契约文件 `refund-api.json`：

```json
{
  "openapi": "3.1.0",
  "info": { "title": "晴空商城退款服务", "version": "1.3.0" },
  "servers": [{ "url": "https://api.qingkong.example/v1" }],
  "paths": {
    "/refunds": {
      "post": {
        "operationId": "createRefund",
        "summary": "受理一笔退款",
        "requestBody": {
          "required": true,
          "content": { "application/json": { "schema": { "$ref": "#/components/schemas/RefundRequest" } } }
        },
        "responses": {
          "201": {
            "description": "已受理",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/Refund" },
                "example": { "refund_id": "R-20261019-0007", "status": "pending", "amount_cents": 1990 }
              }
            }
          },
          "400": { "$ref": "#/components/responses/Error" }
        }
      }
    },
    "/refunds/{refund_id}": {
      "get": {
        "operationId": "getRefund",
        "parameters": [{ "$ref": "#/components/parameters/RefundId" }],
        "responses": {
          "200": { "description": "退款详情", "content": { "application/json": { "schema": { "$ref": "#/components/schemas/Refund" } } } },
          "404": { "$ref": "#/components/responses/Error" }
        }
      }
    }
  },
  "components": {
    "parameters": {
      "RefundId": { "name": "refund_id", "in": "path", "required": true, "schema": { "type": "string", "pattern": "^R-[0-9]{8}-[0-9]{4}$" } }
    },
    "responses": {
      "Error": { "description": "统一错误", "content": { "application/json": { "schema": { "$ref": "#/components/schemas/Error" } } } }
    },
    "schemas": {
      "RefundRequest": {
        "type": "object",
        "required": ["order_id", "amount_cents", "reason"],
        "properties": {
          "order_id": { "type": "string" },
          "amount_cents": { "type": "integer", "minimum": 1 },
          "reason": { "type": "string", "maxLength": 200 }
        },
        "additionalProperties": false
      },
      "Refund": {
        "type": "object",
        "required": ["refund_id", "status", "amount_cents"],
        "properties": {
          "refund_id": { "type": "string" },
          "status": { "type": "string", "enum": ["pending", "succeeded", "failed"] },
          "amount_cents": { "type": "integer" }
        }
      },
      "Error": {
        "type": "object",
        "required": ["code", "message"],
        "properties": { "code": { "type": "string" }, "message": { "type": "string" } }
      }
    }
  }
}
```

JSON 不能写注释，逐字段说明：`openapi` 只声明规范版本；`info.version` 是**这份文档**的版本（1.3.0），不是地址里的 `/v1`；`servers` 由环境注入，避免写死生产域名；`operationId` 必须全局唯一，生成器用它命名客户端方法；`amount_cents` 用整数分，规避浮点误差；`additionalProperties: false` 让多出来的字段显式失败，而不是被静默忽略。

再写校验脚本 `check_contract.py`：

```python
import json
import sys
from pathlib import Path

# 契约用 JSON 存放，标准库即可解析；生产里也可用 YAML，只是要多装一个解析器
doc = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
problems = []  # 收集全部问题再一次性报告，避免改一个跑一次


def walk(node, where="#"):
    """递归遍历文档，产出 (引用字符串, 所在位置)，用于检查 $ref 能否解析。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value, f"{where}/{key}"
            else:
                yield from walk(value, f"{where}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{where}[{index}]")


def resolve(ref):
    """只处理文档内引用：以 #/ 开头，按 / 逐段取键；取不到返回 None。"""
    if not ref.startswith("#/"):
        return None
    node = doc
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


if not str(doc.get("openapi", "")).startswith("3.1"):
    problems.append("openapi 必须声明 3.1.x")  # 3.0 与 3.1 的 schema 语义不同，混用等于没约束

for field in ("title", "version"):
    if not doc.get("info", {}).get(field):
        problems.append(f"info.{field} 缺失")  # 没有版本号就无法判断变更从哪一版开始

operations = set()
for path, item in doc.get("paths", {}).items():
    if not path.startswith("/") or path.endswith("/"):
        problems.append(f"路径必须以 / 开头且不以 / 结尾：{path}")
    for method, operation in item.items():
        if method in {"parameters", "servers", "summary", "description"}:
            continue
        op_id = operation.get("operationId")
        # operationId 是客户端方法名的唯一来源，重复会让生成器互相覆盖
        if not op_id:
            problems.append(f"{method.upper()} {path} 缺 operationId")
        elif op_id in operations:
            problems.append(f"operationId 重复：{op_id}")
        else:
            operations.add(op_id)
        if not operation.get("responses"):
            problems.append(f"{method.upper()} {path} 没有声明响应")


for ref, where in walk(doc):
    if resolve(ref) is None:
        problems.append(f"{where} 指向不存在的组件：{ref}")

# 示例最容易腐烂：它必须满足所引用 schema 的 required，否则 Mock 会骗过前端
for path, item in doc.get("paths", {}).items():
    for method, operation in item.items():
        if not isinstance(operation, dict) or "responses" not in operation:
            continue
        for code, response in operation["responses"].items():
            if "$ref" in response:
                response = resolve(response["$ref"]) or {}
            for media in response.get("content", {}).values():
                schema = media.get("schema", {})
                if "$ref" in schema:
                    schema = resolve(schema["$ref"]) or {}
                example = media.get("example")
                if not isinstance(example, dict):
                    continue
                missing = [name for name in schema.get("required", []) if name not in example]
                if missing:
                    problems.append(f"{method.upper()} {path} {code} 示例缺字段：{missing}")

print(f"操作数：{len(operations)}，问题数：{len(problems)}")
for problem in problems:
    print(f"- {problem}")
sys.exit(1 if problems else 0)  # 非零退出码让 CI 与本地脚本都能直接判断失败
```

运行：

```bash
cd /tmp/dsh-openapi-lab && python3 check_contract.py refund-api.json
```

预期输出（已在 Python 3.14 上验证）：

```text
操作数：2，问题数：0
```

把 `Refund` 的 `required` 改成 `["refund_id", "status", "amount_cents", "updated_at"]`，但不动 201 响应的示例，再运行一次：

```text
操作数：2，问题数：1
- POST /refunds 201 示例缺字段：['updated_at']
```

此时退出码为 1。脚本只覆盖几条最重要的不变量——规范版本、命名与引用完整性、示例与 schema 一致。真实工具会覆盖几百条规则，但**规则的数量不是关键，关键是规则进 CI 并让失败阻塞合并**。

## 动手实验

前置条件：本机有 `python3`，最小示例的两个文件在 `/tmp/dsh-openapi-lab/`，不需要网络。

1. 跑一次基线校验并记录退出码：`cd /tmp/dsh-openapi-lab && python3 check_contract.py refund-api.json; echo $?`。
2. 备份契约：`cp refund-api.json refund-api.json.bak`。
3. 给 `GET /refunds/{refund_id}` 增加可选查询参数 `status`，`enum` 为 `pending`、`succeeded`、`failed`，`required` 缺省。
4. 重新运行校验，判断这次改动是否触发任何问题。
5. 在 `Refund` 的 `required` 中加 `updated_at`，仍不改 201 示例，重跑。
6. 用 `diff -u refund-api.json.bak refund-api.json` 查看改动，判定第 3、5 步各属于哪类变更，并填入：第 3 步属于____；第 5 步属于____。
7. 撤销第 5 步（`cp refund-api.json.bak refund-api.json`），确认校验重新回到 0 问题。

预期结果：第 1 步输出“操作数：2，问题数：0”、退出码 0；第 4 步仍是 0 问题；第 5 步报“示例缺字段：['updated_at']”、退出码 1。

验证方法：`python3 -m json.tool refund-api.json > /dev/null && echo JSON_OK` 确认文件仍是合法 JSON；对比第 1 步与第 5 步的退出码。清理：`rm -rf /tmp/dsh-openapi-lab`。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 文档写 `amount` 是数字，线上返回字符串 | 文档手工维护，没有与实现对照的环节 | 用契约校验真实响应，或对比生成代码 | 由代码生成契约，或把契约测试放进 CI |
| 生成的客户端编译不过 | `$ref` 指向不存在的组件，或参数名与 `{...}` 不一致 | 用 lint 检查引用，核对 `parameters.in: path` 的 `name` | 补全组件，参数名对齐模板 |
| 评审通过了，上线却打断消费方 | 只看“新增了什么”，没看必填、枚举与类型的收紧 | 用差异工具对比主干契约，逐条看 `required` 与 `enum` | 建立变更分类闸门，破坏性变更走新主版本 |
| Mock 能跑通，真实接口却崩 | 示例是手写的，从未校验过是否满足 schema | 校验示例字段，或直接用 schema 生成 Mock | 示例纳入校验，不把示例当“仅供演示” |
| 契约几千行，评审没人看得动 | 单文件堆叠，缺少按领域拆分和 `operationId` | 看文件行数与操作数，检查重复结构 | 按领域拆成多个文件并用 `$ref` 组合 |
| 3.1 文档里写了 `nullable: true`，可空却不生效 | 3.1 已移除 `nullable`，多数工具静默忽略未知字段 | 看 `type` 是否写成数组，或用支持 3.1 的规则集 | 改为 `"type": ["string", "null"]`，并升级 lint |

## 安全与生产注意事项

**<u>把内部接口和真实示例数据发布到公开文档站，等于公开一张攻击地图。</u>** 契约含全部路径、字段命名、限额与示例；渲染成公开页面或提交到仓库后，攻击者能据此枚举管理接口、猜参数。缓解：用 `x-internal: true` 标记内部操作并在构建公开文档时过滤，示例用合成数据，文档站加认证或只在内网可达，生产关闭框架自带的 `/docs`。

**<u>契约校验通过不等于业务校验通过。</u>** `amount_cents: integer` 既允许 1 分也允许 99999999 元；可退余额、单笔上限、超 500 元需审核这些规则 schema 表达不了，也不会自动执行。把它当安全控制，超额退款就会真实发生。缓解：schema 管结构与格式，业务规则在服务端强制执行，并用幂等键阻止重复退款。

**<u>用第三方 spec 直接生成代码，会把供应链风险带进仓库。</u>** 未固定来源与版本的 spec 可能注入外部调用或被篡改的默认值。缓解：锁定来源与版本，生成结果的 diff 一并评审。

另两条要求：破坏性变更必须留出弃用期，并用 `Deprecation`/`Sunset` 类响应头与变更日志告知消费方；<u>契约与实现同仓同 PR，别让它变成另一个要人工同步的仓库</u>，否则问题会复发。

## 本课总结

- **接口契约是可被机器校验的约定，而不是给人看的说明。**
- OpenAPI 的骨架是 `paths` 的操作、`components` 的复用结构和 `$ref` 的连接；`info.version` 是文档版本，路径里的 `/v1` 才是 API 主版本。
- 契约先行的闭环是：建模 → 写骨架 → 定结构 → 定失败 → 本地校验 → 评审变更 → 生成与测试 → 发布与弃用。
- 破坏性变更的核心是“让已有消费方无法继续工作”：删除、重命名、收紧类型与枚举、新增必填字段都属此类；新增可选参数通常兼容。
- 新增响应字段和枚举值在语义上兼容，但对严格模式或穷举分支的客户端可能是行为破坏，需先扩展后收紧。

## 思考题

有同事反对契约先行：“每次改字段都要评审契约，迭代被拖慢。”请设计一个既能拦住破坏性变更、又不阻塞迭代的机制：哪些检查进 CI、哪些留给人评审，用什么数据证明它减少了联调返工。

参考思路：把变更分成两条通道——兼容性变更由 CI 自动放行（结构、引用校验，差异判为兼容即通过），破坏性变更才触发人工评审并要求消费方确认。人工评审只回答三个问题：谁受影响、怎么迁移、何时下线。度量可用联调缺陷数、契约工单数、从合并到消费方升级完成的时长，对比引入前后的同一指标。

## 小测

1. OpenAPI 3.1 文档的 `info.version` 表示什么？  
   A. 接口的主版本号，如 `/v1`　B. 这份契约文档自身的版本　C. OpenAPI 规范的版本　D. 服务端镜像的 tag
2. 判断：在 3.1 文档里写 `nullable: true` 仍然能表达“该字段可以为空”。
3. 下列哪一项最可能是破坏性变更？  
   A. 新增一个可选查询参数　B. 放宽 `maxLength`　C. 把响应字段 `amount_cents` 从整数改成字符串　D. 给字段补充 `description`
4. `$ref: "#/components/schemas/Refund"` 中的 `#` 指什么？
5. 场景题：团队在同一份 `1.3.0` 契约里给响应枚举 `status` 新增 `cancelled`，而前端用 TypeScript 穷举 `switch`、`default` 直接抛错。这次变更算兼容吗？发布前你会要求什么？

## 答案与解析

1. **B。**它描述契约文档的版本，用于追踪“改过几次”。A 由 `servers` 或路径前缀表达；C 是 `openapi` 字段；D 与契约无关。
2. **错。**3.1 已移除 `nullable`，多数校验器把它当未知字段静默忽略，“可空”的约定随之消失，直到线上真的返回 `null` 才暴露。正确写法是 `"type": ["string", "null"]`。
3. **C。**类型变化让按整数解析的客户端直接失败，且无法靠忽略字段绕过。A 旧请求不受影响；B 是放宽，原请求仍合法；D 只影响文档展示。
4. 指向**当前文档的根节点**。后面是从根出发的 JSON Pointer 路径，只在本文档内有效；跨文件引用需要文件路径加 `#` 片段。
5. **按差异分类通常判为向后兼容，但对穷举客户端是行为破坏。**旧客户端没有 `cancelled` 分支，`default` 抛错会让页面崩。发布前应要求：先把前端 `default` 改成安全降级并单独上线（扩展），再让服务端返回新枚举值（收紧），中间用灰度与“未知枚举命中”监控验证。

### 动手实验参考

合格完成应满足：第 1、4 步都报 0 问题，说明新增可选参数属于兼容性变更；第 5 步报“示例缺字段：['updated_at']”且退出码 1，因为它违反“示例必须满足 `required`”这条不变量，同时属于破坏性变更（响应新增必填字段）。若第 4 步报错，检查是否误写成 `required: true` 或空数组。要点是体会“变更分类”与“机械校验”是两件事。

## 延伸阅读与下一课

- [OpenAPI Specification 3.1.0](https://spec.openapis.org/oas/v3.1.0)
- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12)
- [OpenAPI Initiative](https://www.openapis.org/)
- [OpenAPI Generator：从契约生成服务端骨架与客户端 SDK](https://openapi-generator.tech/)
- [Redocly CLI：契约 lint 与文档渲染](https://github.com/Redocly/redocly-cli)
- [RFC 9457：HTTP API 的 Problem Details](https://www.rfc-editor.org/rfc/rfc9457)
- [RFC 8594：Sunset 响应头](https://www.rfc-editor.org/rfc/rfc8594)

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[API、REST 与资源建模](01-api-rest-and-resource-modeling.md)。
- 下一课：[参数校验、错误模型与版本管理](03-validation-errors-and-versioning.md)。
