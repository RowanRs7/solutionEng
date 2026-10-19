---
title: RBAC、ABAC 与多租户权限
slug: rbac-abac-and-multi-tenant-permissions
module: traditional-solutions
stage: design
type: core
difficulty: intermediate
duration: 60m
prerequisites:
  - sso-saml-and-enterprise-identity
outcomes:
  - 区分 RBAC 与 ABAC 的判定依据，并为退款场景的每条规则标注应使用的模型
  - 画出晴空商城的角色权限矩阵，指出角色爆炸出现的位置
  - 设计入口、数据、出口三层租户隔离校验，说明任一层失效的后果
  - 用 Python 标准库实现带租户作用域的策略判定函数，并验证越权请求被拒绝
last_reviewed: 2026-10-19
---

# RBAC、ABAC 与多租户权限

## 为什么需要学习

晴空商城转向平台后，三十家品牌商带着各自的店员共用一个后台。上线第一个月出了三件事：外包客服改掉退款地址里的 `order_id`，看到别家店铺顾客的手机号；财务为赶对账被临时加上“平台管理员”，再没回收；小店的店员既能提交退款又能自己审批。

三件事都不是密码泄露。**系统知道“你是谁”，却没回答“你能对哪一条数据做哪个动作”。**

> **核心结论：** 权限设计的目标不是把角色配齐，而是让每次访问都由可验证的规则判定，并且默认拒绝。

## 学习目标

完成本课后，你能够：

- 用“决策依据来自哪里”区分 RBAC 与 ABAC，并指出各自的失效场景。
- 写出退款流程的角色权限矩阵，说明新增一家店铺时矩阵是否要改。
- 按入口、数据、出口三层说明租户隔离，指出只做一层的漏洞。
- 用 Python 3 标准库实现策略判定函数，正确返回 `allow` 与四种 `deny` 原因。

## 前置知识

- 回看上一课：[SSO、SAML 与企业身份接入](06-sso-saml-and-enterprise-identity.md)。
- 知道认证与授权的区别，能说出 `401` 与 `403` 的含义；必要时回看[身份认证、授权与审计](01-authentication-authorization-and-audit.md)。
- 知道令牌通常带 `sub`、租户标识和角色列表，且由服务端签发。
- 能读懂 Python 3 的字典、集合、`dataclass` 与函数。

## 业务场景

退款流程没变：顾客申请，客服初审，仓库确认是否出库，财务对账。变的是参与方数量和归属。

- 店铺店员：只看本店订单，可提交退款。
- 店铺客服主管：可审批本店 5000 元以内的退款。
- 平台客服：可代任何店铺看订单，只能提交。
- 仓库操作员：只更新自己仓库的发货状态，看不到金额。
- 财务：可以打款，需完整金额与审批记录。
- 平台运营：可跨租户读数据，日常不应有写操作。

评审的问题是：新增第三十一家品牌商要不要新建角色？平台客服跨租户看单，靠什么保证改不了金额？

## 核心概念

*RBAC*（基于角色的访问控制）把权限授予角色，再把角色授予主体；判定只看主体持有哪些角色，不看金额、归属和时间。*ABAC*（基于属性的访问控制）把主体、资源、动作和环境的属性一起送进策略求值，回答“这一次、对这条数据、在这个条件下能不能做”。

*权限*统一表示为“资源 + 动作”的二元组，例如 `("refund", "approve")`。粒度太粗（`admin`）表达不了差异，按接口逐个授权又无法维护。

| 维度 | RBAC | ABAC |
| --- | --- | --- |
| 判定依据 | 主体持有的角色 | 四类属性的取值 |
| 表达“金额 5000 以内” | 只能拆角色 | 一条比较即可 |
| 审计可读性 | 好，“他为什么能”一眼可见 | 差，要记录命中策略与属性快照 |
| 典型失效 | *角色爆炸* | 属性缺失或被篡改，判定不可信 |

*角色爆炸*指为表达更细的条件不断新建角色，最终角色数超过用户数，没人说得清哪个角色该给谁。晴空商城首次评审已有 47 个角色，其中 12 个只差一个金额阈值。

