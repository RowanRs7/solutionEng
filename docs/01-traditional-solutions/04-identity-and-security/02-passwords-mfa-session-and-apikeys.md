---
title: 密码、MFA、Session 与 API Key
slug: passwords-mfa-session-and-apikeys
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 55m
prerequisites:
  - authentication-authorization-and-audit
outcomes:
  - 说明加盐慢哈希的存储格式与校验流程
  - 为不同身份入口选择合适的第二因素、Session 或 API Key 方案
  - 排查凭据泄露、会话失效与 API Key 轮换问题
last_reviewed: 2026-10-19
---

# 密码、MFA、Session 与 API Key

## 为什么需要学习

晴空商城的身份入口不止一个：顾客在网页登录，客服在后台处理退款，三家仓库通过接口回传发货状态，财务每夜读取对账单。同一批工程师维护它们，却需要完全不同的凭据设计。

上周的事故很典型：客服账号被撞库，攻击者用合法会话翻查两百多笔订单；仓库供应商把 API Key 硬编码进安装包，Key 流到论坛；客服至今共用两个账号，审计查不出谁批准退款。三个问题的共同点是没人说清：谁持有凭据、凭据怎么存、泄露后怎么收回。

> **核心结论：** 凭据方案的选型标准不是“哪种更现代”，而是“谁持有它、泄露后能收回什么、事后能否说清是谁在用”。

## 学习目标

完成本课后，你能够：

- 说明密码哈希为什么必须加盐、为什么必须用可调成本的慢哈希。
- 区分知识、持有、生物三类因素，判断 TOTP 与 Passkey 在抗钓鱼上的差别。
- 对比 Session/Cookie 与 API Key 的适用场景、生命周期和吊销方式。
- 为晴空商城的顾客、客服、仓库对接三个入口分别给出凭据方案并说明理由。

## 前置知识

- 回看上一课：[认证、授权与审计](01-authentication-authorization-and-audit.md)。
- 知道 HTTP 是无状态协议，请求之间默认不记得彼此是谁。
- 知道浏览器会在满足条件时自动携带 Cookie，并可用 `HttpOnly`、`Secure` 限制它的行为。
- 能读懂 Python 3 的函数、字典和类型注解。

## 业务场景

晴空商城的退款流程涉及四个参与方：顾客发起退款，客服审核，仓库确认是否已出库，财务系统生成对账记录。

- **商城网页**：顾客用手机号加密码登录，能看订单、发起退款。用户量大，是撞库重灾区。
- **客服后台**：四十名客服能改金额、批退款、看完整地址；要求高权限操作必须追到人。
- **仓库对接**：三家仓库供应商用各自系统调用发货回传接口，没有人点登录按钮，调用由程序发出。
- **财务对账**：每天凌晨拉一次对账单，同样没有交互式登录。

架构评审提出的问题很具体：密码在库里长什么样？客服要不要强制第二因素？仓库对接该发 Key 还是账号？换岗或离职时怎么让旧凭据一分钟内失效？

## 核心概念

*凭据*（credential）是证明“我就是我声称的那个人或那个系统”的材料。密码、短信验证码、API Key、Session ID 都是凭据，区别在于谁生成、谁保管、多久换一次。

*密码哈希*是单向函数，无法从摘要反推密码；但同一密码会产生同一摘要，攻击者可预计算常见密码的摘要表。*盐*（salt）是每用户独立随机值，与密码一起参与哈希，使同一密码在两个账号下结果不同。*慢哈希*（*KDF*，密钥派生函数）把成本调到“登录可接受、批量猜测很昂贵”的区间，如 `scrypt`、`argon2id`、`bcrypt`，成本参数需随硬件进步上调。

*MFA*（多因素认证）要求两类以上不同性质的因素：知识（密码、PIN）、持有（手机、硬件密钥）、生物（指纹、面容）。<u>两个密码不算 MFA</u>。*TOTP* 双方共享种子，每 30 秒各算出同一个 6 位数字。*Passkey*（基于 WebAuthn）用设备私钥签名挑战值，私钥不出设备，对钓鱼站点天然免疫。

