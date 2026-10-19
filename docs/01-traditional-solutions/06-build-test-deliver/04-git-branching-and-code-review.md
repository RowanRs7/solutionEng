---
title: Git、版本与代码审查
slug: git-branching-and-code-review
module: traditional-solutions
stage: build-and-integrate
type: core
difficulty: beginner
duration: 45m
prerequisites:
  - exception-handling-and-structured-logging
outcomes:
  - 用一条提交列表推导出下一次发布的版本号，并说出触发 major、minor、patch 的是哪一条
  - 按 Conventional Commits 写一条提交信息，正确表达类型、范围和破坏性变更
  - 用审查清单对一段退款改动给出至少三条可执行的评审意见
last_reviewed: 2026-10-19
---

# Git、版本与代码审查

## 为什么需要学习

晴空商城的退款服务上线十一个月，`pyproject.toml` 里的版本号始终是 `1.0.0`。大促前夜客服工作台报错：它按 `amount` 读金额，服务端却已改成 `amount_cents`。值班的人问：生产上跑的是哪一版？字段谁改的？能不能回到昨天早上？

追溯下去，代码都没写错：三个人各维护一条活了两周的分支，合并时手工解了十七处冲突；金额判断直接推到主干，没人看过；发布是构建机现打的包，没打过标签。<u>当版本号是装饰、提交信息只写“update”、主干谁都能推时，出事以后就没有任何证据能告诉你该退到哪里。</u>

> **核心结论：** 版本号、提交记录和审查记录合起来，才构成一次改动可追溯、可回滚的证据链。

## 学习目标

完成本课后，你能够：

- 用一条提交列表推导出下一次发布的版本号，并指出触发 major、minor、patch 的是哪一条。
- 按 Conventional Commits 写一条提交信息，正确表达类型、范围和破坏性变更。
- 为晴空商城的具体场景选择分支模型，并说出它的代价。
- 用审查清单对一段退款改动给出至少三条可执行的评审意见。

## 前置知识

- 回看上一课：[异常处理与结构化日志](03-exception-handling-and-structured-logging.md)。
- 会用 `git add`、`git commit`、`git push`、`git switch -c`，知道工作区、暂存区与提交的区别。
- 能读懂一段 FastAPI 路由与 JSON 响应。
- 知道预发布环境与生产环境是两套数据和配置。

## 业务场景

“晴空商城”的退款服务有三个调用方：客服工作台按 `amount` 渲染退款单，仓库夜间导出按 `amount_cents` 汇总，财务对账按 `X-Api-Version` 请求头选择解析规则。双十一前，三件事要在同一个发布窗口内改完：

- 审核阈值从固定 500 元改为按客户等级分档：普通 500 元、VIP 2000 元。
- 支付供应商要求回调带回新的签名版本号，旧签名下个账期停用。
- 客服工作台希望退款单返回“本次适用的阈值”，好解释为什么转人工。

约束：导出脚本由另一团队维护，升级不由商城控制；工作台是桌面客户端，发布周期以月计；财务对账不容忍字段含义变化。于是“何时可以破坏兼容、怎么让下游知道”成了本单元的核心问题。

## 核心概念

*分支模型*（branching model）约定代码在哪些线上并行演进、何时合回主干、何时打发布标签。它不是 Git 的功能，而是团队纪律。

*主干开发*（trunk-based development）指所有人每天把改动合回一条长期主干，分支只活几小时到一两天；*短生命周期分支*是配套做法，分支越短冲突越少，评审范围也读得完。

*语义化版本*（Semantic Versioning，SemVer）写成 `主版本.次版本.修订号`：主版本变表示接口不兼容，次版本变表示新增兼容功能，修订号变表示兼容修复；*预发布版本*加连字符标记，如 `2.0.0-rc.1`，优先级低于同号正式版。

*提交规范*（Conventional Commits）把主题写成 `类型(范围): 主题`，让机器读得出改动性质；类型后加 `!` 或正文写 `BREAKING CHANGE:` 表示*破坏性变更*，即调用方不改代码就无法继续工作。*标签*是给提交起的固定名字，发布时打 `v1.5.0`；*受保护分支*禁止直接推送，必须过检查与审查；*代码审查*是合并前由他人检查正确性与风险，不看风格偏好。

