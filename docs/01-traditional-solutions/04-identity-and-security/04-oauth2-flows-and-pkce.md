---
title: OAuth 2.0 授权流程与 PKCE
slug: oauth2-flows-and-pkce
module: traditional-solutions
stage: design
type: core
difficulty: intermediate
duration: 60m
prerequisites:
  - jwt-structure-and-validation
outcomes:
  - 区分 OAuth 2.0 的四个角色，并把它们对应到晴空商城的具体系统
  - 说明授权码加 PKCE 的换取过程，指出 code_challenge 与 code_verifier 各自出现的时机
  - 判断需求该用授权码流程还是客户端凭证流程，并为接口设计最小 scope
last_reviewed: 2026-10-19
---

# OAuth 2.0 授权流程与 PKCE

## 为什么需要学习

晴空商城最近有三个需求：运营要用第三方 SaaS 工具看订单与退款报表；客服想在新采购的工单系统里直接点“发起退款”；三家仓库供应商要回传发货状态。

三者都能被同一种最省事的办法解决——把账号密码交给对方。后果可预期：运营离职后工具仍在用他的密码拉数据，工单系统库里躺着四十名客服的密码，仓库能读到的数据远超发货所需。密码限定不了范围，撤销不了单个应用，也说不清“这次操作是哪个应用代表谁做的”。

OAuth 2.0 就是为这件事设计的框架：让*资源所有者*把一部分权限，以可限定范围、可过期、可撤销的方式借给第三方，而第三方永远拿不到密码。

> **核心结论：** OAuth 的价值不在“发放令牌”，而在于**用 scope 把权限切小、用短有效期把时间窗切小、用撤销能力把损失封顶**。

## 学习目标

完成本课后，你能够：

- 区分 OAuth 2.0 的四个角色，并为“一键退款”与“仓库回传”标出每个角色由谁担任。
- 说明授权码加 PKCE 的换取过程，指出 `code_challenge` 与 `code_verifier` 各在哪一步出现，以及它为何能阻止授权码被复用。
- 判断一个接入需求该用授权码流程还是客户端凭证流程，并写出依据。
- 为退款接口设计最小 scope，并指出该接口必须拒绝的越权请求。

## 前置知识

- 回看上一课：[JWT 结构、签发与校验](03-jwt-structure-and-validation.md)。
- 知道 `302` 跳转、URL 查询串与 `Authorization` 请求头各自的作用。
- 知道 HTTP 无状态，令牌本身必须携带“这次请求代表谁”。
- 能读懂 Python 3 的类与字典，会用 `hashlib`、`hmac`、`secrets`。

## 业务场景

“工单系统内一键退款”要回答四个问题：工单系统凭什么代表客服 cs-1024 调退款接口？客服只能处理自己负责的工单，限制写在哪？换岗离职或工单系统被入侵，怎么在几分钟内掐断？仓库系统无人在场时“代表谁”？

前三个指向授权码流程，第四个指向客户端凭证。两者共用同一套角色与令牌格式，但信任来源不同：前者信任“用户当场同意过”，后者信任“应用自己持有的密钥”。

## 核心概念

*OAuth 2.0* 是授权框架，规定应用如何在不接触用户密码的前提下取得限定范围的访问令牌。它解决授权，不解决“证明用户是谁”，后者属于 OpenID Connect。

| 角色 | 含义 | 一键退款中由谁担任 |
| --- | --- | --- |
| *资源所有者* | 有权授予访问权限的主体 | 客服 cs-1024 |
| *客户端* | 请求并使用令牌的应用 | 第三方工单系统 |
| *授权服务器* | 认证主体、发放令牌的服务 | 商城统一身份服务 |
| *资源服务器* | 校验令牌并提供数据的服务 | 退款 API、订单 API |

- *访问令牌*是短期凭据，资源服务器凭它判断“谁、能做什么”，其中不含密码。
- *scope* 是令牌携带的权限清单，也是 OAuth 唯一的权限边界，必须由资源服务器逐请求校验。
- *授权码*是一次性、短寿命的中间凭证，只负责把“用户同意过”换成令牌。
- *PKCE*（RFC 7636）为授权码流程加一个只有发起方知道的秘密：*code_verifier* 是客户端本地生成的高熵随机串，*code_challenge* 是它的 SHA-256 摘要，随授权请求发出。
- *redirect_uri* 是回送授权码的地址，须精确白名单登记；*state* 是客户端生成并校验的随机值，用于防回调注入。
- *公共客户端*（SPA、移动 App）保不住密钥，*机密客户端*可在服务端保管；*客户端凭证*是没有用户参与的授权类型，令牌代表应用自身，*刷新令牌*用于换新令牌且必须可撤销。