其余术语：*租户*是共享同一套系统但数据互不可见的一组主体；*最小授权*指只持有必需权限并到期收回；*权限传递*是主动把部分权限临时交给他人，*权限提升*是拿到本不该有的权限，前者是设计，后者是事故；*策略决策点*（PDP）算结论，*策略执行点*（PEP）执行它。

| 角色 | `order:read` | `refund:create` | `refund:approve` | `refund:payout` | `shipment:update` |
| --- | --- | --- | --- | --- | --- |
| 店铺店员 | 本租户 | 本租户 | — | — | — |
| 店铺客服主管 | 本租户 | 本租户 | 本租户 ≤ 5000 | — | — |
| 平台客服 | 跨租户只读 | 代客提交 | — | — | — |
| 仓库操作员 | 发货相关 | — | — | — | 本仓库 |
| 财务 | 本租户 | — | — | 是 | — |
| 平台运营 | 跨租户只读 | — | — | — | — |

表里“≤ 5000”“本租户”已越出 RBAC 的边界。**矩阵负责“这类事”，属性约束负责“这一条”。**

## 工作原理

一次跨租户越权尝试从进来到被拒绝要过七步，顺序本身是设计：

1. **建立主体**：网关验签并检查有效期，从可信声明取出 `sub`、`tenant_id`、`roles`，三者都不接受请求体或查询串覆盖。
2. **固定租户上下文**：中间件把 `tenant_id` 放进只读上下文，业务代码没有改租户的入口。
3. **入口校验**：PEP 先看这个角色是否可能拥有该权限，缺则直接 `403`，不进业务逻辑。
4. **租户先于角色**：目标资源租户与主体租户不一致时，只有明确持有跨租户角色的主体继续。顺序颠倒会把“存在跨租户角色”当成“租户校验通过”。
5. **RBAC 求值**：把角色展开成权限集合，检查是否包含所需的“资源 + 动作”。
6. **ABAC 求值**：对金额上限、是否已出库、仓库是否确认逐条判定。
7. **数据层与出口兜底**：数据访问层强制追加租户条件，返回前按可见字段投影脱敏；判定结果、策略版本与属性快照写入审计。

第 4 步与第 7 步看似重复，其实是承认应用层会漏分支。**唯一可靠的做法是让“漏掉租户条件”在数据层变成查不到数据，而不是返回全部数据。**

## 架构与选型

| 场景 | 推荐模型 | 选它的理由 | 不适用或需注意 |
| --- | --- | --- | --- |
| 后台固定岗位（客服、财务、仓管） | 纯 RBAC | 岗位稳定，矩阵可评审、可培训 | 岗位内差异交给属性，别拆角色 |
| 退款审批带金额与状态条件 | RBAC + ABAC | 角色答“能不能审批”，属性答“这一笔” | 属性须来自可信来源 |
| 平台运营跨租户读数据 | RBAC + 显式租户作用域 | 跨租户是例外能力，须单独授权留痕 | 默认不给写，写操作双人复核 |
| 一次性排查需求 | 带到期时间的临时授权 | 自动失效，不依赖人工回收 | 必须记录申请理由与审批人 |
| 合规级细则（分级、地域、用途） | ABAC 为主 | 条件多且常变，硬编码必然爆炸 | 需要属性字典与策略回滚 |

判断顺序是：**先问“权限能不能枚举成有限角色”，再问“条件是否随资源属性变化”，最后问“是否需要跨租户”。**

边界：RBAC 表达不了“同一角色在不同数据上权限不同”，硬做必然角色爆炸；ABAC 不宜作为唯一防线，属性一旦可被调用方影响就形同虚设；两者都替代不了租户隔离，租户是数据边界，不是权限的一种。

## 最小示例

问题：实现一个判定函数，让上述规则生效，并验证四种拒绝原因都能触发。环境为 Python 3.9+ 标准库，不联网、不依赖数据库。

