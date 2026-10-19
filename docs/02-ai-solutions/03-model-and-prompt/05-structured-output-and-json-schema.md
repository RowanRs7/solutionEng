---
title: 结构化输出与 JSON Schema
slug: structured-output-and-json-schema
module: ai-solutions
stage: design
type: core
difficulty: intermediate
duration: 55m
prerequisites:
  - prompt-templates-and-versioning
outcomes:
  - 为一个业务动作写出可校验的 JSON Schema，并用枚举与 null 联合表达可选字段
  - 说明严格 Schema 模式能保证什么、不能保证什么
  - 识别 Schema 子集限制导致的字段被忽略或不生效
last_reviewed: 2026-10-19
---

# 结构化输出与 JSON Schema

## 为什么需要学习

售后助手要生成答复，同时给出决策：退款、换货、维修、驳回，还是需要追问。最早的做法是让模型“用 JSON 回答”，结果下游解析器每天报错十几次：有时用中文引号，有时在 JSON 前后加一句“以下是结果”，有时把金额写成 `"800 元"`。

修复方式不是继续加提示词“请务必输出合法 JSON”，而是把输出变成*契约*：先定 Schema，再让模型在 Schema 约束下生成，最后在服务端校验。格式靠机制保证，语义才靠提示词。

> **核心结论：** JSON Schema 保证“形状正确”，不保证“内容正确”；金额是否超限、条款是否适用，必须由业务校验兜底。

## 学习目标

完成本课后，你能够：

- 为一个售后决策动作写出含枚举、数组、可选字段的 JSON Schema。
- 说明严格模式（strict）会强制哪些约束，例如所有字段必填与 `additionalProperties: false`。
- 区分“Schema 可表达的限制”和“必须写代码的限制”。
- 列出主流实现不支持的 JSON Schema 关键字，并给出等价写法。

## 前置知识

- 回看上一课：[Prompt 模板、变量与版本管理](04-prompt-templates-and-versioning.md)。
- 了解 JSON 的基本类型：对象、数组、字符串、数字、布尔、null。
- 知道枚举（enum）用于限定取值范围。
- 能读懂 Python 字典与类型判断。

## 业务场景

售后助手的输出要被两个下游消费：客服工作台（渲染答复）和退款服务（读取决策）。退款服务只接受白名单动作，并且必须知道金额、政策依据和是否需要人工审核。

团队约定输出结构如下：`decision` 只能取五个值，`refund_amount` 在非退款场景为 `null`，`policy_ids` 至少给出引用的条款编号，`needs_human` 决定是否进入人工队列，`reply_text` 是给客服看的答复草稿。

## 核心概念

*结构化输出*（structured output）指用机器可读的结构约束模型生成，而不是解析自由文本。*JSON Schema* 是描述 JSON 数据形状的标准；*严格模式*（strict）是厂商提供的强化选项，让模型输出被约束到给定 Schema。*JSON 模式*（JSON mode）只保证“是合法 JSON”，不保证符合你的字段定义，这一点在 Azure OpenAI 文档中被明确区分。

| 能力 | JSON 模式 | 严格 JSON Schema | 业务校验（代码） |
| --- | --- | --- | --- |
| 一定是合法 JSON | 是 | 是 | 不适用 |
| 字段名与类型符合定义 | 不保证 | 是 | 是（二次校验） |
| 枚举取值受限 | 不保证 | 是 | 是 |
| 金额不超过订单金额 | 不能 | 不能 | 是 |
| 条款适用于该商品类目 | 不能 | 不能 | 是 |
| 数值范围、字符串长度 | 不能 | <u>多数实现不支持</u> | 是 |

**Schema 管形状，代码管业务；两者不能互相替代。**

## 工作原理

