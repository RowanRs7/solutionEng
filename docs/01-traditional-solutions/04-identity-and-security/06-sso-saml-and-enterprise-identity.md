---
title: SSO、SAML 与企业身份接入
slug: sso-saml-and-enterprise-identity
module: traditional-solutions
stage: design
type: core
difficulty: intermediate
duration: 60m
prerequisites:
  - openid-connect-and-id-tokens
outcomes:
  - 区分 SSO 的四种形态、说明每种形态信任谁，并据此为给定场景选型
  - 按顺序复述 SAML Web Browser SSO 的报文往返，并列出 SP 必须校验的字段
  - 用 SCIM 或定时对账设计账号的入职、改岗、离职三条路径
last_reviewed: 2026-10-19
---

# SSO、SAML 与企业身份接入

## 为什么需要学习

晴空商城接入第一个企业客户时，对方只提一个要求：员工用公司账号登录我们的采购门户，不再注册一套密码。团队两周做出“点一下就跳转”的效果，上线才是麻烦的开始：客户 A 用微软 AD，客户 B 用 Okta，客户 C 的老工单 SaaS 只认 SAML，而新门户默认走 OIDC；客服发现离职三个月的采购员还能登录，对方 IdP 已停用账号，我们本地那份还活着；审计问“这单是谁下的”，我们只存了邮箱，而同一邮箱在两个客户下指向不同的人。

三次都不是密码问题，而是三件事没定清楚：身份由谁签发、我们凭什么相信一张断言、账号什么时候该不存在。

> **核心结论：** 企业身份接入的难点不在“跳一次登录页”，而在于把“谁签发身份、断言凭什么可信、账号在离职当天怎么消失”这三件事写成可验证的约定。

## 学习目标

完成本课后，你能够：

- 区分同域会话、反向代理注入、SAML、OIDC 四种形态，说出各自信任谁，并为给定场景选型。
- 按顺序复述 SAML 断言往返的 8 个步骤，列出 SP 收到断言后必须校验的 7 项内容。
- 为入职、改岗、离职设计三条可验证的账号生命周期路径，并指出只靠 SSO 会漏掉哪一段。

## 前置知识

- 回看上一课：[OpenID Connect 与身份令牌](05-openid-connect-and-id-tokens.md)。
- 能区分认证（你是谁）与授权（你能做什么），知道 401 与 403 的差别。
- 理解非对称签名：私钥签发、公钥校验，校验方无法伪造。
- 本机可运行 `python3 --version`；示例只用标准库，不联网。

## 业务场景

晴空商城（商城、订单、支付、仓储、客服、退款）在同一年面对三种接入需求：

- **内部员工**约 400 人，用公司统一 IdP 登录客服工作台、退款审核台、仓储看板、财务对账等 6 个系统，人力要求“入职当天开通、离职当天关闭”。
- **两个 B2B 客户**要求用各自 IdP 登录企业采购门户，只看到本公司的订单与额度。
- **仓储外包人员**只用扫码端，甲方要求按班次授权、班次结束失效。

约束也很具体：客服工单系统是十年前的 SaaS，只支持 SAML 2.0；新退款服务基于 OIDC；财务要求审计能回答“操作人来自哪个 IdP、用什么 NameID”。三条叠在一起，决定了不能只选一个协议了事。

## 核心概念

*SSO*（Single Sign-On，单点登录）指用户在一个身份系统完成认证后，访问多个独立系统时不再重复输入凭据。

- *身份提供者*（IdP，Identity Provider）负责认证并签发断言或令牌，是企业身份的权威来源。
- *服务提供者*（SP，Service Provider）是接受断言的业务系统，退款审核台就是一个 SP。
- *联合身份*（federation）指跨组织信任：客户 A 的 IdP 与我们互认，因此不必给对方员工开本地账号。
- *SAML 2.0* 是基于 XML 的断言协议：IdP 用私钥签一份 XML *断言*（assertion，含主体、属性与有效期），由浏览器带给 SP。
- *NameID* 是断言中对用户的标识；`persistent` 格式让同一用户在不同 SP 看到不同值，避免被跨系统串联。
- *属性*（attribute）是断言里的附加字段，如 `mail`、`department`、`groups`，用于映射本地角色。
- *元数据*（metadata）是 IdP 与 SP 互发的 XML 描述，含实体 ID、端点与签名证书。
- *SCIM*（System for Cross-domain Identity Management，RFC 7643/7644）是账号与组的 REST 接口，让 IdP 增删改 SP 里的账号。
- *JIT 预配*（Just-in-Time provisioning）指首次登录时按断言属性临时建号；省事，但不处理离职。

