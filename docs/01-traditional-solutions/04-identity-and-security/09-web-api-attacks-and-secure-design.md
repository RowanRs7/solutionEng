---
title: 常见 Web/API 攻击与安全设计
slug: web-api-attacks-and-secure-design
module: traditional-solutions
stage: design
type: core
difficulty: intermediate
duration: 60m
prerequisites:
  - secrets-and-key-management
outcomes:
  - 把一次 API 请求拆成输入、身份、出口三段，指出每段的信任边界并说明判定应落在哪一层
  - 为注入、越权、SSRF、凭据填充各写一条可执行的验证请求，并让四组样例在代码层被拒
  - 区分网关粗筛与代码级强制的覆盖范围，指出只加 WAF 规则时会漏掉哪类攻击并给出补齐方式
last_reviewed: 2026-10-19
---

# 常见 Web/API 攻击与安全设计

## 为什么需要学习

晴空商城开放 Partner API 后，品牌商 ERP 拉订单、物流回传运单、供应商上传发票一夜之间都接进来了。四个月内发生四件事：搜索框被 `' OR '1'='1` 打出全量顾客手机号；某品牌商把 `/api/orders/8801` 改成 `8802` 就读到别人的订单；发票预览的 `file_url` 参数被指向 `169.254.169.254`，服务器把云上临时凭据交了出去；客服后台在一周内出现 4 万次登录尝试，用的全是别处泄露的邮箱密码组合。

四件事的共同点不是“代码写得差”，而是**系统把不该信的东西当成了事实**：输入、订单主键、URL 与密码各自被当成了证据。

> **核心结论：** Web/API 安全设计的实质，是逐个信任边界回答三个问题——这段输入凭什么可信、这个身份凭什么代表本人、这次出网凭什么被允许。

## 学习目标

完成本课后，你能够：

- 把一次 API 请求拆成输入、身份、出口三段，指出每段的信任边界来源。
- 为注入、越权、SSRF、凭据填充各写一条可复现的验证请求，并说明判定必须落在哪一层。
- 判断“只在网关加 WAF 规则”能挡住什么、漏掉什么，并给出补齐方式。
- 用 Python 3 标准库跑出四组攻击样例被拒的输出，解释每条判定为何放在那个位置。

## 前置知识

- 回看上一课：[Secret、证书与密钥管理](08-secrets-and-key-management.md)。
- 知道 HTTP 方法、状态码与 JSON 报文结构，能读懂一段请求。
- 知道认证（你是谁）与授权（你能做什么）的区别，以及 `401` 与 `403` 的使用场合。
- 能读懂 Python 3 的 `sqlite3`、`urllib.parse` 与 `dataclass`。

## 业务场景

Partner API 的三类调用方各有诉求：品牌商 ERP 需要按租户拉订单并支持排序；物流方回调运单状态时传入一个回调地址；供应商上传发票后要按 URL 预览。加上已有的客服后台与顾客端，同一套接口同时承载内部员工、外部企业和匿名顾客。

安全评审提出四个必须书面回答的问题：

- 订单列表支持“按金额排序”，前端把字段名传给后端，这个参数怎么处理？
- `/api/orders/{id}` 已经要求登录，为什么还会读到别家的订单？
- 预览服务要抓外部地址，怎么证明它抓不到内网？
- 客服后台的登录接口被撞库，按 IP 限速为什么没用？

四个问题分别对应注入、越权、SSRF 和凭据填充。

## 核心概念

*注入*指把不可信输入拼进命令、SQL 或模板后，输入的解释权从数据变成了语法。*参数化查询*把语句结构与数据分两路发送，让引号永远只是字符。*越权*分两种：*横向越权*是同一角色越过数据归属，看别人的订单；*纵向越权*是低权限角色执行高权限动作，比如客服调用打款接口。

*SSRF*（服务端请求伪造）指攻击者让服务器替他访问本不该碰的地址，典型目标是云元数据与内网管理台。*凭据填充*（credential stuffing）用别处泄露的账号密码批量试登录，不破解密码，只赌复用。*信任边界*是数据从不可信变可信的那条线；*纵深防御*指同一条线放多层控制，任一层失效仍有兜底。