| 维度 | 授权码 + PKCE | 客户端凭证 |
| --- | --- | --- |
| 有没有用户在场 | 有，用户要登录并同意 | 没有 |
| 令牌代表谁 | 用户，`sub` 是 cs-1024 | 应用自身，`sub` 为空 |
| 权限来源 | 用户当场的*委托授权* | 应用注册时被授予的 scope |
| 能否细到个人 | 能，可审计到人 | 不能，只能追到应用 |

## 工作原理

**授权码加 PKCE**

1. 客服在工单系统点击“发起退款”。
2. 工单系统本地生成 `code_verifier`，算出 `code_challenge = base64url(sha256(verifier))`；verifier 留在服务端会话，只把摘要发出去。
3. 浏览器跳到授权服务器 `/authorize`，携带 `client_id`、`redirect_uri`、`response_type=code`、`scope`、`state`、`code_challenge` 与 `code_challenge_method=S256`。
4. 授权服务器认证客服并展示*同意页*。同意后它核对 `client_id`、`redirect_uri` 与登记值完全一致，生成短寿命授权码，用 `302` 回送并原样带回 `state`。
5. 工单系统先比对 `state` 再动作，不一致直接丢弃；这防的是有人把受害者浏览器引到你的回调地址并塞入属于自己的授权码。
6. 后端用 `code`、`code_verifier`、`client_id`、`redirect_uri` 向 `/token` 换取令牌，浏览器不参与。
7. 授权服务器对收到的 verifier 重算 SHA-256 并与 challenge 比对；verifier 只在此刻出现，仅截获授权码的人算不出它。
8. 通过后立即把授权码标记为已使用，返回 `access_token`、可选的 `refresh_token` 和实际授予的 scope；同一授权码第二次提交必须失败。
9. 工单系统带 `Authorization: Bearer <token>` 调退款 API；资源服务器验令牌、验 scope，再从主体取出“代表 cs-1024”写入审计日志。

**客户端凭证**

1. 商城为每家仓库注册客户端，签发 `client_id` 与密钥，密钥存入对方的密钥管理服务，不写进代码。
2. 仓库系统直接向 `/token` 提交 `grant_type=client_credentials` 与自己的凭据。
3. 校验通过后发放令牌，主体是应用自身，没有用户主体。
4. 仓库用它回传发货状态；资源服务器按 scope 放行、按 `client_id` 限流记账，轮换密钥时新旧并存一个切换窗口。

**令牌代表应用时，“操作人”必须由请求显式提供并单独校验，绝不能从令牌推断。**这是客户端凭证流程最容易被忽略的边界。

## 架构与选型

| 接入场景 | 推荐流程 | 选它的理由 | 不适用或需注意 |
| --- | --- | --- | --- |
| 第三方 Web 应用代表客服操作 | 授权码 + PKCE，机密客户端 | 用户在场，可撤销到人 | 同意页必须列清 scope，不默认全选 |
| SPA 或移动 App | 授权码 + PKCE，禁用 `client_secret` | 保不住密钥，PKCE 是唯一绑定手段 | 令牌存内存，别长期放 `localStorage` |
| 仓库、财务等系统间调用 | 客户端凭证 | 无人在场，应用身份足够 | 令牌无操作人，业务须另传并校验 |
| 支付回调、Webhook 接收 | 签名校验加时间戳 | 对方不是你的用户，没有令牌可发 | 不要复用 API Key 或 OAuth 令牌 |

判断顺序是固定的：**先问“用户是否在场”，再问“客户端能否保住密钥”，最后问“权限是否要细到人”。**三个答案决定流程，而不是先挑协议再找场景。不适用之处也要说清：OAuth 不是组织内部的权限模型，客服能退多大金额属于 RBAC/ABAC；它也不替代审计与限流。把它当成权限系统的全部，会做出“有令牌就能退任何款”的漏洞。

## 最小示例

问题：验证“只有持有 `code_verifier` 的一方能拿授权码换到令牌”和“scope 不足时资源服务器拒绝请求”。环境为 Python 3 标准库，不联网。

