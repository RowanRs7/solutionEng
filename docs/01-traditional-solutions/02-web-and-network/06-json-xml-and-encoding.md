---
title: JSON、XML、CSV 与字符编码
slug: json-xml-and-encoding
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 50m
prerequisites:
  - https-tls-and-certificates
outcomes:
  - 比较 JSON、XML、CSV 的结构与类型表达能力，并为给定接口选出格式
  - 写出金额、前导零和中文都不丢信息的序列化与回读代码
  - 从原始字节和 Content-Type 定位一次乱码的引入点
last_reviewed: 2026-10-19
---

# JSON、XML、CSV 与字符编码

## 为什么需要学习

晴空商城的退款每天走四条路：支付商回调是 JSON，仓储 WMS 只认 XML，财务要一份能用 Excel 打开的 CSV 对账单，客服页面要展示含地址和备注的退款详情。上线三个月后，工单集中在三类现象上：对账差 0.01 元；Excel 里的订单号 `0012345` 变成了 `12345`，无法与仓储匹配；一条备注含 emoji 的退款导致整批导出失败。

这三类问题都没有异常堆栈指向业务代码，因为数据在格式边界上已经悄悄变了。**格式与编码的错误通常不是“报错退出”，而是“静默改错”**，只能靠提前设计边界来防。

> **核心结论：** 选格式就是选哪些信息能被无损表达，定编码就是定字节如何变成字符；两者都在系统边界上，出错时不报警，只改数据。

## 学习目标

完成本课后，你能够：

- 比较 JSON、XML、CSV 在结构、类型和校验能力上的差异，并说明各自适用场景。
- 为含金额、前导零编号和中文的退款记录写出无损的序列化与回读代码。
- 区分“字节解码失败”和“语法解析失败”，并按顺序定位乱码的引入点。
- 列出 CSV 至少四个静默陷阱，并给出对应的导出约束。

## 前置知识

- 回看上一课：[HTTPS、TLS 与证书](05-https-tls-and-certificates.md)。
- 知道 HTTP 报文由起始行、Header 和 Body 组成，`Content-Type` 描述 Body 的格式。
- 知道计算机用字节存储文本，一个字符可能占多个字节。
- 本机可用 `python3`，实验只用标准库，不需要网络。

## 业务场景

晴空商城的退款服务要把同一批退款结果交付给三个消费方：

| 消费方 | 需要格式 | 硬约束 |
| --- | --- | --- |
| 支付商回调接收 | JSON | 金额以字符串传输，币种单独字段 |
| 仓储 WMS | XML（SOAP 1.1） | 老系统只解析 XML，字段顺序受 `sequence` 约束 |
| 财务对账 | CSV | 双击用 Excel 打开并能直接求和 |
| 客服工单页面 | HTML 片段 | 备注可能含换行、逗号、引号和 emoji |

架构师要回答的不是“哪个格式更好”，而是一份内存中的退款记录为什么不能“随便 dump 成三种格式”。贯穿本课的例子是退款单 `R-20261019-0007`：金额 19.90 元、订单号 `0012345`、备注“晴空, 已退款”。这三个值分别踩中精度、前导零和分隔符三个坑。

## 核心概念

- *序列化*：把内存中的结构化数据转成可传输或可存储的字节序列；*反序列化*是反向过程。
- *模式（schema）*：对字段名、类型、必填和取值范围的显式约定，可被机器校验。
- *字符集*：字符到码点的映射，如 Unicode；*编码*：码点到字节的映射，如 UTF-8。
- *BOM*：字节顺序标记，UTF-8 下是 `EF BB BF` 三个字节，写在文件开头。
- *规范化*：把视觉相同、码点不同的字符统一，例如 `é` 的合成与分解两种写法。
- *类型鸿沟*：文本格式里只有字符，没有小数和日期，类型是双方约定出来的。

| 维度 | JSON | XML | CSV |
| --- | --- | --- | --- |
| 结构 | 对象与数组嵌套 | 元素树 + 属性 + 命名空间 | 扁平行列，无嵌套 |
| 类型 | 字符串、数字、布尔、null | 全是文本，类型靠 schema | 全是文本，无类型 |
| 模式校验 | 需外部 JSON Schema | XSD、DTD、RELAX NG | 无标准，靠表头约定 |
| 注释 | 不允许 | 允许 | 无字段概念 |
| 元数据 | 基本没有，靠 Header | 属性、命名空间、声明 | 仅表头一行 |
| 体积 | 小 | 大，标签重复 | 最小 |
| 典型用途 | REST API、事件、配置 | 企业集成、SOAP、文档 | 报表、批量导入导出 |

**本课最重要的判断：格式的“类型”是约定，不是保证。**<u>JSON 里写的 19.90 到了接收端可能变成 1989.9999999999998 分。</u>