| 攻击 | 被误用的信任 | 有效控制 | 看着有用但不够的控制 |
| --- | --- | --- | --- |
| 注入 | “输入只是数据” | 值与语句分离；标识符走白名单 | 转义函数、关键词黑名单 |
| 横向越权 | “登录即有权” | 对象级授权 + 数据层归属过滤 | 前端隐藏入口、加长主键 |
| 纵向越权 | “角色名可信” | 服务端权限集合判定 | 菜单权限、隐藏按钮 |
| SSRF | “URL 是资源地址” | 协议 + 主机 + 解析地址三查，出口代理 | 只校验 `https://` 前缀 |
| 凭据填充 | “密码对就是本人” | 按账号限速、泄露口令校验、MFA | 只按 IP 限速、图形验证码 |

## 工作原理

一次请求的安全判定沿数据流依次发生，顺序本身就是设计：

1. **边界外粗筛**：CDN 或 WAF 按体积、方法与明显 payload 拦截，只挡噪声，不是唯一防线。
2. **建立身份**：网关验签令牌、检查有效期，从可信声明取 `sub`、`tenant`、`roles`；请求体与查询串无权覆盖身份。
3. **授权到对象**：判定从“这个角色能读订单”下沉到“这个角色能读这一条订单”，归属来自服务端按主键查出的记录。
4. **输入解析**：值一律走占位符，列名、排序方向、过滤维度等无法参数化的部分映射到白名单，未命中即回退默认值。
5. **出网收口**：所有外部调用经统一出口代理，逐跳校验协议、主机与解析地址，禁用内网段与自动重定向。
6. **输出与提示**：错误信息统一，不区分“账号不存在”与“密码错误”；日志脱敏，令牌与密码不入库。
7. **留痕与度量**：记录判定结果、原因码、命中策略版本；对 4xx 率、登录失败率、出网拒绝数打点告警。

四类攻击分别在这条链上断掉不同的一环：注入断在第 4 步，越权断在第 2、3 步，SSRF 断在第 5 步，凭据填充断在第 2、6、7 步。**只在一环补控，等于默认其他环永远不出错。**

## 架构与选型

| 控制手段 | 主要挡住 | 适用条件 | 不适用或需注意 |
| --- | --- | --- | --- |
| WAF / CDN 规则 | 已知 payload、扫描器流量 | 有公网入口且可承受误杀 | 表达不了对象归属，加密或分块请求易绕过 |
| 网关统一认证与租户上下文 | 伪造身份、缺租户标识 | 服务间调用统一入口 | 直连服务的旁路必须一并关闭 |
| 参数化查询 / ORM 绑定 | 值注入 | 所有数据库访问 | 手写 `text()`、`raw()` 会绕开绑定 |
| 对象级授权中间件 | 横向越权 | 资源统一按主键加载 | 批量与导出接口需单独覆盖 |
| 出口代理 + 白名单 | SSRF、数据外带 | 服务需要访问外部 API | 白名单维护成本高，需自助申请与到期复核 |
| 泄露口令校验 + MFA | 凭据填充、账号接管 | 有账号体系的后台与顾客端 | 顾客端 MFA 需权衡转化率，可先高风险场景 |
| 统一错误信息与审计 | 账号枚举、事后追溯 | 全部认证接口 | 统一提示不能替代限速 |

选型判断顺序：**先问“这段数据会不会进入解释器”（注入），再问“这次访问落在哪一条记录上”（越权），然后问“要不要出网”（SSRF），最后问“身份怎么被证明”（凭据）**。前两问是设计必答项。

边界：WAF 不承担任何授权职责；随机化主键只提高猜测成本，不构成访问控制；出口白名单与网络层默认拒绝是叠加关系。

## 最小示例

问题：用 Python 3 标准库复现四组攻击样例，并让每一条都被明确拒绝。环境为 Python 3.9+，不联网、不连数据库，SQL 使用内存库。