| SSO 形态 | 信任建立方式 | 典型场景 | 主要局限 |
| --- | --- | --- | --- |
| 同域共享 Cookie | 同主域下的会话 Cookie | 自建系统、同公司 | 无法跨组织 |
| 反向代理注入身份头 | 应用信任网关注入的用户名头 | 改不了代码的旧系统 | 头可被伪造，只在受控网段可用 |
| SAML 2.0 | IdP 私钥签名的 XML 断言 | 企业客户、存量 SaaS | 报文笨重、移动端体验差 |
| OIDC | IdP 签名的 ID Token（JWT） | 新系统、移动端、SPA | 须正确校验，不能只看能否解出 JSON |

**SAML 与 OIDC 不是新旧替代关系，而是由客户手里的 IdP 和应用清单共同决定的两种现实选择。**

## 工作原理

SAML 的 *Web Browser SSO Profile* 是浏览器参与的三方往返，顺序本身就有安全含义：

1. 用户访问 SP 的受保护页面，SP 没有本地会话，生成一条 *AuthnRequest*，写入请求 ID、`AssertionConsumerServiceURL`、`Issuer` 与 `Destination`，`RelayState` 设为原目标路径。
2. SP 返回 302，浏览器带着 `SAMLRequest`（deflate 后 base64）跳到 IdP 的 SSO 端点。
3. IdP 检查自己的会话。“单点”就在这里：已有会话直接签发，没有则要求登录并做 MFA。
4. IdP 签发 `Response`，内含一条断言：`NameID`、属性、`Conditions`（`NotBefore`/`NotOnOrAfter`）、`AudienceRestriction`、`SubjectConfirmationData`（`InResponseTo`、`Recipient`），整条断言用 IdP 私钥签名。
5. IdP 让浏览器 **POST** 到 SP 的 *ACS*（Assertion Consumer Service，断言接收端点），`RelayState` 原样带回。
6. SP 按固定顺序校验：签名与证书 → 签发者 → 受众是否等于自己的实体 ID → 时间条件（容许少量时钟偏差）→ `InResponseTo` 是否等于本次请求 → `Recipient` 是否等于自己的 ACS → 断言 ID 是否用过。任一步失败即拒绝，不降级为“先放行再记录”。
7. 校验通过后，SP 把 `NameID` 映射到本地用户并建立自己的会话（Cookie 或 JWT）。**这个会话的生命周期由 SP 决定，与 IdP 会话无关。**
8. 登出分两段：SP 清自己的会话；*SLO*（Single Logout）由 SP 或 IdP 发起 `LogoutRequest` 广播给各方。<u>SLO 在实践中经常只覆盖部分系统</u>，不能当作停用账号的手段。

账号生命周期走另一条通道：

9. IdP 作为权威源，在 HR 系统发生入职、改岗、离职后，调用 SP 的 `/Users` 与 `/Groups` 接口做 `POST`、`PATCH`、`DELETE`。
10. SP 把 SCIM 用户与本地账号关联，把组同步成角色，停用表现为 `active=false`。
11. 每日或每周做一次全量对账，找出 SCIM 事件丢失造成的僵尸账号。

两条通道的分工要写清楚：**SAML 与 OIDC 解决“怎么登录”，SCIM 解决“账号什么时候存在”。**只做前者，离职账号会一直活到你偶然发现它。

## 架构与选型

| 场景 | 建议 | 依据 |
| --- | --- | --- |
| 客户 IdP 只支持 SAML，系统又不能改 | SAML 2.0 | 协议由对方存量能力决定 |
| 新系统、移动端、需要细粒度授权 | OIDC + OAuth 2.0 | 令牌易校验，可携带 `scope` |
| 同公司自建系统、同主域 | 共享会话 Cookie | 成本最低，不必引入协议栈 |
| 内网旧系统只认请求头 | 反向代理注入 | 只在受控网段生效，应用不暴露公网 |
| 20 个用户的一次性项目 | 不接 SSO，人工建号 | 集成与运维成本高于收益 |
| 跨组织且要按客户隔离数据 | 联合身份 + 租户映射 | `NameID` 不等于租户 |