1. **先定消费方需求**：谁读这个 JSON、读哪些字段、缺字段会怎样；字段越少越好。
2. **设计形状**：对象根节点、字段类型、枚举、数组元素类型；可选字段用“类型 + null 联合”表达，而不是省略字段。
3. **写 Schema**：根节点用对象，所有属性列入 `required`，并设置 `additionalProperties: false`。
4. **声明严格约束**：请求里把 Schema 放进 `response_format`（Chat Completions）或 `text.format`（Responses API），并设 `strict: true`。
5. **服务端校验**：解析 JSON，再检查枚举、必填、未知字段，最后跑业务规则。
6. **处理拒绝**：模型可能返回 `refusal` 而不是 JSON，这是正常结果，要有对应分支。
7. **版本化**：Schema 变更等同接口变更，下游要能兼容或同步升级。

截至 2026-10-19，Azure OpenAI 文档指出严格模式有一组必须遵守的约束：所有字段都要出现在 `required` 中、对象要设 `additionalProperties: false`、Schema 最多 100 个对象属性且嵌套不超过 5 层；不支持的常见关键字包括 `minLength`、`maxLength`、`pattern`、`format`、`minimum`、`maximum`、`multipleOf`、`minItems`、`maxItems`、`uniqueItems` 等。另外，结构化输出不支持并行工具调用，需要把 `parallel_tool_calls` 设为 `false`。

## 架构与选型

| 方案 | 适用 | 优点 | 不适用/代价 |
| --- | --- | --- | --- |
| 自由文本 + 正则解析 | 原型、一次性脚本 | 零依赖 | 解析失败率高，格式漂移无法控制 |
| JSON 模式 | 只需要“能 parse” | 简单 | 字段缺失、类型错误仍会发生 |
| 严格 JSON Schema | 下游系统消费、字段固定 | 形状可靠，可自动校验 | Schema 子集限制，枚举变更需同步下游 |
| 工具调用参数（function 参数 Schema） | 需要模型“决定调用哪个动作” | 与动作绑定，天然结构化 | 与并行调用、流式组合有额外约束 |
| 语法约束（如语法规则工具） | 需要非 JSON 的严格格式 | 可约束任意文法 | 依赖特定厂商能力，可读性差 |

选型依据：**下游是程序就上严格 Schema，下游是人就看文本质量**；需要“模型自选动作”时用工具参数 Schema，而不是把动作名塞进自由文本。

## 最小示例

先看 Schema（合法 JSON，字段含义见下方说明）：

```json
{
  "type": "object",
  "required": ["decision", "refund_amount", "policy_ids", "needs_human", "reply_text"],
  "additionalProperties": false,
  "properties": {
    "decision": {"type": "string", "enum": ["refund", "exchange", "repair", "reject", "ask_more"]},
    "refund_amount": {"type": ["number", "null"]},
    "policy_ids": {"type": "array", "items": {"type": "string"}},
    "needs_human": {"type": "boolean"},
    "reply_text": {"type": "string"}
  }
}
```

字段说明：`decision` 用英文枚举而非中文自由文本，避免同义表述导致下游无法匹配；`refund_amount` 用 `["number","null"]` 联合类型表达“非退款场景没有金额”，因为严格模式要求字段必须存在，不能靠省略实现可选；`policy_ids` 是数组，允许一条答复引用多个条款；`needs_human` 是布尔，供人工队列直接判断。

下面是标准库校验器，验证“形状正确”这件事在服务端如何兜底：