*Session* 是服务端保存的登录状态，*Session ID* 只是指向它的随机引用；浏览器把 ID 放进 *Cookie* 自动携带，服务端据此查出用户与权限。*API Key* 是发给调用方系统的长期共享密钥，标识“哪个应用在调用”，而非“哪个员工在操作”。

| 机制 | 代表谁 | 存在哪里 | 典型有效期 | 泄露后的影响 |
| --- | --- | --- | --- | --- |
| 密码 | 人 | 服务端摘要，加盐慢哈希 | 长期，直至修改 | 单账号被冒用，可被撞库放大 |
| TOTP / Passkey | 人 | 令牌设备或密钥硬件 | 30 秒 / 每次签名 | TOTP 种子泄露可持续生成验证码，Passkey 私钥不可导出 |
| Session + Cookie | 人（已登录状态） | 服务端存储 + 浏览器 Cookie | 分钟到小时 | 会话被劫持，直到会话被吊销 |
| API Key | 系统 / 应用 | 服务端指纹 + 调用方配置 | 天到月 | 调用方身份被冒用，直到 Key 被轮换 |
| JWT | 人（已签发的声明） | 客户端持有，服务端验签 | 分钟级 | 有效期内无法单方撤销，下一课展开 |

## 工作原理

两条数据流共享三个约束：凭据必须能过期、能吊销、能审计。

**人：密码 + 第二因素 + Session**

1. 用户注册时提交密码，服务端生成 16 字节随机盐。
2. 用带成本参数的慢哈希计算摘要，按 `算法$参数$盐$摘要` 的格式存库，参数一起存，便于日后升级。
3. 登录时密码经 HTTPS 提交，服务端读出该用户的盐和参数，用同样参数重算摘要。
4. 用常量时间比较摘要，避免通过响应耗时逐字节猜出正确值。
5. 第一因素通过后要求 TOTP 或 Passkey：允许前后各一个时间窗，并记录已用计数器，防止同组数字被重放。
6. 全部通过后创建 Session：生成高熵随机 ID，服务端保存 `user_id`、角色、签发时间、最后活动时间。
7. 用 `Set-Cookie` 下发：`HttpOnly` 阻止脚本读取，`Secure` 只走 HTTPS，`SameSite=Lax` 限制跨站自动携带，并设置闲置超时。
8. 后续请求由浏览器自动带回 Cookie，服务端查 Session 决定权限；改密、登出、换岗时删除 Session 并轮换 ID，避免攻击者预置的会话标识继续有效。

**系统：API Key**

1. 平台为调用方生成高熵 Key，只在创建时显示一次。
2. 数据库只存 Key 的哈希指纹、可识别前缀、归属应用、授权范围（scope）和过期时间。
3. 调用方把 Key 放进 `Authorization: Bearer ...` 请求头，不放 URL 查询串。
4. 服务端计算指纹、常量时间比对，再检查 scope、有效期、来源 IP 是否匹配。
5. 每次调用写审计记录：哪个 Key、哪个接口、什么结果。
6. 轮换时新旧 Key 并存一个切换窗口，确认新 Key 正常后再吊销旧的，避免直接停服。

## 架构与选型

| 入口 | 推荐机制 | 选它的理由 | 不适用或需注意 |
| --- | --- | --- | --- |
| 商城顾客网页 | 密码 + Session Cookie，渐进引导 Passkey | 用户基数大、设备杂，Session 可即时吊销 | 跨站嵌入场景要谨慎配置 `SameSite` |
| 客服后台 | 密码 + 强制 MFA（Passkey 优先）+ 短闲置超时 | 高权限、需追责，30 分钟闲置即登出 | 共享账号必须废除，否则审计无意义 |
| 仓库系统对接 | 一供应商一 API Key，限 scope + IP 白名单 + 定期轮换 | 无人在场，密钥可精确授权到接口级 | 不能代替人身份，出问题只能追到应用 |
| 支付回调 | 签名校验 + 时间戳 + 重放窗口 | 第三方不持有你的账号体系 | 见 Webhook 签名一课，不要复用 API Key |
| 移动 App | 短期访问令牌 + 刷新令牌 | 减少长期凭据驻留设备 | 令牌撤销能力弱于服务端 Session |