```python
from dataclasses import dataclass, field

# 权限 = (资源, 动作)。动作写到"审批/打款"这一级，才能与"提交申请"分开授权
PERMS = {
    "cs": {("order", "read"), ("refund", "create")},
    "cs_lead": {("order", "read"), ("refund", "create"), ("refund", "approve")},
    "warehouse": {("shipment", "read"), ("shipment", "update")},
    "finance": {("refund", "read"), ("refund", "payout")},
    # 平台角色故意不含写权限：跨租户读是例外能力，不能顺带得到写
    "platform_cs": {("order", "read"), ("refund", "create")},
    "platform_ops": {("order", "read"), ("refund", "read")},
}

APPROVE_LIMIT = 5000  # 业务上限只写一处，避免散落到每个接口各写一遍


@dataclass(frozen=True)
class Subject:
    user_id: str
    tenant: str          # 来自令牌，不接受请求参数覆盖
    roles: tuple


@dataclass(frozen=True)
class Resource:
    kind: str
    tenant: str          # 由服务端按主键查出，不取客户端传来的值
    attrs: dict = field(default_factory=dict)   # 金额、出库状态等属性快照


def decide(subject, action, resource):
    # 第 1 步：租户校验必须先做。若先查角色，跨租户角色会掩盖租户不匹配
    if resource.tenant != subject.tenant and "platform_ops" not in subject.roles:
        return "deny", "tenant_mismatch"

    # 第 2 步：RBAC。任一角色命中即可继续，未命中说明岗位本身不该做这个动作
    perms = set().union(*(PERMS.get(r, set()) for r in subject.roles))
    if (resource.kind, action) not in perms:
        return "deny", "role_missing"

    # 第 3 步：ABAC。只对审批动作求值，条件随资源属性变化
    if (resource.kind, action) == ("refund", "approve"):
        amount = resource.attrs.get("amount", 0)
        if amount > APPROVE_LIMIT:
            return "deny", "amount_exceeds_limit"
        # 已出库的退款必须由仓库确认，否则可能钱货两空
        if resource.attrs.get("shipped") and not resource.attrs.get("warehouse_confirmed"):
            return "deny", "warehouse_not_confirmed"

    return "allow", "ok"


def check(label, subject, action, resource):
    # 统一打印格式，便于把"规则"和"结果"逐行对照
    decision, reason = decide(subject, action, resource)
    print(f"{label}: {decision} {reason}")


clerk = Subject("cs-1024", "brand-a", ("cs",))
lead = Subject("lead-07", "brand-a", ("cs_lead",))
ops = Subject("ops-02", "platform", ("platform_ops",))

own_order = Resource("order", "brand-a")
other_order = Resource("order", "brand-b")
small_refund = Resource("refund", "brand-a", {"amount": 300, "shipped": False})
big_refund = Resource("refund", "brand-a", {"amount": 8800, "shipped": False})
shipped_refund = Resource("refund", "brand-a", {"amount": 460, "shipped": True})

check("店员读本店订单", clerk, "read", own_order)
check("店员读他店订单", clerk, "read", other_order)
check("店员审批退款", clerk, "approve", small_refund)
check("主管审批小额退款", lead, "approve", small_refund)
check("主管审批大额退款", lead, "approve", big_refund)
check("主管审批未确认出库退款", lead, "approve", shipped_refund)
check("平台运营跨租户读", ops, "read", other_order)
check("平台运营审批退款", ops, "approve", small_refund)
```

运行 `python3 policy_demo.py` 的预期输出：

```text
店员读本店订单: allow ok
店员读他店订单: deny tenant_mismatch
店员审批退款: deny role_missing
主管审批小额退款: allow ok
主管审批大额退款: deny amount_exceeds_limit
主管审批未确认出库退款: deny warehouse_not_confirmed
平台运营跨租户读: allow ok
平台运营审批退款: deny role_missing
```

两处设计值得记住：租户校验在最前，所以“店员读他店订单”返回 `tenant_mismatch` 而不是 `role_missing`；`platform_ops` 没有写动作，跨租户读不会顺带变成写。

## 动手实验

前置条件：已完成最小示例，本机有 Python 3.9+。无需网络与数据库，全部在单进程内完成。

### 任务一：把临时委托做成不扩权的传递