## 工作原理

一条退款记录从内存到另一个系统要穿过六层，每层都可能改变数据：

1. **编码**：应用把字符串按 UTF-8 编码成字节。这一层出错，后面全是乱码。
2. **声明**：发送方在 `Content-Type` 里写 `application/json; charset=utf-8`。声明与实际字节不符，是最常见的乱码来源。
3. **传输**：字节经 HTTP 传输。HTTP 是二进制安全的，本身不改变内容。
4. **解码**：接收方按声明（无声明时按猜测）把字节还原成字符。用错编码时，UTF-8 字节按 GBK 解释通常**不报错**，只得到乱码；反向错配多半直接抛异常。
5. **语法解析**：JSON 解析器检查引号、逗号、转义；XML 解析器检查标签闭合与实体；CSV 解析器按引号和分隔符切分。
6. **类型映射**：解析器把 `"19.90"` 或 `19.90` 变成目标语言的值。精度、前导零和空值语义都在这一步被决定。

JSON 有三条语法边界值得记住：不允许注释；数字精度没有规定（实现多用 IEEE 754 双精度）；对象里重复键的行为未定义。XML 把结构放进元素树，属性适合放元数据，命名空间解决同名冲突，实体引用带来表达力也带来 XXE 风险。CSV 最简单：RFC 4180 只是约定，没有类型也没有嵌套，字段含分隔符时用双引号包裹，字段内的双引号写两次。

## 架构与选型

| 场景 | 建议格式 | 理由 | 不适用原因 |
| --- | --- | --- | --- |
| 前后端 API、服务间事件 | JSON | 结构清晰、体积小、各语言内置解析 | 需要混合内容文档或命名空间隔离时不合适 |
| 对接老 ERP/WMS、SOAP | XML | 对方只支持；XSD 能做严格契约 | 新系统之间用 XML 通常只增加解析复杂度 |
| 财务对账、批量导入导出 | CSV | 表格工具直接打开，可肉眼核对 | 需要嵌套结构或类型保证时不合适 |
| 大数据量交换 | CSV 或 JSON Lines | 可按行流式处理，不必整体载入内存 | 需要跨行引用时不合适 |
| 人工阅读的配置 | JSON | 结构明确、工具链成熟 | 含大量重复标签时不如 XML 严谨，也不如 YAML 省字符 |

选型顺序：(1) 消费方已经固定了什么格式；(2) 是否必须携带类型与精度；(3) 是否需要机器可校验的契约；(4) 数据量和是否要求流式；(5) 是否要人直接打开。前两条通常已经决定答案，剩下的只是权衡。

## 最小示例

环境：Python 3.8+，只用标准库。下面三段代码的输出均已实际运行。

**示例 1：金额精度取决于反序列化策略**

```python
import json
from decimal import Decimal

raw = '{"refund_id": "R-20261019-0007", "amount": 19.90}'
print(json.loads(raw)["amount"] * 100)                       # 默认按二进制浮点还原，乘 100 暴露误差
print(json.loads(raw, parse_float=Decimal)["amount"] * 100)  # 显式按十进制还原，结果精确
```

预期输出：

```text
1989.9999999999998
1990.00
```

设计意图：JSON 规范没有规定数字精度，`parse_float` 是把“约定”变成“保证”的开关。生产接口更稳妥的做法是**金额用字符串传输，并在 schema 里约束格式**。

**示例 2：CSV 的引号由库处理，类型不由库处理**

```python
import csv, io

buf = io.StringIO()
writer = csv.writer(buf, lineterminator="\n")           # 固定换行符，避免 Windows 下变成 \r\n
writer.writerow(["order_id", "amount", "note"])
writer.writerow(["0012345", "19.90", "晴空, 已退款"])  # 备注含逗号，由 writer 决定是否加引号
print(buf.getvalue(), end="")
rows = list(csv.reader(io.StringIO(buf.getvalue())))
print(rows[1][0], type(rows[1][0]).__name__)            # 回读仍是字符串，前导零在 Python 侧安全
```

预期输出：

```text
order_id,amount,note
0012345,19.90,"晴空, 已退款"
0012345 str
```

设计意图：`csv` 模块保证语法无损，但<u>Excel 打开时仍会按单元格类型把 0012345 变成 12345</u>。保真只能靠导出侧约定，例如写出 `="0012345"`（这是 Excel 专属写法，不是 CSV 标准），或直接改用 XLSX。

**示例 3：乱码和 BOM 的两个方向**

```python
text = "晴空商城"
print(text.encode("utf-8").hex())          # 4 个汉字共 12 字节，UTF-8 是变长编码
print(text.encode("utf-8").decode("gbk"))  # UTF-8 字节按 GBK 解释：不报错，得到乱码
try:
    text.encode("gbk").decode("utf-8")     # 反向错配：大多数情况直接抛异常
except UnicodeDecodeError as error:
    print(error)
```