取舍在“可吊销”与“无状态扩展”之间。Session 吊销即时，但多实例要共享存储（如 Redis），否则用户会在实例间反复掉登录；API Key 易校验，但发出去后难限制位置，必须靠 scope、白名单和轮换缩小爆炸半径。**越难吊销的凭据，越应给更小权限和更短有效期。**

## 最小示例

问题：验证“同一密码两次存储结果不同、正确密码可校验、错误密码被拒”，并对比密码与 API Key 的存储差异。环境为 Python 3 标准库，无需第三方依赖，不访问网络。把代码保存为 `password_demo.py` 后直接运行。

```python
import base64
import hashlib
import hmac
import os
import secrets

# 成本参数与盐长度一起写进存储格式，未来升级算法时新旧记录可以共存
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
SALT_BYTES = 16

def hash_password(password: str) -> str:
    # 每个用户独立随机盐：同一密码在不同账号下得到不同摘要，预计算表失效
    salt = os.urandom(SALT_BYTES)
    # scrypt 的 n/r/p 决定内存与 CPU 成本，调高只影响登录耗时，不影响正确性
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    # 存算法名和参数，而不是只存摘要，否则以后无法判断该用哪套参数校验
    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode())

def verify_password(password: str, stored: str) -> bool:
    # 按存储记录里的参数重算，保证参数升级后老用户仍能登录
    algo, n, r, p, b64salt, b64digest = stored.split("$")
    if algo != "scrypt":            # 未知算法直接拒绝，避免降级攻击
        return False
    salt = base64.b64decode(b64salt)
    expected = base64.b64decode(b64digest)
    actual = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=int(n), r=int(r), p=int(p), dklen=len(expected))
    # 常量时间比较：普通 == 会在首个不同字节提前返回，泄漏信息
    return hmac.compare_digest(actual, expected)

def issue_api_key() -> tuple[str, str]:
    # 高熵随机 Key，人能记住的部分只是前缀，用于在日志里辨认
    raw = "sk_live_" + secrets.token_urlsafe(24)
    # 数据库只保存指纹；Key 本身不落库，泄露数据库不等于泄露可用 Key
    return raw, hashlib.sha256(raw.encode()).hexdigest()

def check_api_key(presented: str, stored_fingerprint: str) -> bool:
    # 同样使用常量时间比较，避免逐字节试探
    return hmac.compare_digest(
        hashlib.sha256(presented.encode()).hexdigest(), stored_fingerprint)

h1, h2 = hash_password("Refund@2026"), hash_password("Refund@2026")
print("同一密码两次哈希相同:", h1 == h2)
print("存储格式前缀:", h1[:24] + "...")
print("正确密码校验:", verify_password("Refund@2026", h1))
print("错误密码校验:", verify_password("refund@2026", h1))

raw, fingerprint = issue_api_key()
print("签发 Key 前缀:", raw[:12], "长度:", len(raw))
print("库中指纹前缀:", fingerprint[:12] + "...")
print("Key 校验通过:", check_api_key(raw, fingerprint))
print("伪造 Key 校验:", check_api_key(raw + "x", fingerprint))
```

运行 `python3 password_demo.py` 的预期输出（耗时和随机前缀随机器不同）：

```text
同一密码两次哈希相同: False
存储格式前缀: scrypt$16384$8$1$/1cGkn...
正确密码校验: True
错误密码校验: False
签发 Key 前缀: sk_live_Qwnv 长度: 40
库中指纹前缀: e3754de47398...
Key 校验通过: True
伪造 Key 校验: False
```

三处设计值得记住：随机盐让“同一密码同一哈希”的批量攻击失效；把参数写进存储格式使成本可以逐年上调；`compare_digest` 消除计时侧信道。API Key 可用无盐 SHA-256，因为它是高熵随机串，没有字典攻击空间；人选密码必须加盐慢哈希。

## 动手实验

### 任务：为客服后台补上 TOTP 第二因素