选型看三条：

- **协议由上游决定。**先问客户 IdP 支持什么，不要选完技术再要求客户改造。
- **生命周期单独设计。**SCIM、登录时校验 `active`、定时对账，三者至少有一个。
- **SLO 不是安全控制。**登出是体验，停用是安全，实现路径不同。

## 最小示例

问题：用 Python 标准库接收一条 base64 编码的 SAML `Response`，依次校验签发者、受众、时间、`InResponseTo`、`Recipient` 与重放，观察九种输入各自被哪一步拦下或放行。

环境 Python 3.8+，只用标准库，不联网。**签名校验是桩函数**：标准库做不了 XML DSig（XML 数字签名规范），生产必须用 `xmlsec1` 或 `lxml` 配 IdP 元数据里的证书。

```python
import base64
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

NS = {"samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
      "saml": "urn:oasis:names:tc:SAML:2.0:assertion"}
IDP = "https://id.qingkong.example"       # 唯一可信签发者
SP = "https://refund.qingkong.example"    # 本服务实体 ID，也是断言的 Audience
ACS = SP + "/saml/acs"                    # 断言必须被投递到这个地址
NOW = datetime(2026, 10, 19, 10, 0, 0, tzinfo=timezone.utc)
USED = set()                              # 已用过的断言 ID；生产中必须放共享存储

def parse_instant(text):
    # xs:dateTime 的 Z 表示 UTC；统一成带时区的 datetime 再比较，避免字符串比较出错
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

def verify_signature(xml_bytes, assertion_id):
    # 生产实现必须用 IdP 元数据中的证书验签，并确认签名引用正好指向这条断言
    # 标准库没有 XML DSig，这里用桩函数占位，只为让其余校验分支能被单独演示
    if b"sig-placeholder" not in xml_bytes:
        raise ValueError("签名缺失")

def check(raw_b64, in_response_to, now, verify=verify_signature, skew=60):
    raw = base64.b64decode(raw_b64, validate=True)   # 传输层只是 base64，不是加密
    if len(raw) > 200_000:                           # 解析前先限流，别把 XML 当免费资源
        raise ValueError("报文过大")
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ValueError("禁止 DTD 与实体声明")       # 防 XXE 与实体膨胀
    root = ET.fromstring(raw)
    status = root.find("samlp:Status/samlp:StatusCode", NS)
    if status is None or status.get("Value") != "urn:oasis:names:tc:SAML:2.0:status:Success":
        raise ValueError("状态不是 Success")
    if root.get("Destination") != ACS:
        raise ValueError("总体应答的接收方不是本 SP 的 ACS")
    assertions = root.findall("saml:Assertion", NS)
    if len(assertions) != 1:
        raise ValueError(f"断言数量异常：{len(assertions)}")  # 签名覆盖缺陷常靠塞多条断言
    assertion = assertions[0]
    verify(raw, assertion.get("ID"))                 # 先验签，之后才允许读任何字段
    if assertion.findtext("saml:Issuer", namespaces=NS) != IDP:
        raise ValueError("签发者不是可信 IdP")
    conditions = assertion.find("saml:Conditions", NS)
    audiences = [node.text for node in
                 conditions.findall("saml:AudienceRestriction/saml:Audience", NS)]
    if SP not in audiences:                          # 相等判断，不是子串包含
        raise ValueError(f"受众不符：{audiences}")
    not_after = parse_instant(conditions.get("NotOnOrAfter"))
    if now - timedelta(seconds=skew) >= not_after:   # 容忍有限时钟偏差，不是无限
        raise ValueError("断言已过期")
    data = assertion.find("saml:Subject/saml:SubjectConfirmation/saml:SubjectConfirmationData", NS)
    if data.get("InResponseTo") != in_response_to:   # 防“别人发起的断言被塞给我”
        raise ValueError("应答与本次请求不匹配")
    if data.get("Recipient") != ACS:
        raise ValueError("断言的接收方不是本 SP 的 ACS")
    assertion_id = assertion.get("ID")
    if assertion_id in USED:                         # 防重放：同一断言只准用一次
        raise ValueError("断言已被使用（重放）")
    USED.add(assertion_id)
    return assertion.findtext("saml:Subject/saml:NameID", namespaces=NS)

def make_response(aid="a_1", nameid="u_10086", audience=SP, not_after="2026-10-19T10:05:00Z",
                  in_response_to="req-1", issuer=IDP, recipient=ACS, signed=True):
    # 只用于造测试报文；真实断言来自 IdP，这里不能模拟的是签名本身
    sig = ("<ds:Signature xmlns:ds='http://www.w3.org/2000/09/xmldsig#'>"
           "sig-placeholder</ds:Signature>") if signed else ""
    xml = f"""<samlp:Response xmlns:samlp="{NS['samlp']}" xmlns:saml="{NS['saml']}"
  ID="r_1" Destination="{ACS}" IssueInstant="2026-10-19T09:59:00Z">
  <samlp:Issuer>{issuer}</samlp:Issuer>
  <samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
  <saml:Assertion ID="{aid}" IssueInstant="2026-10-19T09:59:00Z">
    {sig}
    <saml:Issuer>{issuer}</saml:Issuer>
    <saml:Subject>
      <saml:NameID Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">{nameid}</saml:NameID>
      <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData InResponseTo="{in_response_to}"
          NotOnOrAfter="{not_after}" Recipient="{recipient}"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions NotBefore="2026-10-19T09:58:00Z" NotOnOrAfter="{not_after}">
      <saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>
    </saml:Conditions>
  </saml:Assertion>
</samlp:Response>"""
    return base64.b64encode(xml.encode()).decode()

def attempt(label, raw, in_response_to="req-1", now=NOW):
    try:
        name = check(raw, in_response_to, now)
        print(f"{label}: 通过 NameID={name}")
    except ValueError as exc:
        print(f"{label}: 拒绝（{exc}）")

good = make_response()
attempt("正常断言", good)
attempt("重放同一条断言", good)
attempt("换成订单服务受众", make_response(aid="a_2", audience="https://order.qingkong.example"))
attempt("子域后缀仿冒受众", make_response(aid="a_3", audience=SP + ".attacker.test"))
attempt("已过期 6 分钟", make_response(aid="a_4", not_after="2026-10-19T09:54:00Z"))
attempt("InResponseTo 不是本次请求", make_response(aid="a_5", in_response_to="req-attacker"))
attempt("签发者换成攻击者", make_response(aid="a_6", issuer="https://id.attacker.test"))
attempt("缺少签名", make_response(aid="a_7", signed=False))
attempt("回送地址被改到攻击者", make_response(aid="a_8", recipient="https://attacker.test/acs"))
```

