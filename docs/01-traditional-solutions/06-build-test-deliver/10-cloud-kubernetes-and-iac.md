---
title: 云计算、Kubernetes 与 IaC
slug: cloud-kubernetes-and-iac
module: traditional-solutions
stage: deploy-and-deliver
type: core
difficulty: intermediate
duration: 55m
prerequisites:
  - cicd-migrations-canary-and-rollback
outcomes:
  - 区分 IaaS、PaaS、SaaS、FaaS，并把晴空商城的各层组件归入合适的服务模型
  - 说明 Pod、Deployment、Service、Ingress 与 ConfigMap 的职责边界，判断一条变更能否原地更新
  - 用期望状态与实际状态的差异生成变更计划，并为一次生产变更选择控制台、脚本或 IaC 并说明理由
last_reviewed: 2026-10-19
---

# 云计算、Kubernetes 与 IaC

## 为什么需要学习

618 前一周，退款 worker 扛不住积压，运维登录控制台把三台机器改成十二台，又手工加安全组规则、往负载均衡挂了一台后端。大促过了，却没人说得清生产改过什么：日志只有一串 `ModifyInstancesAttribute`，也没人记得预发环境怎么建的。两周后有人清理“闲置资源”，顺手删掉了预发整套环境。

**<u>事故不是因为不会用云，而是基础设施状态只存在于某个人记忆里。</u>**

> **核心结论：** 基础设施的难题不是“能不能建起来”，而是**能不能说清现在是什么状态，并且可重复地回到那个状态**。

## 学习目标

完成本课后，你能够：

- 区分 IaaS、PaaS、SaaS、FaaS，把退款服务、数据库和工单系统归入合适模型。
- 说明 Pod、Deployment、Service 与 Ingress 的职责边界，判断一条变更会原地更新还是需要重建。
- 用“期望状态 vs 实际状态”的差异生成变更计划，说清 `plan`、`diff` 与 `apply` 的顺序关系。
- 为一次生产变更在控制台、脚本与 IaC 之间做出选择，并写出漂移检测与资源回收的做法。

## 前置知识

- 回看上一课：[CI/CD、变更、灰度与回滚](09-cicd-migrations-canary-and-rollback.md)。
- 能读懂 Dockerfile，知道 tag 会被覆盖、digest 指向唯一内容。
- 知道健康检查、滚动更新、灰度与回滚各自解决什么问题。
- 会写 Python 3，能读懂字典比较与退出码。

## 业务场景

本单元跟进退款服务 v2.4 的运行底座：新增重试 worker，大促从 3 个副本扩到 12 个；回调地址换成新域名并启用 HTTPS；生产分布在三个可用区，单区故障不能中断受理。审计要求回答“谁在何时改了什么”；运维两人、开发八人，不能给开发生产控制台权限，但要能自行验证配置。

关键约束：**预发与生产的差异必须小到一句话能描述，且这句话本身被版本管理。**

## 核心概念

*云计算服务模型*按“谁负责哪一层”划分责任。*IaaS* 只交付计算、存储与网络；*PaaS* 再托管运行时与扩缩容；*SaaS* 交付可直接使用的软件；*FaaS* 以函数为部署单位、按调用计费。

| 服务模型 | 你负责 | 厂商负责 | 晴空商城例子 | 主要代价 |
| --- | --- | --- | --- | --- |
| *IaaS* | 补丁、运行时、应用、数据 | 机房、网络、虚拟化 | 自建 K8s 节点池 | 自由度高，运维面大 |
| *PaaS* | 应用代码与配置 | 运行时、备份、扩缩容 | 托管 PostgreSQL | 受平台能力边界约束 |
| *FaaS* | 函数代码与触发规则 | 实例、伸缩、闲置回收 | 商品图转码 | 冷启动、执行时长上限 |
| *SaaS* | 账号与数据使用权 | 全部 | 客服工单系统 | 数据与集成深度受限 |