前置条件：已完成最小示例，本机有 Python 3.9+，能运行 `python3`。不需要手机，也不需要联网。

1. 用标准库实现 TOTP 生成与校验，先对照 RFC 6238 的公开测试向量确认算法正确。

```python
import base64
import hashlib
import hmac
import struct

def totp(secret_b32: str, at: int, step: int = 30, digits: int = 6) -> str:
    # 时间窗编号即 HMAC 的消息，时间推进时编号自然变化
    counter = at // step
    msg = struct.pack(">Q", counter)          # 8 字节大端整数，RFC 4226 规定
    mac = hmac.new(base64.b32decode(secret_b32), msg, hashlib.sha1).digest()
    offset = mac[-1] & 0x0F                   # 动态截断：取末字节低 4 位作偏移
    code = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)

secret = base64.b32encode(b"12345678901234567890").decode()
print("t=59 六位:", totp(secret, 59))
print("t=59 八位:", totp(secret, 59, digits=8))
```

预期输出 `287082` 和 `94287082`，与 RFC 6238 附录 B 的测试向量一致。若不一致，先检查 Base32 解码和 `>Q` 字节序，而不是怀疑时间窗。

2. 写校验函数：接受 `-1/0/+1` 三个时间窗，允许 30 秒时钟漂移；把用过的计数器写入集合，第二次出现即拒绝。

3. 模拟一次登录：第一次提交正确验证码应通过，紧接着重复提交同一验证码应被拒绝，并记录“重放”事件；再把同一账号连续 5 次失败接入锁定策略。

4. 验证方法：用 `at=59` 与 `at=89` 两次调用，确认窗口内通过、窗口外失败；把系统时间改快 5 分钟，确认仍能登录但日志出现“窗口偏移”告警。

清理方法：实验全在本地进程内完成，不写数据库、不发请求，删除临时脚本即可；若曾把测试种子写进任何文件，一并删除并轮换该种子。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 两个测试账号密码相同，库中哈希也相同 | 未加盐，或用了固定盐 | 注册两个相同密码账号，比较两条记录 | 每用户随机盐，改用带参数的慢哈希并迁移旧记录 |
| 用户改密后旧设备仍然登录 | 只更新了密码，未吊销 Session | 改密后拿旧 Cookie 请求受保护接口 | 改密、重置、换岗时删除全部 Session 并轮换 ID |
| 前端能直接搜到 API Key | Key 被写进 JS、安装包或配置模板 | 在打包产物和仓库历史中搜索 `sk_live` | 服务端持有 Key，前端改用短期令牌；立即轮换并吊销旧 Key |
| 日志出现完整 Key 或验证码 | 中间件打印了请求头或请求体 | 在日志平台按前缀检索 | 只记录前缀指纹，统一脱敏后再落盘 |
| Safari 下登录后立刻掉线 | `SameSite=None` 却未配 `Secure`，或跨站场景未放行 | 对比浏览器请求头里的 Cookie | 按部署形态选择 `Lax`/`None` 并强制 HTTPS |

## 安全与生产注意事项

**<u>把 API Key、Session 签名密钥或数据库密码写进前端代码、移动端安装包和公开仓库，等同于直接公开。</u>** 客户端或镜像层可读的字符串都不是秘密；攻击者无需破解即可冒用调用方身份，且常在轮换前潜伏。缓解：密钥只存在于服务端或密钥管理服务，客户端改用短期令牌，并在 CI 中加入密钥扫描。

**<u>永不过期的 Session 和永不轮换的 API Key 会把一次泄露变成永久后门。</u>** 日志、代理、备份和浏览器扩展都可能留存凭据，有效期越长暴露面越大。缓解：Session 设置闲置与绝对超时，API Key 设置过期时间，并演练一次完整轮换，确认旧 Key 确实失效。

**<u>在日志、工单和监控里记录完整密码、一次性验证码或 Key，会造成二次泄露。</u>** 这类数据常被复制到聊天群和报表，扩散范围难以回收。缓解：采集端统一脱敏，只保留前缀和哈希指纹，并对日志访问做权限控制和审计。

## 本课总结