输出（本机 Python 3 实际运行）：

```text
正常断言: 通过 NameID=u_10086
重放同一条断言: 拒绝（断言已被使用（重放））
换成订单服务受众: 拒绝（受众不符：['https://order.qingkong.example']）
子域后缀仿冒受众: 拒绝（受众不符：['https://refund.qingkong.example.attacker.test']）
已过期 6 分钟: 拒绝（断言已过期）
InResponseTo 不是本次请求: 拒绝（应答与本次请求不匹配）
签发者换成攻击者: 拒绝（签发者不是可信 IdP）
缺少签名: 拒绝（签名缺失）
回送地址被改到攻击者: 拒绝（断言的接收方不是本 SP 的 ACS）
```

整体流程分三段：`make_response` 只负责造报文，方便逐项验证；`check` 按固定顺序推进，任何一步失败都抛异常而不返回半个结果；`attempt` 让失败原因肉眼可辨。

几个设计意图。解析前检查 `<!DOCTYPE` 与 `<!ENTITY`，是防 XXE 与实体膨胀的最低成本手段。断言数量必须为 1，因为 XML Signature Wrapping 的经典手法正是往签名覆盖范围之外再塞一条断言。受众用相等判断而非包含判断——<u>改成子串匹配后，`https://refund.qingkong.example.attacker.test` 会被直接放行</u>。`USED` 在生产中必须换成共享存储，否则多副本部署时重放窗口依然存在。

## 动手实验

### 任务：让“少校验一步”和“用错比较方式”的后果可见

前置条件：`python3` 3.8+；把最小示例完整保存为 `/tmp/saml_lab.py`；无需网络与第三方库。

步骤：

