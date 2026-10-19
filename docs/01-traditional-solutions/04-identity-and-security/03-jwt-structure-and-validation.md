---
title: JWT 结构、签发与校验
slug: jwt-structure-and-validation
module: traditional-solutions
stage: build-and-integrate
type: core
difficulty: intermediate
duration: 60m
prerequisites:
  - passwords-mfa-session-and-apikeys
outcomes:
  - 拆开一条 JWT 的三段，指出哪一段可被任意读取、哪一段决定令牌可信度
  - 按「结构 → 算法白名单 → 验签 → 声明校验 → 授权」的顺序校验令牌，并说明每一步防住什么
  - 为短有效期、刷新轮换与吊销设计一组可落地的策略，并指出常见安全误区
last_reviewed: 2026-10-19
---

# JWT 结构、签发与校验

## 为什么需要学习

晴空商城把登录态从 Session 换成 JWT 后，商城、客服、移动端与退款服务第一次做到“不查库也能知道请求是谁发的”。上线三周后，一名已注销的离职运营账号仍能用手机里的旧令牌调用退款审核接口；同一周，安全团队用一条把 `role` 改成 `admin` 的令牌调通了后台，没有任何告警。

两次都不是密码泄露。签名只证明“由持有密钥的一方签发、内容没被改过”，不证明角色是当前角色，不证明签发者是你信任的系统，也不证明令牌未被吊销。

> **核心结论：** JWT 的可信度不来自它长得像令牌，而来自你敢执行的那几步校验；跳过任何一步，剩下的就是一段谁都能改的 JSON。

## 学习目标

完成本课后，你能够：

- 拆开一条 JWT 的三段，指出哪一段明文可读、哪一段决定令牌是否可信。
- 按“结构 → 算法白名单 → 验签 → 声明校验 → 授权”的顺序完成校验，并说明每一步防住什么。
- 为短有效期、刷新轮换和吊销设计一套组合策略，说明各自补的是哪个缺口。
- 拿到被拒绝的令牌时先定位原因，而不是直接延长有效期。

## 前置知识

- 回看上一课：[密码、MFA、Session 与 API Key](02-passwords-mfa-session-and-apikeys.md)。
- 知道 HTTP 请求头如何携带凭据，能区分 401（未通过认证）与 403（已认证但无权限）。
- 理解哈希与 HMAC 的差别：哈希不可逆，HMAC 需要一个只有双方知道的密钥。
- 能在本机运行 `python3 --version`；本课示例只用标准库，不需要联网。

## 业务场景

晴空商城的退款流程有四个调用方：商城前端、客服工作台、仓库扫码端和退款服务。

- 退款服务由另一团队维护，不该为每次请求查商城的 Session 表。
- 高额退款需二次确认，退款服务必须自己判断调用者有无审核权限。
- 仓库扫码端常处弱网，令牌过期后不能把正在扫码的页面直接清空。
- 财务要求每次审核都能追溯到操作人与令牌编号。

所以令牌要带主体、受众、权限和过期时间。但**令牌一旦签发，签发方就不再拥有它**，“注销立即生效”正好落在 JWT 最不擅长的位置。本课要定的是：放什么、谁来签、按什么顺序校验、过期与吊销怎么组合。

## 核心概念

*JWT*（JSON Web Token，RFC 7519）是把一组 *声明*（claim，键值对断言）编码成字符串的格式，用 `.` 分成 `Header.Payload.Signature`。

- *Header*：声明 `alg`（签名算法）、`typ`（类型）与可选的 `kid`（密钥 ID，轮换期指明朝哪把钥匙）。
- *Payload*：声明集合。`sub` 主体、`iss` 签发者、`aud` 受众、`exp` 过期、`nbf` 生效、`iat` 签发、`jti` 唯一 ID 为注册声明，其余为自定义声明，如 `ver`（令牌版本号）。
- *Signature*：对 `base64url(Header) + "." + base64url(Payload)` 用密钥算出的摘要。*JWS* 是签名结构规范，JWT 是其中载荷为 JSON 声明集的用法。