```python
import base64
import hashlib
import hmac
import secrets
import time


def b64url(raw: bytes) -> str:
    # RFC 7636 要求无填充 base64url，保证两串能安全放进 URL 与表单
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def new_verifier() -> str:
    # verifier 是客户端本地生成的高熵随机串，32 字节编码后正好 43 字符
    return b64url(secrets.token_bytes(32))


def s256_challenge(verifier: str) -> str:
    # 授权请求只出示摘要，真正的 verifier 留到换令牌时才提交
    return b64url(hashlib.sha256(verifier.encode("ascii")).digest())


class OAuthError(Exception):
    # 按 RFC 6749 §5.2 返回标准错误码，不泄露内部失败原因
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class AuthServer:
    def __init__(self) -> None:
        self.codes: dict[str, dict] = {}    # 授权码一次性，服务端保存后才可与 verifier 比对
        self.tokens: dict[str, dict] = {}   # 访问令牌 -> 主体与 scope
        self.ttl_code, self.ttl_token = 60, 300

    def authorize(self, client_id, redirect_uri, challenge, scope, sub):
        code = b64url(secrets.token_bytes(16))
        self.codes[code] = {
            "client_id": client_id, "redirect_uri": redirect_uri,
            "challenge": challenge, "scope": set(scope), "sub": sub,
            "used": False, "expires_at": time.time() + self.ttl_code,
        }
        # 真实系统用 302 把 code 送到 redirect_uri，这里直接返回便于单进程观察
        return code

    def token(self, code, verifier, client_id, redirect_uri):
        rec = self.codes.get(code)
        # 四种失败共用同一个 invalid_grant，不给攻击者留下枚举空间
        if not rec or rec["used"] or rec["expires_at"] < time.time():
            raise OAuthError("invalid_grant")
        if rec["client_id"] != client_id or rec["redirect_uri"] != redirect_uri:
            raise OAuthError("invalid_grant")
        if not hmac.compare_digest(s256_challenge(verifier), rec["challenge"]):
            raise OAuthError("invalid_grant")   # verifier 与 challenge 不匹配
        rec["used"] = True                      # 立即作废，同一授权码不能换第二次
        token = b64url(secrets.token_bytes(24))
        self.tokens[token] = {"sub": rec["sub"], "scope": rec["scope"],
                              "expires_at": time.time() + self.ttl_token}
        return {"access_token": token, "token_type": "Bearer",
                "scope": " ".join(sorted(rec["scope"]))}

    def call(self, token, needed_scope, action):
        rec = self.tokens.get(token)
        if not rec or rec["expires_at"] < time.time():
            raise OAuthError("invalid_token")        # 401：令牌无效或过期
        if needed_scope not in rec["scope"]:
            raise OAuthError("insufficient_scope")   # 403：令牌有效但权限不足
        return f"{action} 由 {rec['sub']} 发起"


srv = AuthServer()
cb = "https://help.qingkong.example/oauth/cb"
verifier = new_verifier()
challenge = s256_challenge(verifier)
print("verifier 长度:", len(verifier))
print("challenge 长度:", len(challenge))

code = srv.authorize("ops-desk", cb, challenge, ["orders:read"], "cs-1024")
tok = srv.token(code, verifier, "ops-desk", cb)
print("换取令牌成功:", tok["token_type"], "scope:", tok["scope"])
print("读订单:", srv.call(tok["access_token"], "orders:read", "读取订单 SO-20261019-0042"))

try:
    srv.token(code, verifier, "ops-desk", cb)          # 重放同一个授权码
except OAuthError as err:
    print("重放授权码:", err.code)

code2 = srv.authorize("ops-desk", cb, challenge, ["orders:read"], "cs-1024")
try:
    srv.token(code2, verifier + "x", "ops-desk", cb)   # 攻击者只有摘要，猜不出 verifier
except OAuthError as err:
    print("错误 verifier:", err.code)

try:
    srv.call(tok["access_token"], "refunds:write", "发起退款")
except OAuthError as err:
    print("越权退款:", err.code)
```

运行 `python3 pkce_demo.py` 的预期输出：

```text
verifier 长度: 43
challenge 长度: 43
换取令牌成功: Bearer scope: orders:read
读订单: 读取订单 SO-20261019-0042 由 cs-1024 发起
重放授权码: invalid_grant
错误 verifier: invalid_grant
越权退款: insufficient_scope
```

三处设计值得记住：只暴露摘要，使授权码被截获也换不到令牌；授权码用完即废；scope 校验在资源服务器而非靠调用方自觉。`invalid_token` 要求重新认证，`insufficient_scope` 要求重新授权，两者不可混用。

## 动手实验

### 任务：给示例补上四条真实世界规则