```python
import json

SCHEMA = {
    "type": "object",
    "required": ["decision", "refund_amount", "policy_ids", "needs_human", "reply_text"],
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string", "enum": ["refund", "exchange", "repair", "reject", "ask_more"]},
        "refund_amount": {"type": ["number", "null"]},
        "policy_ids": {"type": "array", "items": {"type": "string"}},
        "needs_human": {"type": "boolean"},
        "reply_text": {"type": "string"},
    },
}
# 把 Schema 里的类型名映射到 Python 类型，供运行时判断
TYPES = {"string": str, "number": (int, float), "boolean": bool, "array": list, "null": type(None)}

def check(payload, schema=SCHEMA):
    errors = []
    for key in schema["required"]:
        if key not in payload:
            errors.append(f"缺少必填字段: {key}")
    if not schema.get("additionalProperties", True):
        for key in payload:
            if key not in schema["properties"]:
                errors.append(f"未知字段: {key}")
    for key, rule in schema["properties"].items():
        if key not in payload:
            continue
        value = payload[key]
        allowed = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
        if not any(isinstance(value, TYPES[t]) for t in allowed):
            errors.append(f"{key} 类型不符: 期望 {allowed}")
            continue
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"{key} 不在枚举内: {value}")
    return errors

good = {
    "decision": "refund", "refund_amount": 800.0, "policy_ids": ["P-03"],
    "needs_human": True, "reply_text": "订单 QK-2026-004821 符合七天无理由退货，金额 800 元，需人工审核。",
}
bad = {
    "decision": "部分退款", "refund_amount": "800", "policy_ids": ["P-03"],
    "needs_human": True, "reply_text": "…", "confidence": 0.92,
}
for name, p in [("A", good), ("B", bad)]:
    errs = check(p)
    print(f"payload {name}:", "通过" if not errs else "失败 → " + "; ".join(errs))
```

预期输出：

```text
payload A: 通过
payload B: 失败 → 未知字段: confidence; decision 不在枚举内: 部分退款; refund_amount 类型不符: 期望 ['number', 'null']
```

关键设计选择：错误信息里带上字段名和实际值，排查时不用重新构造请求。<u>注意 Python 里 `bool` 是 `int` 的子类，`isinstance(True, (int, float))` 为真</u>，所以像 `refund_amount` 这类数字字段若真要拒绝布尔值，需要额外判断 `not isinstance(value, bool)`。

## 动手实验

**前置条件**：Python 3.9+，无需 API Key。

**步骤**：

1. 保存代码为 `schema_check.py`，运行并核对两条输出。
2. 构造 payload C：`decision` 正确但缺 `policy_ids`，确认报“缺少必填字段”。
3. 构造 payload D：`needs_human` 传字符串 `"true"`，确认报类型不符。
4. 在 `check()` 之后追加一条业务校验函数（不是改 Schema）：`refund_amount > 500` 时 `needs_human` 必须为 `true`。
5. 用 payload A（800 元且 `needs_human: true`）与一条把 `needs_human` 改为 `false` 的变体验证规则生效。

**预期结果**：第 2、3 步各自报出对应的结构性错误；第 4 步说明<u>业务规则必须自己写在校验层，Schema 无法表达“条件依赖”</u>；第 5 步变体应被业务校验拦截。

**验证方法**：把 `additionalProperties` 改为 `true`，重新跑 payload B，确认“未知字段”不再报错——这验证了严格性来自该标志位。

**清理方法**：删除 `schema_check.py`，不产生外部资源。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 模型返回的 JSON 少字段 | 未开启严格模式，字段未全部 required | 检查请求体是否 `strict: true` | 所有字段列入 required，可选字段用 null 联合 |
| 加了 `maxLength` 但长度限制无效 | 该关键字不被严格模式支持 | 查厂商“支持的关键字/子集”文档 | 改用代码校验或提示词约束 |
| 输出多出一个 `confidence` 字段导致入库失败 | 未设 `additionalProperties: false` | 打印 Schema 对象 | 关掉额外属性，并在服务端拒绝未知字段 |
| 开启 Schema 后工具调用报错 | 结构化输出与并行工具调用不兼容 | 查看是否发送了多个并行调用 | 设 `parallel_tool_calls: false` |
| Schema 改了但下游解析全崩 | 枚举或字段名变更未同步消费方 | 对比 Schema 版本与下游常量表 | Schema 版本化，变更走接口兼容流程 |

## 安全与生产注意事项

**<u>严格 Schema 会让“合法但危险”的输出直接流入下游。</u>** 例如 `decision: "refund"`、`refund_amount: 99999` 完全符合 Schema，但金额远超订单金额。必须在退款服务侧做额度与归属校验，不能因为“Schema 通过”就放行。