| 概念 | 本课程中的含义 | 晴空商城示例 |
| --- | --- | --- |
| 分支模型 | 并行开发与合并时机的约定 | 阈值改动走短分支 |
| 语义化版本 | 用版本号承诺兼容性 | `amount` 改名 → `2.0.0` |
| 破坏性变更 | 下游必须改代码的变化 | 删除 `amount`，只留 `amount_cents` |
| 标签 | 发布产物的唯一身份 | `v1.5.0` 指向构建该包的提交 |

审查需要清单，否则每人只看自己在意的那段：

| 维度 | 要问的问题 | 通过标准 |
| --- | --- | --- |
| 契约 | 字段增删改有没有通知下游、升主版本 | 删除或改义即 `!`，并列出受影响方 |
| 正确性 | 边界值、空值、失败路径走到没有 | 有覆盖 199/200 元边界的测试 |
| 安全 | 有没有拼 SQL、打印凭据、放宽权限 | 参数化查询，日志无密钥与手机号 |
| 可运维 | 出错时能否从日志和指标定位 | 新增失败分支带错误码和上下文 |
| 范围 | 是否夹带了无关重构 | 一个 PR 只解决一个问题 |

## 工作原理

一次改动从分支到可回滚的发布，走的是这条链：

1. **拉短分支**：从最新主干切 `feat/REF-231-review-threshold`，分支名带工单号，半年后也能追到需求。
2. **小步提交**：每完成一个可解释的单元提交一次，主题写清类型与范围。
3. **推送并开 PR**：描述写清“改了什么、为什么、怎么验证、影响谁”；超出几百行就说明它其实是两件事。
4. **过 CI 门禁**：单元测试、静态检查、密钥扫描、契约测试依次跑。**门禁不过就没有人工审查这回事**，否则审查者会把时间花在机器能发现的问题上。
5. **人工审查**：按核心概念里的清单看 diff、看测试、看失败路径，留下可执行的意见，结论只有“可以合并”和“需要修改”。
6. **合并回主干**：用 squash 或 rebase 保持线性，一条 PR 对应一个提交，回滚时才能整条撤销。
7. **判定版本档位**：比较上一个标签以来的提交并取最高档——有 `!` 是主版本，有 `feat` 是次版本，只有 `fix`、`perf` 是修订号。
8. **打标签并发布同一产物**：先打 `v1.5.0`，再用这个标签构建部署；标签与线上产物不一致，回滚就没有坐标。
9. **回滚**：把流量切回上一个标签的产物，而不是在主干上反向提交一个“撤销”，那会引入新的未审查改动。

第 7、8 步最容易断：版本号不是发布时手填的数字，而是第 2 步提交的函数；标签也不是发布后的记录，而是构建的输入。**把两者当成事后补的文档，回滚就只能靠记忆。**

版本比较也有坑：`1.9.3` 与 `1.10.0` 按字符串排会把后者排到前面，正确做法是逐段按数值比较，预发布版排在同号正式版之前。

## 架构与选型

分支模型取决于“同时有几个版本要活着”，而不是团队人数：

| 方案 | 适用 | 不适用或代价 | 判断依据 |
| --- | --- | --- | --- |
| 主干开发 + 短分支 | 持续交付、测试可信 | 测试不可信时主干随时是坏的 | 能否在 10 分钟内完整验证 |
| GitHub Flow | 单一线上版本、以天发布 | 多历史版本并行时无处安放 | 是否只需一条发布线 |
| 发布分支 | 大促冻结、要维护旧版本 | 修复要在主干与发布分支各合一次 | 是否有“已上线不能带新功能”的窗口 |
| Git Flow | 版本周期明确、多客户版本并行 | 分支多、合并路径长，慢交付被流程拖住 | 是否有两个以上版本要修缺陷 |

晴空商城的选择：日常走主干开发加短分支；大促前两周切 `release/2026-11` 冻结功能，只允许经审查的 `fix` 进入；紧急缺陷从标签切 `hotfix` 分支，修完同时合回主干与发布分支。

版本策略则由兼容负担决定：对外接口的版本是契约承诺，删字段前先发 `2.0.0` 并双写一个周期；内部服务的镜像标签用 `v1.5.0`，禁止 `latest`；客户端 SDK 的升级不受控，只能只增不删，废弃字段保留两个次版本。

<u>0.x 阶段的规则要团队内部先统一</u>：有的团队把破坏性变更记为次版本，有的直接升 `1.0.0`。两种都行，混用会让同一批提交算出两个版本号。

## 最小示例

问题：把“分支名是否合规、提交是否规范、下次版本号是多少”写成可离线运行的检查，验证版本号确实是提交信息的函数。

环境：Python 3.9 及以上，只用标准库，不需要 Git 或任何包。