```python
import ipaddress
import sqlite3
import urllib.parse
from dataclasses import dataclass

# ---------- ① 注入：值走占位符，标识符走白名单 ----------
conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, tenant TEXT, amount INTEGER)")
# 建表数据也用占位符，顺带说明占位符不只用于查询
conn.executemany("INSERT INTO orders VALUES (?, ?, ?)",
                 [(1, "brand-a", 300), (2, "brand-b", 8800)])
payload = "brand-a' OR '1'='1"


def unsafe_find(tenant):
    # 反面示例：把输入直接拼进 SQL，引号被数据库当成语法而非数据
    sql = f"SELECT id, tenant, amount FROM orders WHERE tenant = '{tenant}'"
    return conn.execute(sql).fetchall()


def safe_find(sort_field, tenant):
    # 列名与排序方向无法用占位符替代，只能映射到固定白名单，未命中回退默认列
    columns = {"amount": "amount", "id": "id"}
    order_by = columns.get(sort_field, "id")
    # 值一律走占位符：驱动把整串当数据发送，引号失去语法意义
    sql = f"SELECT id, tenant, amount FROM orders WHERE tenant = ? ORDER BY {order_by}"
    return conn.execute(sql, (tenant,)).fetchall()


print(f"注入-拼接: 命中 {len(unsafe_find(payload))} 行")
print(f"注入-参数化: 命中 {len(safe_find('amount', payload))} 行")

# ---------- ② 越权：判定必须落到具体对象 ----------
@dataclass(frozen=True)
class Subject:
    user_id: str
    tenant: str          # 来自服务端验签后的令牌，不接受请求参数覆盖
    roles: tuple


def can_read_order(subject, order):
    # 先回答“这条数据属于谁”，再回答“这个角色能不能读”；顺序颠倒会掩盖横向越权
    if order["tenant"] != subject.tenant and "platform_audit" not in subject.roles:
        return "deny order_not_in_tenant"
    if "order:read" not in subject.roles:
        return "deny role_missing"
    return "allow"


clerk = Subject("cs-1024", "brand-a", ("order:read",))
print(f"越权-本租户订单: {can_read_order(clerk, {'tenant': 'brand-a'})}")
print(f"越权-跨租户详情: {can_read_order(clerk, {'tenant': 'brand-b'})}")

# ---------- ③ SSRF：协议 + 主机 + 解析结果三道校验 ----------
ALLOWED_SUFFIX = ".partner-logistics.cn"
BLOCKED_IPS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
               "169.254.0.0/16", "127.0.0.0/8")


def blocked(ip):
    # 判定放在解析之后：域名合法不代表它解析到的地址合法
    return any(ipaddress.ip_address(ip) in ipaddress.ip_network(net) for net in BLOCKED_IPS)


def check_outbound(url, resolved_ips):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":                  # 挡掉 file://、gopher://、dict:// 等非 HTTP 协议
        return "deny scheme"
    host = (parts.hostname or "").lower()
    # 必须用“等于根域或 endswith 后缀”比较；startswith 可被 api.partner-logistics.cn.evil.cn 绕过
    if host != ALLOWED_SUFFIX[1:] and not host.endswith(ALLOWED_SUFFIX):
        return "deny host_not_allowlisted"
    if any(blocked(ip) for ip in resolved_ips):
        return "deny resolved_to_internal"
    return "allow"


# 真实实现用 socket.getaddrinfo(host) 取解析结果；这里显式传入，便于离线复现
cases = [
    ("https://169.254.169.254/latest/meta-data/", ["169.254.169.254"]),
    ("https://api.partner-logistics.cn.evil.cn/cb", ["203.0.113.9"]),
    ("https://api.partner-logistics.cn/cb", ["10.0.8.7"]),
    ("https://api.partner-logistics.cn/cb", ["203.0.113.9"]),
]
labels = ["SSRF-内网元数据地址", "SSRF-相似域名", "SSRF-白名单域名解析到内网", "SSRF-合法物流回调"]
for (url, ips), label in zip(cases, labels):
    print(f"{label}: {check_outbound(url, ips)}")

# ---------- ④ 凭据填充：计数键选错，限速形同虚设 ----------
def budget(key, failures, window_s):
    # 上限按“账号 + 设备”计，而不是按 IP：撞库从大量 IP 打同一批账号
    if window_s < 3600 and failures >= 5:
        return "deny locked_cooldown"
    return "allow"


print(f"凭据填充-按IP计数(换IP): {budget('ip:203.0.113.9', 1, 60)}")
print(f"凭据填充-按账号计数: {budget('user:cs-1024', 6, 60)}")
print("登录失败提示: 账号或密码不正确")
```

运行 `python3 demo.py` 的预期输出：

```text
注入-拼接: 命中 2 行
注入-参数化: 命中 0 行
越权-本租户订单: allow
越权-跨租户详情: deny order_not_in_tenant
SSRF-内网元数据地址: deny host_not_allowlisted
SSRF-相似域名: deny host_not_allowlisted
SSRF-白名单域名解析到内网: deny resolved_to_internal
SSRF-合法物流回调: allow
凭据填充-按IP计数(换IP): allow
凭据填充-按账号计数: deny locked_cooldown
登录失败提示: 账号或密码不正确
```