三段的性质完全不同，这是最该先建立的直觉：

| 段 | 内容 | 是否明文可读 | 改一个字节会怎样 | 能否单凭它判断身份 |
| --- | --- | --- | --- | --- |
| Header | `alg`、`typ`、`kid` | 是 | 签名对不上（除非算法被换掉） | 不能，只用于选算法、选密钥 |
| Payload | `sub`、`aud`、`exp`、角色等 | 是 | 签名对不上 | 不能，必须验签后才可信 |
| Signature | HMAC 值或非对称签名 | 是，但不可逆 | — | 能，前提是算法与密钥都正确 |

几个必须分清的概念：

- *base64url* 只是把字节转成 URL 安全字符，不是加密，谁都能解开。
- *对称签名*（HS256）共用密钥，简单但校验方可伪造；*非对称签名*私钥签发、公钥校验。
- *访问令牌*用于调用 API，有效期短；*刷新令牌*只用于换新，有效期长且必须能被吊销。
- *吊销*是让未过期令牌失效；JWT 无状态，只能靠缩短有效期、令牌版本号和 *黑名单*（按 `jti` 记录）实现。

**只有验签通过的 Payload 才有资格被读取。**<u>把“解出 JSON 能看见 sub”当成“已验证身份”，是本课多数事故的起点。</u>

## 工作原理

签发发生在身份服务里：

1. 认证通过后确定 `sub`、`aud`（谁有权接收，如 `refund-api`）与 `ver`（令牌版本号）。
2. 生成 `iat`、`nbf`、`exp`；访问令牌通常 5–15 分钟，够走完一次业务流程，又让吊销窗口足够短。
3. 组 Header，写明 `alg` 与 `kid`；`kid` 是密钥轮换的前提。
4. 两段转紧凑 JSON、base64url 编码并去掉 `=` 填充，用 `.` 连接后对整串签名，再把签名拼作第三段。

校验发生在每个资源服务里，顺序不能换：

5. 拆分三段并检查长度上限，超长令牌直接拒绝。
6. 读出 Header，但只当候选参数：`alg` 必须命中白名单，`kid` 必须能在本地密钥集中找到。
7. 用 `kid` 指向的密钥、按白名单算法重算签名，恒定时间比对；不通过即 401。
8. 校验声明：`exp` 未过期（留几十秒时钟偏差）、`nbf` 已生效、`iss` 等于预期签发者、`aud` 包含本服务、`jti` 未被吊销。
9. 做授权判断：`sub` 与角色只回答“是谁”，能否退款由退款服务的策略决定。
10. 写审计：`jti`、`sub`、`aud`、`ver` 进入操作日志。

刷新与吊销是两条互补的线：

11. 访问令牌过期后，客户端用刷新令牌换新；服务端校验后签发新令牌并*轮换*刷新令牌，旧的立即作废。刷新令牌被重复使用说明已泄露，应吊销该用户全部令牌。
12. 需要“立即失效”时自增 `ver` 并写入共享存储；对“此刻必须作废”的单条令牌，把 `jti` 写进黑名单，过期时间设为该令牌的 `exp`，避免无限增长。

两个顺序性错误要写进规范：<u>先验签、后读声明</u>；<u>先判时效与算法、后算摘要</u>，否则攻击者能用 `alg=none` 或超长令牌白白消耗你的 CPU。

## 架构与选型

先判断该不该用 JWT：

| 场景 | 是否适用 | 理由 |
| --- | --- | --- |
| 多服务、多端独立校验身份，不愿每次查会话表 | 适用 | 无状态校验，扩容不需要会话粘滞 |
| 要求注销或封号“立即且绝对”生效 | 不适用，需补机制 | 无状态令牌不感知状态变化，必须加版本号或黑名单 |
| 高频内部调用、带宽敏感 | 谨慎 | 令牌随每个请求携带，体积可比 session ID 大一个数量级 |
| 浏览器长期登录态 | 谨慎 | 需配合 `HttpOnly` Cookie、短有效期与刷新轮换，否则 XSS 可整条取走 |
| 单体应用且已有服务端会话 | 不必替换 | 增加复杂度却换不到收益 |