1. 新增 `Delegation`，字段为 `grantor`、`grantee`、`perms`、`expires_at`。
2. 在 `decide` 中解析：主体除自身角色外，还获得未过期且授予对象是自己的委托权限。
3. 强制校验委托权限是委托人自身权限的子集，否则创建时返回 `delegation_escalation`。
4. 用“主管把 `refund:approve` 委托给店员 24 小时”验证，再把 `expires_at` 改成过去时间，确认立刻失效。

### 任务二：证明新增租户不需要新增角色

1. 复制 `brand-a` 的三个主体，把 `tenant` 改为 `brand-c`，角色不动。
2. 让 `brand-c` 主管审批本租户退款，再审批 `brand-a` 的退款。
3. 统计 `PERMS` 的角色数量是否变化。

预期结果：本租户 `allow`，跨租户 `deny tenant_mismatch`，角色表一条未改。扩权委托在创建阶段返回 `delegation_escalation`；委托过期后变回 `role_missing`，不依赖定时清理。若为让第三十一家店铺跑通而必须新增角色，说明租户被建模成了角色。

验证方法：每个用例打印“判定结果 + 原因码 + 命中策略版本”；再确认审计里有 `subject.tenant` 与 `resource.tenant`，缺任一项都无法复盘跨租户访问。

清理方法：实验只在内存中进行，删除临时脚本即可；若曾把真实令牌或顾客数据写进日志，一并删除并轮换凭据。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 改 `order_id` 就能读到别家订单 | 只在应用层按租户过滤，数据层无强制 | 用 A 租户令牌直接请求 B 租户主键 | 数据层强制注入租户条件，加唯一索引校验 |
| 角色数量持续增长 | 用角色表达金额、状态这类资源属性 | 统计角色数与用户数，看差异是否只在阈值 | 属性条件移进策略，角色回到岗位语义 |
| 平台侧账号能改价、能退款 | 跨租户角色复用了后台角色的权限集合 | 打印跨租户角色展开后的权限集合 | 跨租户角色只给读，写操作双人复核 |
| 审计查不到谁批准了退款 | 只记录令牌主体，未记录判定依据 | 检查审计字段是否含原因码与策略版本 | 记录原因码、策略版本与属性快照 |
| 前端隐藏了按钮，接口仍可调用 | 把前端可见性当成权限控制 | 直接构造请求，绕过界面调用接口 | 前端隐藏只做体验，判定放服务端 |

## 安全与生产注意事项

**<u>把租户标识从请求参数或请求头里读出来，等于让调用方自己声明“我能看哪个租户的数据”。</u>** 这类实现平时看不出问题，直到有人改一个参数，三十家品牌商的订单与顾客信息被打包返回。缓解方式是租户标识只从已验签的令牌取，中间件设为只读，数据层无条件追加过滤，并对跨租户读取告警。

**<u>为赶需求临时发放“平台管理员”这类超级角色，会让最小授权事实上失效，而且通常再不会被回收。</u>** 后果不是“多了点权限”，而是单个账号被盗即全租户可写；审计里所有高危操作都“有权执行”，分不出正常与异常。缓解方式是把审批、打款、导出、改价拆成独立权限，临时授权带到期时间与理由，每月复核持有者。

**<u>只在网关或只在页面上做权限判断，会让任何直连服务的调用绕过全部检查。</u>** 网关只认路径与方法，表达不了“这条订单属于哪个租户”；隐藏按钮只是交互设计。缓解方式是每个服务自身持有判定逻辑，数据层兜底。

## 本课总结

- **RBAC 答“这个岗位能不能做这类事”，ABAC 答“这一次对这条数据能不能做”**，后者只能叠加。
- **角色爆炸的根因是用角色表达资源属性**；金额、状态、归属应进策略，而不是变成新角色。
- **租户是数据边界，不是权限的一种**：标识须来自可信来源，数据层强制生效，且租户判定先于角色判定。
- **权限传递必须不扩权且能自动失效**，否则“临时授权”会变成长期后门。

## 思考题