前置条件：已完成最小示例，本机有 Python 3.9+，不需要联网或注册应用。

1. 加入 `state` 校验：客户端生成随机 `state` 写入会话，回调时先比对再换令牌。
2. 把授权码记录的 `expires_at` 减 1 再换取，观察错误码。
3. 增加 `token_client(client_id, client_secret, scope)`：用 `hmac.compare_digest` 比对密钥，发放 `sub` 为 `None` 的令牌；退款接口在该令牌缺少 `operation_by` 时返回 `operation_by_required`。
4. 用 `token_client` 申请只含 `shipping:read` 的令牌，再调退款接口。

| 用例 | 观察点 | 预期结果 |
| --- | --- | --- |
| `state` 不匹配 | 是否先校验再换令牌 | 丢弃回调，换取请求数为 0 |
| 授权码过期 | 错误码是否与“已使用”一致 | `invalid_grant` |
| 客户端凭证缺操作人 | 能否从令牌推出操作人 | `operation_by_required` |
| scope 收窄 | 拒绝发生在哪一层 | `insufficient_scope`，日志记 403 |

验证方法：为每个用例打印“是否抛错 + 错误码 + 是否写审计日志”三元组，四组齐全才算通过；若审计里大量出现“操作人为空”，说明第 3 条没有落地。

清理方法：实验全在单进程内完成，不落库、不发请求，删除临时脚本即可；若把测试密钥或 verifier 写进了文件或日志，一并删除并轮换真实凭据。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 换取令牌总是 `invalid_grant` | 授权码已使用或已过期 | 查授权服务器日志中该 code 的状态与时间戳 | 有效期控制在 60 秒内，且一次一换 |
| 同上，但授权码是新生成的 | `redirect_uri` 与登记值不完全一致 | 逐字符比对，注意末尾斜杠与端口 | 精确白名单登记，不做前缀匹配 |
| 加了 PKCE 仍 `invalid_grant` | 用了 `plain`，或对 verifier 二次编码 | 打印两端 challenge 前 8 位比对 | 固定 `S256`，按 ASCII 哈希且不重复编码 |
| 移动端令牌被他人换走 | 公共客户端未启用 PKCE，回调 scheme 被抢占 | 抓包看授权请求有无 `code_challenge` | 强制 PKCE，改用 App 链接或声明式回调 |
| 仓库接口出现无法追溯的退款 | 客户端凭证令牌被当成用户令牌 | 令牌 `sub` 是否为空 | 业务显式传操作人并校验，禁止从令牌推断 |

## 安全与生产注意事项

**<u>公共客户端若不用 PKCE，或用 `code_challenge_method=plain`，授权码一旦被拦截就能直接换出令牌。</u>** 拦截并不罕见：自定义回调 scheme 会被恶意应用抢占，完整跳转 URL 会留在日志与代理里。缓解方式是对所有客户端强制 `S256`，并在授权端点拒绝 `plain` 与缺失 challenge 的请求。

**<u>把访问令牌放进 URL 查询串，或在网关日志里完整记录 `Authorization` 头，等于把令牌复制到多个可读位置。</u>** 浏览器历史、Referer、代理日志、APM 采样都会留存，事后无法确认泄露范围。缓解方式是只走 `Authorization: Bearer`，采集端统一脱敏，寿命控制在分钟级并保留按令牌追溯的审计。

**<u>给第三方一个“读取全部订单、可发起任意退款”的大 scope，等于一次授权交出退款权限全集。</u>** 第三方被入侵或出 bug 时，爆炸半径覆盖所有顾客与金额。缓解方式是按资源与动作拆分 scope（`orders:read`、`refunds:read`、`refunds:write`），高风险动作加金额上限与人工复核，并按 client 限流告警。

## 本课总结

- **OAuth 是授权框架，不是认证协议**：第三方拿到的是限定范围的令牌，不是密码；证明用户是谁属于 OpenID Connect。
- **授权码加 PKCE 靠三件事成立**：授权码一次性且短命、challenge 与 verifier 分两步出现、`state` 把回调绑回本次会话。
- **流程由三个问题决定**：用户是否在场、客户端能否保住密钥、权限是否要细到人。
- **scope 是唯一权限边界**，须在资源服务器逐请求校验；令牌代表应用时，操作人还必须显式传递并校验。

## 思考题