对称与否，实际比的是“谁有资格校验”：

| 维度 | 对称（HS256） | 非对称（RS256/ES256/EdDSA） |
| --- | --- | --- |
| 密钥持有方 | 签发方与每个校验方持有同一密钥 | 只有签发方持私钥，校验方只拿公钥 |
| 校验方能否伪造令牌 | 能 | 不能 |
| 实现与性能成本 | 低，几行标准库代码 | 略高，需管理密钥对与公钥分发 |
| 轮换难度 | 高，新密钥要安全下发到每个服务 | 低，公钥可公开分发，按 `kid` 平滑切换 |
| 典型适用 | 单一团队内的少量服务 | 跨团队、跨组织、存在第三方校验方 |

选型依据压成一句：**密钥的信任边界决定算法**。签发方与校验方同处一个信任域、只有两三个服务时，HS256 足够；一旦有外部或跨团队校验方就必须用非对称，否则每个校验方都能伪造令牌。无论选哪种都要带 `kid`，否则轮换那天只能全站重启或容忍一轮 401。

## 最小示例

问题：用标准库签发并校验一条 HS256 令牌，验证篡改、换受众、过期、`alg=none` 都被拒绝。环境 Python 3.8+，只用标准库，不联网。

```python
import base64
import hashlib
import hmac
import json

SECRET = b"demo-only-not-a-real-key"  # 真实密钥来自密钥服务，禁止写进代码库或镜像
ALG = "HS256"                         # 只接受显式白名单中的算法

def b64url(raw: bytes) -> str:
    # JWT 使用无填充的 base64url；标准库默认带 "="，必须自己去掉
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

def b64url_decode(text: str) -> bytes:
    # 补齐被去掉的填充，否则长度不是 4 的倍数时解码会报错
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))

def sign(header: dict, payload: dict) -> str:
    # 1) 两段都先转紧凑 JSON 再编码，空格与键序差异会让签名对不上
    head = b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    body = b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{head}.{body}"  # 2) 签名只覆盖前两段，签名段自己不在其中
    digest = hmac.new(SECRET, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{b64url(digest)}"  # 3) 三段用 "." 拼成一个字符串

def verify(token: str, now: int, issuer: str, audience: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("结构不是三段")
    head_b64, body_b64, sig_b64 = parts
    header = json.loads(b64url_decode(head_b64))
    # 4) 先确认算法在白名单里，绝不按 header 自报的 alg 去选择实现
    if header.get("alg") != ALG:
        raise ValueError(f"算法不被接受: {header.get('alg')!r}")
    expected = hmac.new(SECRET, f"{head_b64}.{body_b64}".encode(), hashlib.sha256).digest()
    actual = b64url_decode(sig_b64)
    # 5) 恒定时间比较，避免通过响应耗时逐字节猜签名
    if not hmac.compare_digest(expected, actual):
        raise ValueError("签名无效")
    claims = json.loads(b64url_decode(body_b64))
    # 6) 签名通过后才读声明；顺序颠倒等于相信了任何人都能改的数据
    if claims.get("iss") != issuer:
        raise ValueError("签发者不符")
    if audience not in claims.get("aud", []):
        raise ValueError("受众不符")
    if now >= claims["exp"]:
        raise ValueError("令牌已过期")
    if now < claims.get("nbf", 0):
        raise ValueError("令牌尚未生效")
    return claims

NOW = 1_760_832_000  # 固定“当前时间”，让下面的输出可以复现
token = sign(
    {"alg": "HS256", "typ": "JWT", "kid": "k1"},
    {"sub": "u_10086", "iss": "https://id.qingkong.example", "aud": ["refund-api"],
     "iat": NOW, "exp": NOW + 300, "jti": "j_7f3a", "ver": 12},
)
print("令牌:", token)
print("长度:", len(token), "字符")

def attempt(label: str, candidate: str, at: int, aud: str) -> None:
    try:
        claims = verify(candidate, at, "https://id.qingkong.example", aud)
        print(f"{label}: 通过 sub={claims['sub']}")
    except ValueError as exc:
        print(f"{label}: 拒绝（{exc}）")

attempt("正常校验", token, NOW, "refund-api")
attempt("过期 301 秒", token, NOW + 301, "refund-api")
attempt("换成订单服务受众", token, NOW, "order-api")

head_b64, body_b64, sig_b64 = token.split(".")
forged_body = b64url(json.dumps({"sub": "u_99999", "iss": "https://id.qingkong.example",
                                 "aud": ["refund-api"], "iat": NOW, "exp": NOW + 300},
                                separators=(",", ":"), sort_keys=True).encode())
attempt("篡改 sub 后复用原签名", f"{head_b64}.{forged_body}.{sig_b64}", NOW, "refund-api")

none_head = b64url(json.dumps({"alg": "none", "typ": "JWT"}, separators=(",", ":"), sort_keys=True).encode())
attempt("alg=none 去掉签名", f"{none_head}.{body_b64}.", NOW, "refund-api")
print("payload 明文可读:", b64url_decode(body_b64).decode())
```