预期输出：

```text
e699b4e7a9bae59586e59f8e
鏅寸┖鍟嗗煄
'utf-8' codec can't decode byte 0xc7 in position 0: invalid continuation byte
```

BOM 方向的错误更隐蔽：带 BOM 的 JSON 若先用 `utf-8` 读成字符串再解析，会报 `Unexpected UTF-8 BOM (decode using utf-8-sig)`。CSV 带 BOM 时，第一个字段名会变成 `\ufeffrefund_id`，下游按名字取值的代码全部落空。

## 动手实验

任务：为退款导出做一次“往返无损”验证，确认金额、前导零和中文都能原样回来。

前置条件：本机有 `python3`；不需要网络；所有文件放在 `/tmp/dsh-encoding-lab`。

步骤：

1. 建目录，写入导出脚本 `refund_export.py`：

```python
import csv, json
from decimal import Decimal
from pathlib import Path

out = Path("/tmp/dsh-encoding-lab")  # 放在工作区外，便于整体清理
record = {
    "refund_id": "R-20261019-0007",
    "order_id": "0012345",
    "amount": Decimal("19.90"),
    "note": "晴空, 已退款",
}

# JSON：金额显式转字符串，避免消费端按双精度还原
(out / "refund.json").write_text(
    json.dumps(record, ensure_ascii=False, default=str, indent=2),
    encoding="utf-8",  # 显式指定，不依赖系统默认编码
)

# CSV：utf-8-sig 写出 BOM，Excel 才不会把中文按本地编码解释
with (out / "refund.csv").open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(record.keys())
    writer.writerow([str(value) for value in record.values()])  # 全部按字符串写出
```

2. 运行 `python3 /tmp/dsh-encoding-lab/refund_export.py`。
3. 查看 JSON：`cat /tmp/dsh-encoding-lab/refund.json`。
4. 查看前三个字节：`python3 -c "print(open('/tmp/dsh-encoding-lab/refund.csv','rb').read(3))"`。
5. 用正确编码回读：`python3 -c "import csv;print(list(csv.reader(open('/tmp/dsh-encoding-lab/refund.csv',encoding='utf-8-sig',newline=''))))"`。
6. 故意把第 5 步的 `utf-8-sig` 改成 `utf-8` 再跑一次。

预期结果：

- JSON 中 `"amount": "19.90"`、`"order_id": "0012345"`，中文原样保留。
- 第 4 步输出 `b'\xef\xbb\xbf'`。
- 第 5 步首个表头是 `refund_id`。
- 第 6 步首个表头变成 `\ufeffrefund_id`，数据行本身仍然正确。

验证方法：比对回读的 `order_id` 与源值是否逐字符相等；`amount` 回读后乘 100 应精确等于 1990；用 `file --mime refund.csv` 确认 `charset=utf-8`。

清理方法：`rm -rf /tmp/dsh-encoding-lab`。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 对账金额差 0.01 元 | 金额以 JSON 数字传输，被双精度浮点还原 | 用 `Decimal` 反序列化后对比，或用 `repr()` 打印原值 | 金额改为字符串，或改用最小货币单位的整数 |
| 订单号前导零消失 | Excel 把单元格识别为数字 | 用纯文本编辑器打开同一 CSV 对比 | 导出侧加 `="..."`，或改用 XLSX 并设文本格式 |
| Excel 打开中文全是乱码 | 文件是 UTF-8 但没有 BOM，Excel 按本地编码解释 | `read(3)` 检查是否有 `EF BB BF` | 用 `utf-8-sig` 写出，另留无 BOM 版本给程序读 |
| 页面出现「锟斤拷」 | 原始字节被错误解码后又被按 UTF-8 重新编码 | 从最上游抓原始字节，逐层打印 `hex()` | 全链路统一 UTF-8，非法字节显式报错 |
| CSV 行数比业务记录多 | 字段内含换行或逗号，且未按引号解析 | 用 `csv` 模块读取而非 `split(",")` | 统一用标准 CSV 解析器，导出侧强制加引号 |
| XML 解析报实体未定义 | 报文用了 DTD 自定义实体，或解析器关闭了实体处理 | 查看报文头部有无 `<!DOCTYPE` | 禁用外部实体，用 XSD 校验代替 DTD |

## 安全与生产注意事项

**<u>不要用默认配置解析外部来源的 XML。</u>**XXE 会通过 `<!ENTITY>` 读取服务器本地文件或发起内网请求，“十亿笑声”式实体展开则能在解析阶段耗尽 CPU 和内存。缓解措施是显式关闭 DTD 与外部实体解析，并对报文大小设上限。