商城计划开放“经营分析”：品牌商可看本店近 90 天销售、退款率与顾客地域分布，并按门店、品类下钻。数据团队建议“给数仓宽表加一列 `tenant_id` 过滤，一次投入长期可用”。请分析这个建议在聚合结果、权限传递和验证证据上的漏洞，并给出替代设计。

参考思路：加一列过滤能挡明细越权，挡不住小样本聚合——下钻到单门店、单日时可能只剩一两名顾客，地域加金额足以反推个人。权限传递要看分析账号能否导出明细、分享到外部平台、离职后是否随 SSO 失效。替代设计是按租户做视图、设最小聚合粒度与抑制规则、导出单独授权留痕。证据要可执行：小样本租户下钻确认被抑制、A 租户凭据请求 B 租户维度确认拒绝、审计能否还原“谁基于哪条策略看了哪个租户”。

## 小测

1. “客服主管只能审批 5000 元以内的退款”，只用 RBAC 实现通常出现什么后果？  
   A. 无法实现　B. 角色数量随阈值组合增长　C. 必须放弃租户隔离　D. 审计日志失去意义
2. 为什么 `decide` 要先判租户再判角色？顺序反过来会看到什么现象？
3. “租户标识必须来自可信来源”指什么？举一个不可信来源并说明后果。
4. 权限传递必须满足哪两个条件，才不会变成权限提升？
5. 场景题：平台运营提出“请给 `platform_ops` 加上 `refund:approve`，发现异常退款直接处理，省得走工单”。你接受吗？

## 答案与解析

1. **B。** RBAC 只表达“角色是否拥有该权限”，每个金额档位都要新增角色，档位一多就角色爆炸。A 不成立，拆成 `cs_lead_small`、`cs_lead_large` 能实现，只是代价高；C、D 与阈值无关，租户隔离是数据边界，审计仍会记录角色。
2. 租户不匹配是更基础的事实：主体连这条数据都不该看见，讨论角色没有意义。顺序反过来时，跨租户角色会让判定继续往下走，可能误返 `allow`，也可能返回 `role_missing`，把越权误报成“权限配置不足”。
3. 指服务端签发、已验证完整性、调用方改不了的来源，例如验签后的令牌声明或会话；不可信来源包括 `?tenant_id=`、请求体字段、前端自设的请求头。后果是登录用户改一个值即可读其他租户数据，而正常请求全部成功，功能测试几乎不会暴露。
4. 一是**不扩权**：授予的权限必须是委托人自身权限的子集，并在创建委托时校验；二是**能失效**：委托带明确到期时间，判定以当前时间为准，不依赖清理。
5. 不接受。跨租户角色的价值是“看见全局”，附上写权限等于让分析岗持有对全部租户的审批能力：账号被盗或误操作波及所有品牌商，审计里却一切“有权执行”。替代做法是保持只读，把异常退款转工单给店铺主管；紧急需求走带到期时间的临时授权并单独告警。

### 动手实验参考

任务一的关键是把校验放在创建委托时：先算 `grantor_perms`，再判断 `perms <= grantor_perms`，否则返回 `delegation_escalation`；判定阶段只检查 `grantee == subject.user_id` 与 `expires_at > now`。任务二的关键是看角色数量有没有变：若为第三十一家店铺新增了角色，说明租户被建模成了角色。

## 延伸阅读与下一课

- [NIST RBAC 项目页](https://csrc.nist.gov/projects/role-based-access-control)，RBAC 参考模型与演进。
- [NIST SP 800-162：ABAC 指南](https://doi.org/10.6028/NIST.SP.800-162)，属性、策略与架构组件的定义来源。
- [OWASP 授权备忘录](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)，默认拒绝与服务端强制的清单。
- [OWASP Top 10：A01 失效的访问控制](https://owasp.org/Top10/A01_2021-Broken_Access_Control/)，越权访问的常见形态与影响。
- [PostgreSQL 行级安全策略](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)，把租户隔离下沉到数据层的实现。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[SSO、SAML 与企业身份接入](06-sso-saml-and-enterprise-identity.md)。
- 下一课：[Secret、证书与密钥管理](08-secrets-and-key-management.md)。