输出（本机 Python 3 实际运行）：

```text
令牌: eyJhbGciOiJIUzI1NiIsImtpZCI6ImsxIiwidHlwIjoiSldUIn0.eyJhdWQiOlsicmVmdW5kLWFwaSJdLCJleHAiOjE3NjA4MzIzMDAsImlhdCI6MTc2MDgzMjAwMCwiaXNzIjoiaHR0cHM6Ly9pZC5xaW5na29uZy5leGFtcGxlIiwianRpIjoial83ZjNhIiwic3ViIjoidV8xMDA4NiIsInZlciI6MTJ9.iwINGM0RDdWxfo03F_w6H1IxHMVw6lN-ZVjrsWd0mYE
长度: 272 字符
正常校验: 通过 sub=u_10086
过期 301 秒: 拒绝（令牌已过期）
换成订单服务受众: 拒绝（受众不符）
篡改 sub 后复用原签名: 拒绝（签名无效）
alg=none 去掉签名: 拒绝（算法不被接受: 'none'）
payload 明文可读: {"aud":["refund-api"],"exp":1760832300,"iat":1760832000,"iss":"https://id.qingkong.example","jti":"j_7f3a","sub":"u_10086","ver":12}
```

`sign` 只做编码、签名、拼接，不含业务判断；`verify` 按“结构 → 算法白名单 → 验签 → 声明”推进，失败即抛异常而不返回半成品；`attempt` 只让失败原因可辨。三处设计值得注意：签名比较用 `hmac.compare_digest` 而非 `==`，否则攻击者可凭比较耗时逐字节猜签名；算法判断是“等于 `HS256`”而非“读出 `alg` 再调用”，`alg=none` 因此没有入口；`aud` 校验防的是“用订单服务的令牌调退款接口”，<u>而 `aud` 可能是字符串或数组，先归一化成列表，否则 `refund` 会子串命中 `refund-api`。</u>

## 动手实验

### 任务：让“少一步校验”的后果可见

前置条件：`python3` 3.8+；把最小示例的 `SECRET`、`ALG` 与四个函数保存为 `/tmp/jwt_lab.py`；无需网络与第三方库。

步骤：

1. 运行 `python3 /tmp/jwt_lab.py`，确认“正常校验”通过，其余四个用例都被拒绝。
2. 把 `exp` 从 `NOW + 300` 改成 `NOW + 60`，重跑，记录新的令牌字符串。
3. 用短脚本只改 Payload 里的 `exp` 为更晚时间、保留原签名，再交给 `verify`。
4. 把 Header 的 `alg` 改成 `"none"`、第三段留空，再交给 `verify`。
5. 注释掉 `verify` 中 `audience not in claims.get("aud", [])` 这一行，重跑，观察“换成订单服务受众”从拒绝变成通过。