四处细节值得对照：拼接版“命中 2 行”说明注入不报错也算成功，功能测试看不出来；越权用例先判归属，返回 `order_not_in_tenant` 而非 `role_missing`，原因码决定排查方向；SSRF 第三例主机合法，只有解析结果校验能拦下它；凭据填充两行结论相反——换个 IP 就被放行，说明计数键选错时限速只是安慰剂。

## 动手实验

前置条件：已完成最小示例，本机有 Python 3.9+；无需网络与数据库。

### 任务一：让注入样例在“排序参数”上失败

1. 把 `safe_find` 的 `order_by` 改成直接拼接 `sort_field`。
2. 用 `sort_field="amount; DROP TABLE orders"` 调用一次，观察异常。
3. 加回白名单，确认异常消失且返回顺序仍按 `amount`。

### 任务二：把 SSRF 校验补到重定向之后

1. 复制 `check_outbound`，新增 `max_redirects` 参数。
2. 构造“白名单域名返回 `302` 指向 `http://127.0.0.1:8500`”的用例，对每一跳重新校验。
3. 确认第二跳返回 `deny scheme`，而不是直接跟随。

| 用例 | 观察点 | 预期结果 |
| --- | --- | --- |
| 排序参数注入 | 异常是否发生在执行期 | 抛 `OperationalError`，表被删除 |
| 白名单外域 | 拒绝码 | `host_not_allowlisted` |
| 解析到内网 | 拒绝码 | `resolved_to_internal` |
| 重定向到回环 | 哪一跳被拒 | 第二跳 `deny scheme` |
| 换 IP 撞库 | 是否被限速 | 按账号计数时 `deny locked_cooldown` |

验证方法：每个用例打印“拒绝码 + 判定层次（网关/应用/数据/出口）”，再确认审计日志有主体、租户、目标对象与策略版本，缺任一项都无法复盘。

清理方法：脚本只在内存运行，删除临时文件即可；若曾把真实订单号、邮箱或令牌写进脚本或日志，一并删除并轮换凭据。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 值参数化了，排序仍被注入 | 列名与排序方向直接拼接 | 用 `amount; DROP TABLE` 作排序字段 | 标识符映射白名单，未命中回退默认 |
| 列表接口安全，详情接口越权 | 只对查询做了租户过滤 | 用 A 租户令牌请求 B 租户主键 | 按主键加载后做对象级判定 |
| 域名白名单被绕过 | 用 `startswith` 比较主机 | 请求 `api.xxx.cn.evil.cn` | 改为根域相等或 `endswith` 后缀 |
| 换 IP 后限速失效 | 计数键只用 IP | 模拟多 IP 打同一账号 | 按账号 + 设备计数，叠加风险评分 |
| 登录接口可枚举账号 | 失败提示或响应时间有差异 | 比对不存在账号与错误密码的响应 | 统一提示与耗时，异步化校验 |

## 安全与生产注意事项

**<u>允许服务任意出网，等于把内网控制面交给任何能触发外部请求的人。</u>** 发票预览这类“按 URL 抓取”的功能一旦没有出口白名单，攻击者把参数指向云元数据地址就能拿到临时凭据，再读取对象存储与配置中心，事故范围从一条参数扩大到整个账号。缓解方式：出网经统一代理、白名单自助申请并到期复核、禁止自动重定向、元数据服务强制 token 访问、网络层默认拒绝。

**<u>只按 IP 限速、且失败提示能区分账号是否存在，会让凭据填充分两步拿到账号接管。</u>** 攻击者先用提示差异筛出有效邮箱，再用分布式 IP 换取无限次尝试；后果是账号被接管、订单与收货地址被读取、退款被打到他人账户，而日志里每个 IP 都“很干净”。缓解方式：按账号与设备计数并逐级延迟、接入泄露口令校验、高风险操作强制 MFA、新设备异地登录单独告警。

**<u>为排查注入把请求原文（含 `Authorization` 头与表单密码）写进日志，会让一次安全事件变成第二次泄露。</u>** 日志会同步到多个分析平台、保留数月且访问面更宽。缓解方式：字段级脱敏、令牌只留前缀与哈希、日志访问本身纳入审计。

## 本课总结

- **四类攻击的共同点是系统把不该信的东西当成了事实**：输入、主键、URL、密码各自需要不同证据。
- **注入用值与语句分离解决，标识符只能靠白名单**，转义与黑名单挡不住排序、表名这类位置。
- **登录不等于有权**，判定必须下沉到具体对象，数据层再做一次归属兜底。
- **SSRF 要三查：协议、主机、解析后的地址**，并逐跳校验重定向；白名单不是终点，出口收口才是。
- **凭据填充的计数键必须选账号，而不是 IP**，认证强度与错误提示同样属于控制手段。