- **密码**只存加盐慢哈希摘要，参数随记录保存，校验用常量时间比较。
- **MFA** 的价值来自因素类型不同；TOTP 可被钓鱼转发，Passkey 因私钥不出设备而抗钓鱼。
- **Session** 适合人在浏览器里的连续操作，可即时吊销，但需服务端共享存储。
- **API Key** 适合系统间调用，标识应用而非个人，须限定 scope、来源和有效期。
- 凭据设计三条底线：能过期、能吊销、能审计到具体使用方。

## 思考题

晴空商城计划让客服在手机上审批退款。若沿用“密码 + 短信验证码”，请分析客服出差、换号、批量审批三种情况各会出什么问题；再给出更合适的方案，并说明它在成本、可用性和抗钓鱼能力上的取舍。

参考思路：短信依赖运营商与手机号归属，换号和出境漫游会造成不可用，SIM 交换攻击还可绕过；批量审批逐笔验证码会显著降低效率，可能诱导客服共享验证码。可考虑 Passkey 绑定设备、低额退款只做一次会话认证、高额退款要求设备内生物确认，并对异常地点告警与人工复核。评价标准：是否说明失效场景、是否给出降级路径、是否明确谁承担风险。

## 小测

1. 下列哪种做法能让“两个用户设置相同密码”时数据库中的值不同？  
   A. 使用更长的密码　B. 为每个用户生成随机盐　C. 把哈希算两遍　D. 使用 Base64 编码
2. TOTP 校验为什么要允许前后各一个时间窗？
3. Session ID 与 API Key 在“代表谁”这一点上有何本质区别？
4. 把 API Key 存进数据库时，为什么可以只存无盐 SHA-256 指纹，而密码不可以？
5. 场景题：客服主管要求“给仓库对接发一个管理员账号，密码写在配置里，方便排查”。你接受吗？说明理由与替代方案。

## 答案与解析

1. **B。**随机盐让每次哈希的输入不同，相同密码得到不同摘要。A 不能阻止相同密码同摘要；C 结果仍确定；D 是可逆编码。
2. 设备与服务端的时钟不可能完全一致，网络延迟也会让验证码落入相邻窗口。允许 ±1 窗口是可用性与安全性的折中，代价是有效期从 30 秒扩到 90 秒，因此必须配合“同一计数器只用一次”的防重放记录。
3. Session ID 代表一个已认证的*人*的登录状态，服务端知道 `user_id` 和角色，可精确吊销；API Key 代表*调用方应用*，常由多个任务甚至多人共用，出问题只能追到应用。
4. API Key 是高熵随机串，无字典攻击空间；密码出自有限且高度重复的分布，必须用盐破坏预计算表、用慢哈希抬高猜测成本。密码若做无盐 SHA-256，一张彩虹表就能批量还原。
5. 不接受。管理员账号加明文密码意味着权限过大、无法追责、配置泄露即全盘失守，“方便排查”不该以长期高权限凭据为代价。替代方案：签发限定 scope 的 API Key、限制 IP、设置过期与轮换，并提供只读日志与请求追踪；人工介入用带审批和时效的临时凭据。

### 动手实验参考

TOTP 的关键是用 `>Q` 打包计数器、按末字节低 4 位动态截断、对 31 位结果取模。维护“已用计数器”集合即可阻止同码重放；担心集合无限增长时可按时间窗滚动清理。窗口偏移告警比直接拒绝更有用，它能提前暴露 NTP 故障。

## 延伸阅读与下一课

- [NIST SP 800-63B：数字身份认证指南](https://pages.nist.gov/800-63-3/sp800-63b.html)，关于密码长度、黑名单与 MFA 的权威要求。
- [OWASP 密码存储备忘录](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)，各算法参数与迁移建议。
- [OWASP 会话管理备忘录](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)，Cookie 属性与超时设计。
- [RFC 6238：TOTP 算法](https://www.rfc-editor.org/rfc/rfc6238)，含可直接对照的测试向量。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[认证、授权与审计](01-authentication-authorization-and-audit.md)。
- 下一课：[JWT 结构、签发与校验](03-jwt-structure-and-validation.md)。