```python
"""release_check.py：只用标准库检查分支名、提交规范与下一次版本号。"""
import re                       # 只靠正则解析，不引入 git 客户端
from dataclasses import dataclass

# 分支名要能追到工单：<类型>/<工单号>-<短描述>，短描述只允许小写与连字符
BRANCH_RE = re.compile(r"^(feat|fix|docs|refactor|hotfix)/([A-Z]+-\d+)-[a-z0-9]+(?:-[a-z0-9]+)*$")

# Conventional Commits：<类型>(<范围>)?(!)?: <主题>，`!` 表示破坏性变更
COMMIT_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?: (?P<subject>.+)$"
)


def check_branch(name: str) -> str:
    """分支名合法与否直接决定“这行改动是谁、为什么改的”。"""
    match = BRANCH_RE.match(name)
    if match:
        return f"分支 {name} -> 合法（类型 {match.group(1)}，工单 {match.group(2)}）"
    return f"分支 {name} -> 非法：缺少工单号与短描述"


@dataclass(frozen=True)
class Commit:
    """一条已解析的提交；frozen 保证下游只读，不会被改得面目全非。"""
    type: str
    scope: str
    subject: str
    breaking: bool


def parse_commit(line: str) -> Commit:
    """格式不合格就报错，而不是猜。静默容忍脏提交会让变更日志失去意义。"""
    match = COMMIT_RE.match(line)
    if not match:
        raise ValueError(f"不符合 Conventional Commits：{line}")
    return Commit(
        type=match["type"],
        scope=match["scope"] or "-",   # 无范围时用连字符占位，输出对齐
        subject=match["subject"],
        breaking=bool(match["breaking"]),
    )


# 只有这三类会改变版本号；chore、docs、test 之类不进“新功能”区
BUMPS = {"feat": "minor", "fix": "patch", "perf": "patch"}
RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}


def next_version(current: str, commits: list) -> tuple:
    """取所有提交里最高的那一档：有破坏性变更就是 major，不会只升 patch。"""
    level = "none"
    for commit in commits:
        bump = "major" if commit.breaking else BUMPS.get(commit.type, "none")
        if RANK[bump] > RANK[level]:
            level = bump

    major, minor, patch = (int(part) for part in current.split("."))
    if level == "major":
        major, minor, patch = major + 1, 0, 0      # 破坏性变更把后面两位清零
    elif level == "minor":
        minor, patch = minor + 1, 0                # 新功能把 patch 清零
    elif level == "patch":
        patch += 1
    return f"{major}.{minor}.{patch}", level


def render_changelog(commits: list) -> list:
    """按“破坏性变更 / 新功能 / 修复”分组，读者先看会打断兼容的那部分。"""
    groups = [("破坏性变更", [c for c in commits if c.breaking]),
              ("新功能", [c for c in commits if c.type == "feat" and not c.breaking]),
              ("修复", [c for c in commits if c.type in ("fix", "perf") and not c.breaking])]
    lines = []
    for title, items in groups:
        if items:
            lines.append(f"### {title}")
            lines.extend(f"- {c.scope}: {c.subject}" for c in items)
    return lines


def version_key(tag: str) -> tuple:
    """把 tag 变成可比较的元组；直接按字符串排序会把 1.10.0 排到 1.9.3 前面。"""
    core = tag.split("+")[0]                       # 丢弃构建元数据，它不参与优先级
    main, _, pre = core.partition("-")             # 预发布段单独处理
    major, minor, patch = (int(part) for part in main.split("."))
    return (major, minor, patch, 0 if pre else 1)  # 有预发布标记的排在正式版之前


if __name__ == "__main__":
    for branch in ("feat/REF-231-review-threshold", "hotfix"):
        print(check_branch(branch))

    raw = [
        "feat(refund): 支持按客户等级设置审核阈值",
        "fix(refund): 修正 199 元边界判断",
        "feat(api)!: 移除退款接口的 amount 字段",
    ]
    commits = [parse_commit(line) for line in raw]
    print("\n提交:")
    print("\n".join(f"  {line}" for line in raw))

    version, level = next_version("1.4.2", commits)
    print(f"\n版本: 1.4.2 -> {version}（触发档位: {level}）")
    print("变更日志:")
    print("\n".join(f"  {line}" for line in render_changelog(commits)))

    tags = ["1.9.3", "1.10.0", "1.2.0"]
    print("\ntag 排序:", " < ".join(sorted(tags, key=version_key)))
```

运行与真实输出（Python 3.14.7 实跑）：