## 思考题

发票预览要按供应商给的 URL 抓取 PDF。安全团队要求出口代理维护 200 条域名白名单，业务方说供应商域名每两周变一批，按这套流程上线要等一个月。请说明：如何在不放开任意出网的前提下把变更周期压到一天内，用什么机制防止白名单变成“人人可加”的通道，以及用什么证据判断达标。

参考思路：先让出网需求消失——供应商改上传到商城预签名地址，预览只读自家对象存储，这是首选。若必须抓取，就把白名单变成“供应商登记表”：入驻流程带出域名并自动生效，只认登记过的域名与端口，出口做解析后校验、重定向逐跳校验与体积上限；业务自助登记，安全只看规则与日志。证据要可执行：未登记域名被拒、登记域名解析到内网被拒、抽查日志能否还原“谁在何时为哪个供应商开的口子”。

## 小测

1. 参数化查询挡不住下面哪一类注入？  
   A. `WHERE` 条件里的值　B. `ORDER BY` 的列名　C. 字符串形式的金额　D. `LIKE` 的匹配模式
2. `/api/orders/{id}` 已要求登录，仍能读到别家订单，缺的主要是？  
   A. 更强的密码策略　B. 对象级授权与归属过滤　C. HTTPS　D. 请求签名
3. SSRF 只校验“必须是 `https://` 且域名后缀匹配”为什么不够？举出两种绕过方式。
4. 凭据填充为什么按 IP 限速常常无效？应改成按什么计数？
5. 场景题：安全运营报告“WAF 本月拦截 12 万次 SQL 注入尝试”，运维据此认为注入风险已关闭，建议暂缓代码层改造。你接受吗？

## 答案与解析

1. **B。** 列名与排序方向属于语句结构，占位符只能替换值，必须用白名单映射。A、C、D 都是值的位置，绑定参数后可安全处理；D 只需额外处理 `%` 与 `_`，不属于结构注入。
2. **B。** 登录只证明“你是谁”，不证明“这条数据归你”。A 与本次越权无因果关系；C 只保护传输，令牌合法时照样越权；D 防篡改与重放，但不判断归属。
3. 至少两种：一是前缀判断错误，`api.partner-logistics.cn.evil.cn` 以合法域名开头却不是同一主机；二是域名合法但解析到内网，或先返回重定向再跳到内网。理由是校验停在字符串层时，攻击者控制的正是 DNS 与响应，校验必须延伸到解析结果与每一跳。
4. 因为撞库的典型形态是大量 IP 各试少量次数打同一批账号，单 IP 计数永远低于阈值。应改成按账号 + 设备指纹计数并逐级延迟，叠加泄露口令校验与 MFA。
5. 不接受。WAF 只匹配已知 payload，判断不了某次查询是否越权，也挡不住编码变形与直连源站的旁路；12 万次拦截只说明暴露面在被扫描。应把它当线索：抽样看命中的接口与参数，回代码层补参数化查询与对象级授权，并验证源站不可绕过网关。

### 动手实验参考

任务一的关键是让失败发生在执行期：拼接后 SQL 变成两条语句，`sqlite3` 抛 `OperationalError`，后续查询报表不存在——这比“返回错误数据”更危险，因为它证明输入能改变语句结构。任务二的关键是把校验放进跳转循环：每一跳重新走三查，`http://127.0.0.1` 会在第二跳被 `deny scheme` 拦下；只在入口校验一次，重定向就是现成的绕过通道。

## 延伸阅读与下一课

- [OWASP Top 10：A01 失效的访问控制](https://owasp.org/Top10/A01_2021-Broken_Access_Control/)，横向与纵向越权的分类与案例。
- [OWASP Top 10：A03 注入](https://owasp.org/Top10/A03_2021-Injection/)，注入的形态与参数化的边界。
- [OWASP SSRF 防护备忘录](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)，出口白名单、解析后校验与重定向处理。
- [OWASP 凭据填充防护备忘录](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html)，多键限速与 MFA 的落地建议。
- [CWE-918：服务端请求伪造](https://cwe.mitre.org/data/definitions/918.html)，漏洞分类与相关弱点链。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[Secret、证书与密钥管理](08-secrets-and-key-management.md)。
- 下一课：[数据分类、脱敏与合规基础](10-data-classification-encryption-and-compliance.md)。