1. 运行 `python3 /tmp/saml_lab.py`，确认只有“正常断言”通过。
2. 把 `if assertion_id in USED:` 到 `USED.add(assertion_id)` 这三行注释掉，重跑，“重放同一条断言”变成通过。
3. 把受众判断改成子串匹配 `if not any(SP in a for a in audiences):`，重跑，“子域后缀仿冒受众”变成通过。
4. 把 `skew=60` 改成 `skew=3600`，重跑，“已过期 6 分钟”变成通过。
5. 改回这三处，确认输出恢复原样。

预期结果：第 2 步说明防重放是独立控制，签名替代不了；第 3 步说明受众必须相等比较；第 4 步说明时钟容忍必须写死上限。

验证方法：恢复代码后输出恰好 8 行含“拒绝”、1 行含“通过”；改过受众判断的那一版能复现第 3 步的“通过”。

清理方法：`rm -f /tmp/saml_lab.py /tmp/saml_trap.py`。示例域名与证书都是占位，不得用于真实环境。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 在几个域名间来回跳，报重定向过多 | ACS 地址或 `Destination` 配错，SP 没建会话就重发 | 看 302 链上每次的 `Location`、`SAMLRequest` 是否变化 | 两端元数据里的实体 ID 与端点逐字一致 |
| 验签失败，IdP 侧却显示成功 | IdP 轮换了签名证书，SP 仍用旧的；或代理改写了 XML | 比对元数据证书指纹与断言携带的证书 | 用元数据自动刷新，别让代理重排 XML |
| 只在测试环境报 Audience 不匹配 | 多环境共用一个 IdP 应用，实体 ID 填成生产值 | 打印断言的 `Audience` 与 SP 配置 | 每环境一个 IdP 应用，实体 ID 用专属域名 |
| 登录成功但部门为空、角色没同步 | 属性名映射错，或 `NameID` 格式不符 | 导出断言看真实属性名 | 按实际属性名配置映射，留样例断言 |
| 离职员工仍能登录并审核退款 | 只做了 SSO，IdP 停用后 SP 本地账号仍有效 | 在 IdP 停用测试账号再登录 | 登录时校验 `active`；接 SCIM；每日对账 |
| 全员同时无法登录 | IdP 证书或元数据过期，或策略被误改 | 看 SP 日志里第一个失败的校验项 | 到期前 90 天告警；留受审计的应急账号 |

## 安全与生产注意事项

**<u>不做验签，或验签后不校验断言归属，等于把登录入口开在公网上。</u>** 只解析 XML 就采信字段，任何人都能构造一条“管理员”断言；只验签却不校验 `Audience` 与 `InResponseTo`，攻击者能拿别的 SP 的合法断言，或把别人发起的断言塞进你的会话，后果是账号被接管而日志里一切正常。缓解方式：用成熟库完成 XML DSig 校验、确认签名引用指向唯一断言、拒绝多断言与 DTD，把受众、接收方、请求 ID 做成硬编码校验。

**<u>只接 SSO 不管账号生命周期，离职账号会变成永久后门。</u>** IdP 停用只拦住“下一次登录”，SP 里那条本地账号和未过期会话仍可继续用。缓解方式：接 SCIM 推停用、会话短有效期并在续期时回查 `active`、高敏操作实时回查，再加全量对账兜底。

**<u>留一个不受 IdP 约束又没人审计的本地超级管理员，会在事故当天变成最大风险。</u>** 应急账号必须有，但要限定来源 IP、强制 MFA、用后轮换，并写进独立审计通道。另外，`groups` 只能采信 IdP 签发的值，报文里的工号、手机号进日志前要脱敏。

## 本课总结

- SSO 有四种形态，**信任谁**决定它的边界；跨组织只能用联合身份。
- SAML 往返是“SP 发起请求 → IdP 认证并签名断言 → 浏览器 POST 到 ACS → SP 校验 → 建本地会话”，少一步等于没做。
- SP 必须校验七项：签名、签发者、受众、时间、`InResponseTo`、`Recipient`、是否重放，顺序不能变。
- **SAML/OIDC 解决登录，SCIM 解决账号是否存在**；只做前者，离职账号永远存在。
- SLO 是体验优化，不是停用手段；停用靠 IdP 状态、SP 侧校验与对账三层。

## 思考题