*Kubernetes* 是容器编排系统：把“要几个什么镜像的副本”这类*期望状态*写进对象，由控制循环持续拉回。这个“比对—修正”的循环叫*调和（reconcile）*，执行它的是*控制平面*，跑容器的机器是*工作节点*。

| 对象 | 负责什么 | 明确不负责 | 常见误用 |
| --- | --- | --- | --- |
| *Pod* | 最小调度单位，共享网络的容器组 | 自我修复、扩缩容 | 直接提交 Pod 清单上线 |
| *Deployment* | 副本数、滚动更新、版本历史 | 流量接入、持久化数据 | 改 `selector` 后望其原地生效 |
| *Service* | 给一组 Pod 稳定地址与四层负载均衡 | 域名、证书、七层路由 | 把 Service 当入口网关 |
| *Ingress* | 七层路由与 TLS 终止 | 选择后端、健康检查 | 拿它做四层转发 |
| *ConfigMap* / *Secret* | 注入配置与敏感值 | 自动重启、默认加密 | 密钥写进 ConfigMap |

*基础设施即代码（IaC）*把基础设施写成可评审、可版本管理的声明式文件，由工具执行并记账。*不可变基础设施*指运行实例永不就地修补：要变更就替换，而不是登录进去改文件。*漂移*是实际状态偏离期望状态，多因手工改控制台、脚本漏跑或资源被绕过删除。*状态文件*是记录“上次建了什么”的账本，`plan` 靠它对上账。*GitOps* 则让集群内控制器持续从 Git 拉取对账。

<u>“声明式”不等于“自动正确”</u>：它只保证写下的东西被反复对齐。

## 工作原理

从改动到生效，数据流按此顺序推进：

1. **写期望状态**：改 `deploy/refund-api.yaml` 的镜像版本，走合并请求评审。
2. **构建不可变产物**：流水线产出镜像并以 digest 固定引用。**清单里写 digest，不写可被覆盖的 tag。**
3. **生成计划**：`plan` 把声明、状态文件与真实 API 三方比对，输出“改镜像、加副本”，不可变字段标为“需重建”。这一步**不改任何东西**。
4. **执行**：人评审计划后 `apply` 写入期望状态；API Server 校验通过后存入 etcd，事件被控制器看到。
5. **调和**：Deployment 控制器发现现存 Pod 还是旧镜像，新建 ReplicaSet，在 `maxSurge`/`maxUnavailable` 约束下逐步替换。
6. **调度与启动**：调度器选节点，kubelet 拉镜像、起容器、跑就绪探针。**探针不通过不进后端。**
7. **接入流量**：Endpoints 更新后 Service 转发请求，Ingress 按域名接入并终止 TLS。
8. **持续对账**：HPA 按指标调副本数。<u>漂移也在这里产生：HPA 改了副本数，Git 里还写着 3。</u>

两条反向路径要记牢：**域名 → Ingress → Service → 就绪的 Pod**；**Git → 流水线 → API Server → etcd → 控制器 → Pod**。

## 架构与选型

| 场景 | 推荐做法 | 理由 | 代价 |
| --- | --- | --- | --- |
| 无状态、需按小时扩缩的服务 | 托管 K8s + Deployment + HPA | 副本与滚动更新是内建能力 | 需要集群运维能力 |
| 单个交付项目、一台机器 | 托管 PaaS 或 Compose + 脚本 | 不值得引入控制平面 | 扩缩与多可用区能力有限 |
| 关系型数据库、支付流水 | 厂商托管数据库，不自建 StatefulSet | 备份、主备切换、补丁归厂商 | 成本高，部分参数不可调 |
| 低频突发的短任务 | FaaS | 零闲置成本 | 冷启动、超时上限、调试困难 |
| 需要审计“谁改了什么” | IaC + 合并请求评审 | 变更即 diff，评审记录即审计线索 | 学习曲线，状态文件需治理 |

选型依据可归为三问：**变更频率多高、出错后爆炸半径多大、团队里有多少人读得懂定义**。前两问决定要不要 IaC，第三问决定抽象层次——两人运维团队自建控制平面，往往比用托管服务更易出事故。