**<u>导出的 CSV 会被 Excel 当作公式执行。</u>**以 `=`、`+`、`-`、`@` 开头的单元格在打开时可能被求值或触发外部链接，攻击者只要在备注字段植入这种内容就能利用。缓解措施是导出前对首字符转义（前置单引号）或强制按文本写出，并对导出内容做白名单过滤。

另外两条常规要求：<u>编码转换失败时必须显式报错</u>，`errors="ignore"` 会把错误字符静默删掉，比乱码更难追查；日志可以记录格式、编码和字节长度，但不要把整段含个人信息的备注落盘。

## 本课总结

- **格式选择决定哪些信息能无损表达，编码决定字节如何变成字符。**
- JSON 表达结构但不保证精度；金额和有格式要求的 ID 应按字符串约定，并用 schema 校验。
- XML 适合企业集成和需要命名空间、严格 schema 的场景，代价是体积和解析风险。
- CSV 没有类型，前导零、公式注入、字段内换行都必须在导出侧处理。
- 排查乱码的顺序是：原始字节 → 声明的 charset → 解码结果 → 解析结果，逐层打印，不要从页面往回猜。

## 思考题

财务要求“CSV 双击就能直接求和”，工程要求“数据必须机器可校验、金额精确到分”。这两个要求能同时满足吗？请写出你的方案、需要谁做出让步，以及你会用什么证据验证。

参考思路：把“机器可校验的精确数据”和“给人看的报表”拆成两份产物：接口与存档用 JSON（金额用整数分），报表用 XLSX 或 CSV 并明确标注仅供展示。若必须只交付 CSV，则约定金额列为纯数字、另附 `currency` 与 `amount_cents` 列，并请财务确认对账口径。验证方式是对同一批退款同时生成两种产物并逐笔比对。

## 小测

1. JSON 里写 `19.90`，接收方一定拿到十进制 19.90 吗？为什么？
2. CSV 字段内同时含逗号和双引号，标准写法是什么？
3. 把 UTF-8 字节按 GBK 解码，通常报错还是得到乱码？为什么？
4. 为什么说“JSON 支持日期类型”是错的？
5. 场景题：客服导出的 CSV 中，订单号在 Excel 里丢失前导零，备注列里还有一条以 `=` 开头的内容。作为架构师，你会先改哪一处，为什么？

## 答案与解析

1. **不一定。**规范只规定语法，不规定数字精度；多数实现映射为 IEEE 754 双精度，19.90 无法精确表示，乘 100 会得到 1989.9999999999998。正确做法是用字符串传输并约定格式。
2. 整个字段用双引号包裹，字段内的双引号写成两个：`"他说""已退款"", 请注意"`。只转义逗号、或整段不加引号，都会让列错位。
3. **通常得到乱码，而且不报错。**UTF-8 多字节序列的字节值多数能落到 GBK 的合法码位上，解码器没有理由拒绝，于是产出“鏅寸┖鍟嗗煄”这类结果。反向（GBK 字节按 UTF-8 解）更容易直接抛异常，因为字节不构成合法 UTF-8 序列。
4. JSON 只有字符串、数字、布尔、null、对象、数组六种值；日期只能以字符串约定（如 RFC 3339），解析和校验责任在应用层。
5. 先修公式注入。前导零丢失属于显示与匹配问题，对账时会被发现；以 `=` 开头的单元格在打开瞬间就可能执行，属于安全事故。修复顺序按“不可逆风险优先”，但两处都要改。

### 动手实验参考

合格完成应满足：JSON 中金额是字符串而非数字；CSV 前三个字节是 `EF BB BF`；用 `utf-8-sig` 回读时首列名为 `refund_id`，用 `utf-8` 回读时变成 `\ufeffrefund_id`；`order_id` 回读值与源值逐字符相等。若你的 CSV 没有 BOM，检查写出时是否用了 `encoding="utf-8"` 而不是 `utf-8-sig`。

## 延伸阅读与下一课

- [RFC 8259：JSON 数据交换格式](https://www.rfc-editor.org/rfc/rfc8259)
- [RFC 4180：CSV 的通用格式与 MIME 类型](https://www.rfc-editor.org/rfc/rfc4180)
- [RFC 3629：UTF-8 编码](https://www.rfc-editor.org/rfc/rfc3629)
- [W3C：XML 1.0（第五版）](https://www.w3.org/TR/xml/)
- [MDN：JSON](https://developer.mozilla.org/zh-CN/docs/Web/JavaScript/Reference/Global_Objects/JSON)
- [OWASP：XML 外部实体（XXE）防护速查表](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html)

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[HTTPS、TLS 与证书](05-https-tls-and-certificates.md)。
- 下一课：[CORS、CSRF 与浏览器安全](07-cors-csrf-and-browser-security.md)。