预期结果：第 3 步得到“签名无效”，第 4 步得到“算法不被接受”，第 5 步该用例打印“通过”，说明缺受众校验时任何服务的令牌都能打进退款服务。

验证方法：只有“正常校验”一行是通过；Payload 能打印出 `sub` 与 `ver` 明文；令牌长度在 250–300 字符，明显长于 session ID。

清理方法：`rm -f /tmp/jwt_lab.py`。示例密钥只是字符串常量，不得复制到任何真实环境；若曾在终端粘贴过真实密钥，立即轮换。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 所有服务同时 401，报签名无效 | 轮换密钥时先把旧密钥下掉了 | 对比令牌 Header 的 `kid` 与各服务启用的密钥版本 | 双密钥并存一段时间，按 `kid` 路由后再下线旧密钥 |
| 刚签发的令牌被判过期 | `exp` 秒与毫秒混用，或节点时钟漂移 | 打印 `exp` 与 `int(time.time())`，比较量级与差值 | 统一用秒级 NumericDate；开启时间同步并留 30–60 秒容忍 |
| 越权成功：订单端令牌能调退款接口 | 未校验 `iss` 与 `aud` | 用另一服务的合法令牌直接打本服务接口 | 强制校验 `iss` 白名单与 `aud` 包含本服务 |
| 用户已登出，旧令牌仍可用 15 分钟 | JWT 无状态，服务端无记录 | 登出后立即重放请求 | 缩短访问令牌有效期，并用 `ver` 或 `jti` 黑名单 |
| 令牌出现在访问日志或 URL 中 | 放进 query string 或打印了整个请求头 | 在日志里检索 `eyJ` 前缀 | 只走 `Authorization: Bearer`，日志字段脱敏 |

## 安全与生产注意事项

**<u>绝不能让令牌自己决定用什么算法校验。</u>** 若代码按 Header 的 `alg` 动态选择实现，攻击者把算法改成 `none`，或用公钥当 HMAC 密钥重算签名，就能伪造任意身份。缓解方式：固定白名单、先判 `alg` 再验签、拒绝未知算法。

**<u>不要把 JWT 当成加密容器。</u>** Payload 只是 base64url，任何抓到令牌的人都能读出手机号、身份证号、内部接口地址；把它塞进浏览器存储、日志或错误上报，等于把这些字段公开发布，往往“还没被攻破，合规先出事”。只放 `sub`、`aud`、`exp`、`ver` 这类标识，敏感数据用 `sub` 回查，确有需要再上 JWE 或改用不透明令牌。

**<u>长有效期加无吊销，等于给离职员工和被盗账号发长期通行证。</u>** 令牌签发出去就无法收回，10 小时的管理员令牌泄露就是 10 小时的管理员权限。访问令牌压到 5–15 分钟、刷新令牌轮换并绑定设备、`ver` 变更即时失效，把“封号、改密、登出”都实现成版本号自增。校验端还必须限制令牌长度与解析深度，否则无状态校验会被做成 CPU 放大器。

## 本课总结

- JWT 是 `Header.Payload.Signature` 三段结构，三段都明文可读，**只有签名决定可信度**。
- 校验顺序固定为“结构 → 算法白名单 → 验签 → 声明（`exp`/`nbf`/`iss`/`aud`/`jti`）→ 授权”，颠倒就是把未验证数据当事实。
- 签名只证明来源与完整性，不证明角色是当前角色、令牌未被吊销、受众是本服务。
- 吊销靠三件事组合：短有效期压缩窗口，`ver` 让某用户全部令牌失效，`jti` 黑名单处理单条令牌的作废。
- 密钥的信任边界决定算法：跨团队或对外校验必须用非对称签名，并始终保留 `kid`。

## 思考题