不适用也要说清：强依赖本机磁盘的服务不能无脑塞进 Deployment；一年改两次的单机项目上 IaC 收益低于成本；而**没有人评审的 IaC 流水线，等于把手工误操作自动化了**。

## 最小示例

问题是：怎样在上生产前看清“这次改动会做什么”。下面用 Python 3 标准库实现一个极简 `plan`，输入期望与实际两份字典，输出变更清单并区分“原地更新”与“必须重建”。环境 Python 3.8 以上、仅标准库；输出为逐条变更与退出码。

```python
#!/usr/bin/env python3
"""plan_drift.py：比较期望状态与实际状态，输出可评审的计划，不做任何修改。"""

# 不可变字段：改这些不能打补丁，只能删掉重建。
# Deployment 的 selector、Service 的 clusterIP 都是真实例子。
IMMUTABLE_FIELDS = {"selector", "cluster_ip"}

# 期望状态来自 Git 里的清单。
DESIRED = {
    "name": "refund-api",
    "replicas": 3,
    "image": "registry.sky.shop/refund-api:2.4.0",
    "selector": "app=refund-api-v2",
}

# 实际状态来自集群 API，可能已被手工改过。
ACTUAL = {
    "name": "refund-api",
    "replicas": 2,
    "image": "registry.sky.shop/refund-api:2.3.1",
    "selector": "app=refund-api",
    "owner": "ops-li",  # 手工加的标签，Git 里没有，属于漂移
}


def plan(desired, actual):
    """返回 (动作列表, 是否需要重建)。只描述差异，绝不执行更改。"""
    actions = []
    replace_needed = False

    # 只遍历期望：不同即修改，相同则沉默，避免噪声淹没评审者。
    for key, want in desired.items():
        have = actual.get(key)
        if have == want:
            continue
        if key in IMMUTABLE_FIELDS:
            replace_needed = True
            actions.append(f"~ {key}: {have!r} -> {want!r}（不可变字段，只能删除重建）")
        else:
            actions.append(f"~ {key}: {have!r} -> {want!r}")

    # 反向遍历：多出来的字段是手工改动，必须显式回收。
    for key in sorted(set(actual) - set(desired)):
        actions.append(f"- {key}: {actual[key]!r}（不在期望状态中，回收）")

    return actions, replace_needed


def main():
    actions, replace_needed = plan(DESIRED, ACTUAL)
    if not actions:
        print("无变更：实际状态与期望状态一致")
        return 0  # 退出码 0 供流水线判断"无需审批"
    title = "变更计划（含重建）" if replace_needed else "变更计划（可原地更新）"
    print(f"{title}：{len(actions)} 项")
    for action in actions:
        print(action)
    # 退出码区分风险：2 需人工确认重建窗口
    return 2 if replace_needed else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

运行与预期输出：

```console
$ python3 plan_drift.py
变更计划（含重建）：4 项
~ replicas: 2 -> 3
~ image: 'registry.sky.shop/refund-api:2.3.1' -> 'registry.sky.shop/refund-api:2.4.0'
~ selector: 'app=refund-api' -> 'app=refund-api-v2'（不可变字段，只能删除重建）
- owner: 'ops-li'（不在期望状态中，回收）
$ echo $?
2
```

流程是：读两份状态 → 逐字段比对 → 命中不可变字段升级为“重建” → 反向找回漂移 → 输出计划并用退出码表达风险。三个设计选择值得注意：**先出计划再执行**，让评审发生在破坏之前；**不可变字段单独标记**，因为“改标签”和“改选择器”不是一回事；**漂移必须显式列出**，`owner` 那行就是手工改动的证据。

把 `selector` 改成与 `ACTUAL` 相同的值再跑，退出码变成 1——这就是 `plan` 与 `apply` 之间那个审批点的理由。

## 动手实验

### 前置条件

Python 3.8 以上，无需网络、集群或云账号，全部操作在一个临时目录完成。

### 步骤

1. 建目录 `~/k8s-lab`，把上面的脚本保存为 `plan_drift.py`。
2. 直接运行，观察退出码 2 与“含重建”字样。
3. 把 `DESIRED["selector"]` 改成 `"app=refund-api"` 再跑，观察退出码变为 1。
4. 把 `ACTUAL` 的 `replicas` 改成 3、`image` 改成 `2.4.0` 再跑，观察是否只剩漂移回收一条。
5. 临时删掉 `DESIRED` 的 `selector` 键，看它是否出现在“回收”列表里，并思考真实集群里删它会怎样。

### 预期结果

第 2 步 4 项变更、退出码 2；第 3 步仍 4 项但标题为“可原地更新”、退出码 1；第 4 步只剩 `- owner`；第 5 步 `selector` 被当作漂移回收。

### 验证方法

- 用 `echo $?` 检查退出码，流水线也只认退出码。
- 对 `plan` 每一项回答“原地更新还是重建、依据哪个字段”，答不出的项说明清单写得不够具体。
- 有集群时执行 `kubectl apply --dry-run=server -f deploy/refund-api.yaml`，服务端会直接拒绝缺失 `selector` 的清单。**<u>`--dry-run=server` 能在落地前暴露不可变字段与准入校验问题。</u>**

### 清理方法

`rm -r ~/k8s-lab`。执行前先 `ls ~/k8s-lab` 确认内容就是本次实验产物。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 用 `latest` 镜像，回滚后行为仍不对 | tag 被重推覆盖，拉到的不是旧内容 | 比对 Pod 的 `imageID` digest | 用 digest 部署，tag 只作标注 |
| 每次 `apply` 都提示改副本数 | HPA 在调副本，Git 里也写死了 `replicas` | `kubectl get hpa` 与清单对照 | 副本数只由 HPA 管，清单移除该字段 |
| `apply` 报 `field is immutable` | 改了 `selector`、`clusterIP` 等不可变字段 | 读报错中的字段名，或先用 `--dry-run=server` | 重建资源（新名字加切流量）或回退该字段 |
| 改了 ConfigMap，Pod 里值没变 | 环境变量在启动时注入 | `kubectl exec` 读同名变量 | 用 checksum 注解触发滚动，或挂载为文件 |

## 安全与生产注意事项

**<u>把 Secret 明文提交进 Git 或写进 ConfigMap，等于把生产凭据永久写进版本历史。</u>** 删文件也没用，历史记录与镜像层里仍留着；K8s 的 Secret 默认在 etcd 中不加密。缓解方式：凭据只通过外部密钥管理注入，仓库只放引用；开启 etcd 静态加密与最小 RBAC；提交过的凭据视为已泄露并立即轮换。

**<u>一次错误的 `apply` 或 `delete` 可以同时抹掉生产数据库和它的备份，基础设施没有回收站。</u>** 声明式工具忠实执行意图：清单里少写一个资源，工具就认为它该删除；改掉不可变字段，工具就删除重建。缓解方式：对数据库、存储桶、DNS 设删除保护，变更先看 `plan` 并由非提交者批准，另留一份不在同一权限域的备份。

**<u>集群管理员权限等价于生产数据权限</u>**：能创建 Pod 的人就能挂载任意 Secret。因此生产集群不对开发者开放写权限。

## 本课总结

- 云服务模型的差别是**责任分界线**：选 IaaS 就接过补丁与运行时，选 PaaS 换来能力上限与版本约束。
- Kubernetes 的核心是**期望状态 + 持续调和**；Deployment 管副本与滚动更新、Service 管稳定地址、Ingress 管七层入口，边界重叠处最易出事故。
- 不可变字段决定变更是“打补丁”还是“删掉重建”，这是 <u>`apply` 报 immutable 错误</u>的根源。
- IaC 的价值在**先出计划、再执行**：`plan`/`diff` 把破坏性动作提前暴露给评审，状态文件让“上次建了什么”可查。
- 漂移是常态：要么持续对账（GitOps），要么每次 `plan` 显式回收，<u>不能靠“应该没人动过”</u>。

## 思考题

618 前两小时，业务要求把退款 worker 从 3 个副本扩到 12 个。运维希望在控制台直接改，理由是“改个数字而已，流水线来不及”。你会怎么处理？请写出可接受的临时方案、需要立刻确认的风险，以及大促后必须补上的机制。

参考思路：区分“变更本身”与“变更的通道”。扩副本是可逆的原地更新，临时在控制台操作并非不可接受，但前提是配额、HPA 行为、支付商限流与连接池余量都确认过——12 个 worker 意味着 12 份连接和 12 倍对外并发。可接受的做法是授权一人操作、记录前后值，并把数字回写清单或交给 HPA。大促后要补的是：扩缩交给 HPA，生产写权限从个人收回到流水线。

## 小测

1. 下列哪种服务模型下，你仍要自己负责操作系统安全补丁？  
   A. IaaS　B. PaaS　C. SaaS　D. FaaS
2. 判断：把 Deployment 的 `replicas` 从 3 改成 5，Kubernetes 会原地修改已有 Pod 的配置。对还是错？为什么？
3. Deployment、Service、Ingress 三者的职责分别是什么？哪个负责终止 TLS？
4. 什么是“漂移”？为什么 `plan` 能发现它，而 `kubectl apply` 往往不能？
5. 场景题：团队要上线新的回调域名并启用 HTTPS，运维提议“在控制台点几下，五分钟搞定”。你会要求改成什么方式，理由是什么？

## 答案与解析

1. **A。**IaaS 只交付基础设施，补丁、运行时与中间件都归你。B 与 D 由厂商维护运行时，C 连应用都由厂商运营——代价是交出控制权。
2. **错。**容器启动后不能就地改配置，控制器会**新建** Pod 并逐步替换旧的，这正是滚动更新的含义。把“改数字”当成“改实例”，是虚拟机时代的经验，会误判资源开销与回滚窗口。
3. Deployment 管副本、滚动更新与版本历史；Service 给一组 Pod 稳定地址并做四层负载均衡；Ingress 做七层路由与 **TLS 终止**。混为一谈的后果，是把证书配在 Service 上，或指望它按路径分流。
4. *漂移*是实际状态偏离期望状态。`plan` 能发现，是因为它把声明、状态账本与真实 API 三方读出来比对；`kubectl apply` 只声明“这些字段该是什么”，<u>不会告诉你实际状态多出了什么</u>，也报不出你手工删掉的资源。
5. 应要求走 IaC 与流水线。理由不在“控制台不好用”，而在域名与证书是跨系统资源（DNS、证书、Ingress、负载均衡），手工操作留不下可复核的 diff，续期与吊销也需自动化。折中是先演练一遍、把耗时压到大促窗口可接受；确需手工操作必须回写清单，否则下次 `plan` 会试图删掉它。

### 动手实验参考

关键观察有三个：`selector` 一变就必须重建，说明“无法原地更新”来自字段语义；退出码变化让流水线能在破坏前停下；`owner` 被列入回收，说明**期望状态是唯一事实来源，多出来的东西都会被清掉**。

## 延伸阅读与下一课

- NIST：[SP 800-145](https://csrc.nist.gov/pubs/sp/800/145/final)（服务模型定义来源）。
- Kubernetes：[Concepts](https://kubernetes.io/docs/concepts/)（对象模型与控制器职责）。
- Kubernetes：[Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)（滚动更新与 `selector` 不可变）。
- Terraform：[Introduction](https://developer.hashicorp.com/terraform/intro)（`plan`/`apply` 与状态文件的作用）。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[CI/CD、变更、灰度与回滚](09-cicd-migrations-canary-and-rollback.md)。
- 下一课：[开发、测试与交付阶段综合测评](11-stage-assessment.md)。