运营团队要求：给第三方报表工具一个有效期一年、scope 为 `orders:read refunds:read` 的刷新令牌，理由是“体验顺滑”；该工具还会缓存数据并把报表分享到外部协作平台。请指出它在哪些环节放大了风险，给出替代方案，并说明若业务坚持“一年免重授权”，你要求哪些补偿控制。

参考思路：先区分“减少用户打扰”和“减少凭据暴露”。长效刷新令牌加宽 scope，等于让外部工具一年内随时读取全部订单与退款；叠加缓存与外部分享后，数据已流出可控范围。替代方案：短效访问令牌加刷新令牌轮换（作废旧令牌，异常即吊销）、scope 收窄到聚合统计、逐单脱敏。若业务坚持，至少要求：令牌可即时撤销并有撤销演练、按 client 的审计与告警、数据留存与外传的书面约束。评价看能否分清“体验”与“凭据寿命”、指出失控点、给出可执行控制。

## 小测

1. 授权码流程中，`code_challenge` 与 `code_verifier` 分别在哪一步出现？  
   A. 都在授权请求里　B. challenge 在授权请求，verifier 在令牌请求　C. 都在令牌请求里　D. verifier 在授权请求，challenge 在令牌请求
2. `state` 主要防什么？换成固定值会怎样？
3. 客户端凭证流程的令牌，为什么不能用来判断“这次退款是谁批的”？
4. 资源服务器收到合法但不含 `refunds:write` 的令牌，应返回 `invalid_token` 还是 `insufficient_scope`？
5. 场景题：工单系统提出“回调域名随环境变化，别做 `redirect_uri` 白名单，用通配符最省事”。你接受吗？说明理由与替代做法。

## 答案与解析

1. **B。**challenge 随 `/authorize` 发出，verifier 只在 `/token` 提交，这正是 PKCE 的关键：只截获授权码拿不到 verifier。A 提前暴露 verifier，拿到跳转 URL 即可换令牌；C 让服务端无从绑定，等于没有 PKCE；D 位置颠倒，把秘密交给浏览器，同样失去意义。
2. 防回调注入：攻击者诱导受害者浏览器访问构造好的回调地址，塞入属于攻击者的授权码，把受害者账号与攻击者应用静默绑定。固定 `state` 是公开常量，校验形同虚设；应每次生成高熵随机值，存会话并在回调时比对一次后作废。
3. 令牌主体是应用自身，`sub` 为空，协议层面没有用户信息；把它当操作人，就是把“某个系统调用过”错记成“某人批准过”。应让请求显式携带 `operation_by`，服务端校验权限后写审计，并保留 `client_id` 追溯调用方。
4. 应返回 `insufficient_scope`（通常配 403）。`invalid_token` 表示令牌不可用，应重新认证；`insufficient_scope` 表示身份没问题但权限不够，应重新授权。混用会让客户端要么反复刷新却永远 403，要么在权限不足时把用户踢下线。
5. 不接受。`redirect_uri` 是授权码的唯一投递地址，通配符等于允许任意域接收授权码，攻击者可借相似域名完成开放重定向并换出代表用户的令牌。替代做法：每个环境登记精确地址（含端口与路径），新增环境走一次评审；本地开发用 `http://127.0.0.1:<端口>/cb` 这类明确条目，多地址逐条登记。

### 动手实验参考

四个用例的关键：`state` 校验必须发生在换取请求之前，否则只是装饰；授权码过期与已使用返回同一个 `invalid_grant`，是为了不让攻击者区分“过期”与“被人用了”；客户端凭证令牌 `sub` 为空，须在业务层强制 `operation_by`；scope 校验在资源服务器，先判有效性再看 scope，两个错误码不可合并。

## 延伸阅读与下一课

- [RFC 6749：OAuth 2.0 授权框架](https://www.rfc-editor.org/rfc/rfc6749)，四种授权类型与错误码的原始定义。
- [RFC 7636：PKCE](https://www.rfc-editor.org/rfc/rfc7636)，`code_verifier` 规则与 S256 变换，附录含可对照示例值。
- [RFC 9700：OAuth 2.0 安全最佳实践](https://www.rfc-editor.org/rfc/rfc9700)，强制 PKCE、`redirect_uri` 精确匹配与刷新令牌轮换的共识。
- [RFC 6750：Bearer 令牌的使用](https://www.rfc-editor.org/rfc/rfc6750)，`Authorization` 头格式与两个错误码语义。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[JWT 结构、签发与校验](03-jwt-structure-and-validation.md)。
- 下一课：[OpenID Connect 与身份令牌](05-openid-connect-and-id-tokens.md)。