```bash
python3 release_check.py
```

```text
分支 feat/REF-231-review-threshold -> 合法（类型 feat，工单 REF-231）
分支 hotfix -> 非法：缺少工单号与短描述

提交:
  feat(refund): 支持按客户等级设置审核阈值
  fix(refund): 修正 199 元边界判断
  feat(api)!: 移除退款接口的 amount 字段

版本: 1.4.2 -> 2.0.0（触发档位: major）
变更日志:
  ### 破坏性变更
  - api: 移除退款接口的 amount 字段
  ### 新功能
  - refund: 支持按客户等级设置审核阈值
  ### 修复
  - refund: 修正 199 元边界判断

tag 排序: 1.2.0 < 1.9.3 < 1.10.0
```

整体流程：`parse_commit` 把文本变成不可变记录，`next_version` 遍历一次取最高档再进位，`render_changelog` 按兼容性风险分组，`version_key` 给出可比较的元组。关键选择有两处：**取最高档位而不是累加**，因为只要有一条破坏性变更，整个发布就是主版本；**预发布版排在正式版之前**，`2.0.0-rc.1` 才不会被判为比 `2.0.0` 新。

## 动手实验

### 任务：判定版本档位，并按清单审一段 diff

前置条件：Python 3.9 及以上；工作目录 `/tmp/git_lab`；只用标准库，不需要网络、数据库或 Git 仓库。

1. 创建 `/tmp/git_lab`，把最小示例保存为 `release_check.py`，运行并确认版号为 `2.0.0`。
2. 删掉 `raw` 里带 `!` 的提交再跑，预期 `1.5.0`（`minor`）。
3. 再删掉 `feat(refund)` 那条、只留 `fix`，预期 `1.4.3`（`patch`）。
4. 把 `check_branch` 的循环改成 `("feat/REF-231", "fix/ref-9-x")`，两行都应报非法：前者缺短描述，后者工单号是小写。
5. 按清单读下面的待审 diff，写出至少三条“问题 + 后果 + 建议”。

```diff
--- a/app/service/refund.py
+++ b/app/service/refund.py
@@ -18,8 +18,11 @@ class RefundService:
     def decide(self, refund_id, customer_level):
         row = self._repo.find(refund_id)
-        auto = row["amount_cents"] <= 50000
-        return {"id": refund_id,
-                "next_action": "auto_approve" if auto else "manual_review"}
+        limit = 50000 if customer_level == "normal" else 200000
+        auto = row["amount_cents"] <= limit
+        self._repo.audit(f"refund {refund_id} checked by {self._settings.env}")
+        return {"id": refund_id,
+                "next_action": "auto_approve" if auto else "manual_review",
+                "limit_cents": limit}
```

预期结果：步骤 2 至 4 的输出与描述一致；步骤 5 至少写出三条意见。

验证方法：比对终端里的版本号与触发档位；再用清单的五个维度逐条对照，说清每条意见落在哪一栏。

清理方法：`rm -rf /tmp/git_lab`。若建过本地分支做对照，用 `git switch main` 切回主干后删除。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 线上报字段缺失，代码里字段还在 | 发布产物不是标签对应的版本 | 比对线上镜像标签与 `git rev-list -n1 <tag>` | 用标签构建部署，禁止 `latest` |
| 一次小修复被算成主版本 | 提交里混进了带 `!` 的描述 | 看触发档位来自哪条提交 | 拆开提交，破坏性变更单独发布 |
| 合并冲突多到没人敢合 | 分支活了两周，主干改了同一片代码 | 看分支起点到主干的提交数 | 缩短分支寿命，未完成代码用开关 |
| 回滚后问题仍在 | 靠反向提交回滚，引入了未审查逻辑 | 检查回滚标签是否真指向旧产物 | 产物不可变，回滚即切回旧标签 |

## 安全与生产注意事项

**<u>把密钥或连接串提交进仓库、再用 force-push 覆盖历史，并不等于删除。</u>** 对象仍在 reflog、其他克隆、CI 缓存和平台的不可达对象里。缓解：提交前密钥扫描；推送过就立即轮换凭据，再清理历史并评估访问记录。

**<u>允许直接推送主干、缺少必须审查与门禁，一次误提交就能把未经复核的退款阈值改上生产。</u>** 金额判断改错可直接计价，事后还分不清“故意绕过”和“没人看见”。缓解：主干设为受保护分支，要求非作者审查、门禁必过、禁止强推。