退款服务要求“运营人员一被注销，令牌在任意节点上必须立刻失效”，团队却在用 JWT 换无状态扩展。这两者为什么冲突？如果必须付出“每次请求多一次读取”的代价，你愿意花在哪里；如果不愿意，能容忍多长的失效延迟，依据是什么？

参考思路：无状态校验意味着令牌内容在签发时就固定了，服务端不查询就不知道“这人已被注销”。可行的折中是分层：普通接口接受十几分钟延迟，靠短有效期兜底；高敏操作（退款审核、导出客户数据）在令牌之外再加一次实时检查，查 `ver` 或权限服务，并把结果缓存几十秒。判断依据不是“哪个更先进”，而是业务能容忍多长的越权窗口。

## 小测

1. 一条 JWT 的 Payload 被修改后为什么不能继续使用？
   A. Payload 被加密，改了就解不开　B. 签名覆盖 Header 与 Payload，改动会让摘要不匹配　C. 服务端缓存了原始 Payload　D. base64url 编码本身会校验内容
2. 下列哪一项不属于 JWT 签名能保证的性质？
   A. 令牌由持有密钥的一方签发　B. 令牌内容在传输后未被篡改　C. 令牌里的角色仍然是用户当前的权限　D. 不知道密钥的人无法伪造签名
3. `exp` 与 `jti` 各解决什么问题？各用一句话说明。
4. 为什么校验时必须先判 `alg` 白名单再验签，而不能“读出 `alg` 再调用对应算法”？
5. 场景题：客服反馈“用户点了退出登录，但用抓包工具重放请求，10 分钟内仍然能读到订单”。作为架构师，你会先改哪一处，并向业务承诺多长的失效窗口？

## 答案与解析

1. **B。** 签名覆盖 `base64url(Header).base64url(Payload)`，改 Payload 后摘要必然不同。A 错在把 JWT 当加密，它只是编码；C 错在 JWT 本身无状态；D 错在 base64url 只做编码，不提供完整性校验。
2. **C。** 签名保证来源与完整性，不保证声明与现实一致；角色是否仍成立取决于签发时的数据，只能在授权时回查，或靠 `ver` 让旧令牌失效。A、B、D 都是签名的正常性质。
3. `exp` 限定最后可用时刻，把“泄露后还能用多久”压成有限窗口；`jti` 给每条令牌唯一标识，使单条令牌能被精确列入黑名单并写进审计。
4. 因为 `alg` 是攻击者可控的输入。若按它选择实现，攻击者可以填 `none` 跳过校验，或把公钥当 HMAC 密钥伪造签名。白名单把可选算法收缩成一个固定值，攻击面随之消失。
5. 优先改最短路径：访问令牌从 10 分钟压到 2–5 分钟，同时让登出触发 `ver` 自增或 `jti` 入黑名单。对业务按“令牌有效期 + 时钟容忍”表述，例如“登出后 5 分钟内全部失效，高敏接口实时失效”；只承诺“立即失效”又不做实时检查，等于承诺做不到。

### 动手实验参考

第 3 步应看到“签名无效”，因为签名段没有一起改；若改完 `exp` 同时重算签名，令牌会重新变合法——这正是“谁持有密钥谁就能签发”的含义。第 4 步应看到“算法不被接受”，报错带出 `'none'`。第 5 步注释掉 `aud` 校验后，该用例会打印“通过”，说明缺受众校验时令牌可在服务间串用；把校验加回去，确认输出恢复拒绝。

## 延伸阅读与下一课

- [RFC 7519：JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)：声明定义与 `exp`、`aud` 的语义。
- [RFC 7515：JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515)：签名输入的具体构造方式。
- [RFC 8725：JWT 最佳当前实践](https://www.rfc-editor.org/rfc/rfc8725)：算法混淆与令牌校验清单的权威说明。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[密码、MFA、Session 与 API Key](02-passwords-mfa-session-and-apikeys.md)。
- 下一课：[OAuth 2.0 授权流程与 PKCE](04-oauth2-flows-and-pkce.md)。