客户 A 的 IdP 只支持 SAML 2.0，明确不支持 SLO，但合同要求“员工离职后 5 分钟内失去全部权限”。请给出方案：哪些能力只能落在 IdP 侧、哪些必须由 SP 补、你愿意承诺多长的失效窗口、需要客户配合什么。如果客户连 SCIM 也不开放，承诺要怎么改？

参考思路：SLO 缺席不等于无法失效。把承诺拆三层：IdP 停用后拒绝新登录；已建立的 SP 会话短有效期并滚动续期，续期时回查 `active`；退款审核、导出数据这类高敏操作实时回查。承诺应写成“新登录立即拒绝，已登录会话最长 N 分钟失效，高敏操作即时失效”，而不是笼统的“5 分钟”。需要客户配合的是开放 SCIM、停用事件可推送、提供可对账清单；若只有对账，窗口就拉长到对账周期，应如实写进合同。

## 小测

1. SAML 断言里最能限定“这条断言只能给某个 SP 使用”的字段是？  
   A. `NameID`　B. `Audience`　C. `RelayState`　D. `IssueInstant`
2. 为什么 SAML 断言要用 IdP 的私钥签名，而不是 SP 与 IdP 共享一把密钥？
3. SCIM 与 SAML 各解决什么问题？只做其中一个会留下什么缺口？
4. `RelayState` 为什么不能直接当作可信的回跳地址使用？
5. 场景题：客户要求“离职后 5 分钟内失去全部访问”，但对方 IdP 既无 SLO 也不开放 SCIM。作为架构师，你会先向客户确认哪两件事，又会把承诺改成什么？

## 答案与解析

1. **B。**`Audience` 把断言绑定到某个实体 ID，SP 必须判断它是否等于自己。A 只标识用户，同一条断言仍可能被别的 SP 接受；C 是应用层回跳提示；D 只是签发时刻。
2. 因为签名让接收方相信“内容来自可信签发者”。共享密钥时每个 SP 都能伪造断言，任一 SP 被攻破等于 IdP 被攻破；私钥签发、公钥校验才让信任单向。
3. SAML 是登录通道，解决“怎么认证并把身份传给 SP”；SCIM 是生命周期通道，解决“账号何时创建、修改、停用”。只做 SAML 会留下永久存活的离职账号；只做 SCIM 则用户仍要各自登录。
4. 因为 `RelayState` 随浏览器明文往返、可被改写，能把刚登录的用户带去钓鱼站点，形成开放重定向。应只接受站内路径白名单，或换成服务端保存的一次性票据。
5. 先确认两件事：客户 IdP 停用后能否推送事件或提供可拉取清单；我方能否在会话续期时实时查询账号状态。承诺改为分层表述：“新登录立即拒绝；已登录会话最长 N 分钟失效；高敏操作即时失效。”若连清单都拿不到，只能承诺到对账周期。

### 动手实验参考

第 2 步重放打印“通过”，说明签名合法的断言仍可能被重复使用，防重放必须独立实现。第 3 步改成子串匹配后，“子域后缀仿冒受众”打印“通过 NameID=u_10086”，这是把域名当字符串而非标识符的典型后果，结论是受众必须相等比较，比较前还要归一化大小写与末尾斜杠。第 4 步 `skew=3600` 后过期 6 分钟的断言被接受，说明时钟容忍需要明确上限。做完务必改回，确认输出恢复为 8 行拒绝、1 行通过。

## 延伸阅读与下一课

- [SAML 2.0 Core（OASIS 标准）](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)：断言、`Conditions`、`SubjectConfirmation` 的权威定义。
- [SAML 2.0 Web Browser SSO Profile](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)：本课“工作原理”所依据的报文往返。
- [SAML 2.0 Security and Privacy Considerations](https://docs.oasis-open.org/security/saml/v2.0/saml-sec-consider-2.0-os.pdf)：XML Signature Wrapping 等攻击面的官方说明。
- [RFC 7643：SCIM Core Schema](https://www.rfc-editor.org/rfc/rfc7643) 与 [RFC 7644：SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644)：账号与组接口的字段和语义。
- [NIST SP 800-63C：Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html)：联邦身份分级（FAL）与断言要求。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[OpenID Connect 与身份令牌](05-openid-connect-and-id-tokens.md)。
- 下一课：[RBAC、ABAC 与多租户权限](07-rbac-abac-and-multi-tenant-permissions.md)。