**<u>发布标签被移动或重复使用，会让回滚退到一段从未测试过的代码。</u>** 缓解：标签只创建不修改，重建产物用新版本号；标签保护禁止删除改写，流水线记录“标签 → 产物摘要 → 环境”。

## 本课总结

- 分支模型把并行改动限制在可合并、可审查的规模内，短分支比复杂流程更有效。
- 语义化版本是承诺：主版本改兼容性，次版本加功能，修订号修缺陷；**版本号应由提交推导，而不是发布时手填**。
- 审查审契约、正确性、安全、可运维和范围，不审个人风格；机器能查的不要交给人。
- 发布产物必须与标签一一对应且不可变，否则回滚只是又一次赌博。

## 思考题

晴空商城只有一条线上产品线，但双十一前有两周冻结窗口，还要维护一个已交付大客户的旧版本；团队 12 人，测试覆盖中等。你选主干开发加发布分支，还是完整 Git Flow？请写清选择、大促期间的操作，以及如何应对“覆盖中等”。

参考思路：不必二选一到底。日常走主干开发加短分支，冻结期切发布分支只收经审查的 `fix`，同时为大客户旧版本留维护分支，修复要双向合回。代价是每次修复合两次、版本号分别打，因此需要“哪些修复必须回合并”的标准。“覆盖中等”意味着主干随时可能被合坏，应先把门禁补到能拦住退款关键规则，再谈缩短分支寿命。

## 小测

1. 提交 `refactor(refund): 抽出发送通知的客户端` 会把版本从 `1.4.2` 推到多少？
2. 下面哪种情况必须升主版本？  
   A. 给响应新增一个可选字段　B. 修复金额边界判断　C. 把 `amount` 改名为 `amount_cents`　D. 提高日志级别
3. 为什么发布要用标签构建，而不是在构建机上直接打包当前目录？
4. 代码审查中，审查者发现变量名不符合个人偏好，应不应该作为阻塞意见？
5. 场景题：同事把“阈值从 500 元改成 300 元”和“重构退款状态机”放进同一个 PR，说“反正是同一片代码”。作为审查者你怎么处理？

## 答案与解析

1. **仍是 `1.4.2`。** `refactor` 不改变对外行为，不触发版本档位。若算成次版本，版本号会随内部整理跳变，下游无法据此判断要不要行动。
2. **C。** 改名让依赖旧字段的工作台和导出直接失效。A 是兼容新增，对应次版本；B 是缺陷修复，对应修订号；D 是运行期配置，与接口契约无关。
3. 标签把线上产物固定到唯一一个提交上。直接打包当前目录，产物取决于那台机器的状态，可能与任何提交都对不上，回滚时无从确认旧包是哪份代码。
4. 不应该。审查目标是正确性与风险，命名不引起误解就不该阻塞合并。可作为建议提出，或交给格式化工具；把它当阻塞项会让审查退化成风格争论。
5. 先要求拆分。混在一起时，回滚会把重构一起撤掉，破坏性变更也无法单独标版本；审查者还要同时判断业务规则与结构改动，容易漏掉边界。可建议重构另开 PR，本 PR 只留阈值改动，并补 299/300 元边界测试。

### 动手实验参考

步骤 2 得到 `1.5.0`（`minor`），步骤 3 得到 `1.4.3`（`patch`），步骤 4 两行都报非法。步骤 5 的合理意见至少包括：

- 阈值 `50000`/`200000` 硬编码在方法里，大促调价要改代码并重新发布，应移到配置或策略对象。
- 响应新增 `limit_cents`，但 PR 没标为契约变更、也没通知按严格 schema 校验的客户端，是兼容风险。
- 审计日志拼了 `self._settings.env` 却没有操作人，事后答不出“谁批准的”，环境名还会混淆测试与生产日志。
- 没为 VIP 分支和 199/200 元边界补测试，`customer_level` 传入未知值时默认走 2000 元额度，这是安全侧问题。

## 延伸阅读与下一课

- 语义化版本 2.0.0 中文版：三条规则与预发布优先级，<https://semver.org/lang/zh-CN/>。
- Conventional Commits 1.0.0 中文版：类型、范围与破坏性变更，<https://www.conventionalcommits.org/zh-hans/v1.0.0/>。
- Google 工程实践《Code Review Developer Guide》：审什么、不审什么，<https://google.github.io/eng-practices/review/>。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[异常处理与结构化日志](03-exception-handling-and-structured-logging.md)。
- 下一课：[单元、集成、契约、端到端与验收测试](05-test-levels-and-acceptance.md)。