**<u>把枚举值当作权限判断依据可能被模型误选。</u>** 模型输出的是分类结果，不是授权决定；高额退款仍要人工确认，且确认人要有对应角色。

此外，`reply_text` 是自由文本，可能包含提示注入诱导模型写出的内容；对外展示前需过滤，且不要把它直接拼进其他系统提示词。

## 本课总结

- 结构化输出把“格式”从提示词问题变成契约问题。
- 严格模式要求字段全部必填、禁止额外属性，可选字段靠 null 联合表达。
- 主流实现只支持 JSON Schema 子集，长度、范围类关键字通常要代码补。
- Schema 保证形状，业务规则（额度、归属、适用性）必须自行校验。
- Schema 是接口，变更要版本化并同步下游。

## 思考题

如果下游要求“金额字段必须是字符串且带两位小数”，而严格模式不支持 `pattern` 与 `multipleOf`，你会怎么设计？请给出两种方案并说明取舍。

参考思路：方案一是让 Schema 用 `string` 输出，服务端用正则与定点数转换校验，错误即重试；方案二是 Schema 用 `number`，服务端格式化成字符串后再出站。前者契合下游契约但校验成本在服务端；后者简单但多一次转换，需明确谁负责格式化。

## 小测

1. JSON 模式与严格 JSON Schema 的核心差别是什么？
2. 为什么可选字段要用 `["string","null"]` 而不是从 `required` 里去掉？
3. `additionalProperties: false` 的作用是？  
   A. 禁止字段为空　B. 禁止出现未定义字段　C. 强制字段顺序　D. 限制字符串长度
4. 下列哪项必须由代码校验而不能只靠 Schema？  
   A. 字段是否存在　B. 取值是否在枚举内　C. 金额是否超过订单金额　D. 是否为数组
5. 场景题：模型返回了合法 Schema 的输出，但 `policy_ids` 里写的条款编号在政策库里不存在。这说明什么、接下来怎么改？

## 答案与解析

1. JSON 模式只保证可解析为 JSON，字段名、类型、枚举都可能不符；严格 JSON Schema 让模型按给定 Schema 生成，形状可靠，但仍不校验业务含义。
2. 因为严格模式要求所有字段必填，去掉 `required` 会导致校验失败或字段缺失；用 null 联合既满足“必填”，又能表达“此场景无值”，下游还能显式判断 null。
3. **B。** 它控制对象能否包含 Schema 未声明的键。A 与空值无关；C 顺序由 Schema 属性顺序决定而非该标志；D 属于字符串关键字。
4. **C。** 金额上限是业务条件，需要查询订单数据后比较。A、B、D 都是结构约束，Schema 层面即可表达。
5. 说明只校验了形状，没有校验引用完整性。应在服务端增加“条款编号存在于政策库且适用于该商品类目”的校验；若不通过则触发修复或重试，并把该样本加入评测集，同时考虑在提示词中直接提供可选的条款编号列表（枚举化）来降低错误率。

## 延伸阅读与下一课

- Azure OpenAI 结构化输出（`strict`、必填字段、`additionalProperties: false`、支持与不支持的关键字、并行工具调用限制）：[learn.microsoft.com/.../how-to/structured-outputs](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/structured-outputs)，复核日期 2026-10-19。
- JSON Schema 官方文档（`type` 关键字与类型映射）：[json-schema.org/understanding-json-schema/reference/type](https://json-schema.org/understanding-json-schema/reference/type)，复核日期 2026-10-19。
- Azure OpenAI 推理模型文档中的语法约束工具（`lark_tool`，用于非 JSON 的严格输出格式）：[learn.microsoft.com/.../how-to/reasoning](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/reasoning)，复核日期 2026-10-19。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[Prompt 模板、变量与版本管理](04-prompt-templates-and-versioning.md)。
- 下一课：[输出解析、校验、修复与重试](06-output-parsing-validation-and-repair.md)。
