---
title: 距离度量、向量索引与向量数据库
slug: vector-index-and-vector-databases
module: ai-solutions
stage: design
type: core
difficulty: intermediate
duration: 55m
prerequisites:
  - embeddings-vectors-and-similarity
outcomes:
  - 说明 HNSW 与 IVF 两类索引的结构差异及其对召回和内存的影响
  - 量化近似检索的召回损失，并为 nprobe / ef_search 给出有依据的取值
  - 依据数据量、过滤需求、租户隔离和运维能力选择向量存储方案
last_reviewed: 2026-10-19
---

# 距离度量、向量索引与向量数据库

## 为什么需要学习

晴空商城的售后政策库只有 1.2 万条片段时，检索代码是“全表算余弦再排序”，每次几十毫秒，简单可靠。半年后历史工单也进了索引，片段数涨到 480 万，同一条查询要扫描 480 万 × 1536 个浮点数，接口 p95 从 90 毫秒涨到 4 秒，客服端开始超时重试。

更麻烦的是“加索引”之后出现了新的投诉：客户问“华东仓发错货怎么退”，明明有对应条款，系统却答“未找到相关政策”。工程师加了索引，却没测量索引带来的召回损失。

> **核心结论：** 近似最近邻（ANN）索引用召回率换速度；不量化召回损失就上线，等于用偶发的“查不到”换取不可见的性能数字。

## 学习目标

完成本课后，你能够：

- 解释 *ANN*、*HNSW*、*IVF*、*量化* 的含义，并画出它们在内存、建索引时间和召回上的差别。
- 用一个小实验测出 nprobe（或 `ef_search`）与 recall@k 的曲线，并据此选定参数。
- 判断一条向量查询为什么“没用上索引”，并写出能被索引命中的 SQL。
- 为跨租户的知识库选出隔离方案，并说明不隔离的后果。

## 前置知识

- 回看上一课：[Embedding、向量与语义相似度](01-embeddings-vectors-and-similarity.md)。
- 会写基本 SQL，理解 `WHERE`、`ORDER BY`、`LIMIT` 与普通 B-tree 索引的作用。
- 知道“近似”意味着结果可能不完整，而不一定报错。
- 了解 Postgres 是可扩展的关系库，本课以 pgvector 为主要示例。

## 业务场景

售后智能助手每天约 2.6 万次检索，90% 的问题只需要 top-8 片段。晴空商城的订单、政策和工单本来就存在 Postgres 里，团队不希望为了向量再引入一套独立集群，于是选择 pgvector 起步，并设定三条约束：检索 p95 不超过 300 毫秒；同一索引内要按商家租户严格隔离；政策改版后 5 分钟内新条款可被检索到。

这三条约束分别对应本课的三个主题：索引参数决定延迟，过滤策略决定隔离与召回，写入与重建流程决定新鲜度。

## 核心概念

*向量索引* 是为高维向量建立的可快速查找近邻的数据结构；*ANN（近似最近邻）* 是这类索引的共同策略：牺牲少量召回换取数量级的加速。*召回率 recall@k* 指“精确 top-k 中有多少比例被近似检索找回”。

| 索引 | 结构 | 建索引 | 查询调参 | 主要权衡 |
| --- | --- | --- | --- | --- |
| 精确扫描（无索引） | 逐条比对 | 无 | 无 | 召回 100%，延迟随数据量线性增长 |
| *HNSW* | 多层可导航小世界图 | 慢，占内存 | `ef_search` | 查询快、召回高；内存与建索引时间高 |
| *IVF*（倒排文件） | k-means 聚成若干列表 | 需先有数据训练 | `probes` | 省内存、建得快；召回低于 HNSW |
| *量化*（PQ / 二值） | 压缩向量表示 | 需训练 | 与重排配合 | 索引变小；必须用原向量重排补召回 |
| 专用向量库 | 独立服务 + 段/分片 | 视实现 | 视实现 | 规模与功能强；多一套运维与一致性负担 |

几个容易混淆的词：*预过滤* 是先在元数据上筛出候选再算相似度，*后过滤* 是先取近邻再用条件筛掉。pgvector 官方文档明确说明：使用近似索引时，过滤是在索引扫描之后应用的，因此过滤条件命中率低时会拿不到足够结果。

## 工作原理

以最常见的一条链路为例（Postgres + pgvector，HNSW 索引）：

1. **确定度量**：入库前把所有向量归一化，之后统一用余弦（或内积）；度量必须与索引算子一致，否则索引不生效。
2. **写入行**：向量与元数据（租户、文档 ID、版本、生效时间）写入同一张表，事务保证一致性。
3. **建索引**：HNSW 按 `m`（每层最大连接数，默认 16）与 `ef_construction`（建图候选队列，默认 64）构建多层图，无需训练数据即可建；IVF 则要先用已有数据跑 k-means 得到列表中心。
4. **查询编码**：问题向量化后按距离算子排序，例如 `ORDER BY embedding <=> $1 LIMIT 8`。
5. **图导航**：HNSW 从高层稀疏图逐层下降，在底层用 `ef_search`（默认 40）大小的候选队列扩展，返回其中最近的若干点。
6. **过滤**：带 `WHERE tenant_id = ...` 时，过滤发生在索引扫描之后，所以先取 40 个候选再筛掉 90%，可能只剩 4 条。pgvector 0.8 起可用迭代扫描（`hnsw.iterative_scan`）在结果不足时继续扫索引。
7. **回归验证**：对比近似结果与关闭索引的精确结果，得到真实召回率，再决定是否调大参数。

<u>第 6 步是最常见的生产事故来源</u>：参数看起来“调好了”，一加过滤条件就悄悄丢结果，而且不报错。

## 架构与选型

| 方案 | 适用 | 不适用 | 选型依据 |
| --- | --- | --- | --- |
| Postgres + pgvector | 已有 Postgres；百万级片段；需要事务与 JOIN | 上亿向量；需要复杂多路召回与原生混合检索 | 一致性、事务、备份复用现有能力 |
| 专用向量数据库 | 千万级以上；多副本、分片、多租户隔离成熟 | 团队不想再维护一套有状态服务 | 规模与运维功能优先 |
| 搜索引擎（含向量字段） | 已经用它做站内搜索，需要 BM25 + kNN 融合 | 只做纯语义检索、对资源敏感 | 混合检索开箱可用 |
| 内存索引库（hnswlib / FAISS 类） | 离线评测、批处理、单机原型 | 需要在线增删、持久化与并发 | 极致性能与实验灵活度 |

维度会直接限制可选方案。截至 2026-10-19，pgvector 文档说明可建索引的 `vector` 最多 2000 维，`halfvec` 最多 4000 维，二值向量最多 64000 维；主流的 3072 维模型因此需要用半精度、降维或子向量索引。选型时先确认这个硬约束，再谈性能。

## 最小示例

下面用 Python 3 标准库实现一个极简 IVF：先用 k-means 聚类，再只扫描最近的几个列表，从而直观看到 `probes` 与召回率的关系。它等价于 IVFFlat 的核心机制，不依赖任何第三方包。

```python
import random

random.seed(7)
DIM, N, LISTS, K = 16, 800, 25, 10   # 16 维、800 条片段、25 个列表、取 top-10

def rand_vec():
    # 用高斯随机向量模拟已编码的政策片段
    return [random.gauss(0.0, 1.0) for _ in range(DIM)]

def dist2(a, b):
    # 平方欧氏距离：与 L2 同序，省一次开方
    return sum((x - y) ** 2 for x, y in zip(a, b))

def mean(vecs):
    return [sum(col) / len(vecs) for col in zip(*vecs)]

# 文档带稳定 ID，避免用列表下标反查
docs = [(i, rand_vec()) for i in range(N)]
centroids = [vec for _, vec in random.sample(docs, LISTS)]

for _ in range(10):                    # 对应 IVFFlat 建索引时的 k-means 训练
    buckets = [[] for _ in range(LISTS)]
    for doc_id, vec in docs:
        c = min(range(LISTS), key=lambda j: dist2(vec, centroids[j]))
        buckets[c].append((doc_id, vec))
    for j, bucket in enumerate(buckets):
        if bucket:                     # 空桶保留原质心，避免除零
            centroids[j] = mean([vec for _, vec in bucket])

def exact_topk(q, k):
    # 精确基线：暴力扫描全部向量，召回率定义为 100%
    return [i for i, _ in sorted(docs, key=lambda d: dist2(q, d[1]))[:k]]

def ivf_topk(q, k, nprobe):
    # 只扫描最近的 nprobe 个列表，这就是“近似”的来源
    order = sorted(range(LISTS), key=lambda j: dist2(q, centroids[j]))[:nprobe]
    cand = [item for j in order for item in buckets[j]]
    best = sorted(cand, key=lambda d: dist2(q, d[1]))[:k]
    return [i for i, _ in best], len(cand)

print("nprobe  avg_candidates  recall@10")
for nprobe in (1, 2, 4, 8, LISTS):
    hits, scans = 0.0, 0
    for _ in range(50):
        q = rand_vec()                                  # 随机问题向量
        truth = set(exact_topk(q, K))                   # 精确 top-10 作为标准答案
        got, scanned = ivf_topk(q, K, nprobe)
        hits += len(truth & set(got)) / K               # 命中比例
        scans += scanned
    print(f"{nprobe:6d}  {scans/50:14.1f}  {hits/50:.3f}")
```

预期输出（已用 `python3 ivf_demo.py` 在本机实际运行；因随机种子固定，结果可复现）：

```text
nprobe  avg_candidates  recall@10
     1            33.5  0.302
     2            65.9  0.428
     4           132.2  0.662
     8           258.4  0.838
    25           800.0  1.000
```

读法：只扫 1 个列表时只看了约 4% 的候选就丢掉 70% 的正确答案；扫 8 个列表能拿回 83.8% 的召回，代价是候选数约为全量的三分之一。**生产上要选的是“满足召回目标的最小候选数”，而不是扫描比例越低越好。**

对应的 pgvector 写法如下（未在本机数据库执行，标注为预期行为）：

```sql
CREATE INDEX ON policy_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);   -- 每个距离函数需单独建索引

SET LOCAL hnsw.ef_search = 100;            -- 单次查询内调大候选队列
SET LOCAL hnsw.iterative_scan = strict_order;  -- 过滤后结果不足时继续扫

SELECT id, content
FROM policy_chunks
WHERE tenant_id = $1                       -- 过滤在索引扫描之后生效
ORDER BY embedding <=> $2                  -- 必须是距离算子本身
LIMIT 8;
```

## 动手实验

**前置条件**：Python 3.9+，无需数据库与网络。

1. 保存代码为 `ivf_demo.py`，运行 `python3 ivf_demo.py`，记录每个 `nprobe` 的召回率。
2. 把 `LISTS` 改为 8 和 100，各重跑一次，观察同样的 `nprobe` 下召回如何变化。
3. 把 `K` 改为 3，观察 top-3 与 top-10 的召回差异。
4. 删除临时文件。

**预期结果**：`LISTS` 变小（列表更少、每列更长）时，同样 `nprobe` 的候选数上升、召回上升；`LISTS` 变大时召回下降但候选数更少。top-3 的召回通常高于 top-10，因为正确答案更容易挤进更短的榜单。

**验证方法**：`nprobe = LISTS` 那一行必须等于 1.000 且候选数等于 N，这是“退化为精确检索”的自检点。若不为 1，说明候选收集或去重有误。

**清理方法**：删除 `ivf_demo.py`；不写数据库、不产生费用。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 建了索引但查询仍很慢 | `ORDER BY` 用了表达式而非距离算子，或缺 `LIMIT` | 执行 `EXPLAIN (ANALYZE, BUFFERS)` 看是否走索引扫描 | 改成 `ORDER BY embedding <=> $1 LIMIT n`，算子保持升序 |
| 加 `WHERE` 后返回条数变少 | 过滤在索引扫描之后，候选被筛空 | 统计带过滤与不带过滤的返回行数 | 调大 `ef_search`、启用迭代扫描、对高频过滤值建部分索引 |
| IVFFlat 召回莫名很低 | 表还是空的就建了索引，k-means 训练不充分 | 检查建索引时表的行数 | 先灌数据再建索引，`lists` 用 rows/1000 或 sqrt(rows) 起步 |
| 明明有数据却检索不到 | 向量为 `NULL` 或零向量，不会进入索引 | 统计 `embedding IS NULL` 与全零向量行数 | 入库前校验向量非空、非零 |
| 3072 维模型建 HNSW 失败 | `vector` 索引上限 2000 维 | 查看报错中的维度提示 | 用 `halfvec`、降维或子向量索引 |
| 升级索引参数后结果和昨天不同 | 近似索引本身不保证结果稳定 | 与关闭索引的精确结果比对 | 把召回率纳入回归测试，参数变更需评审 |

## 安全与生产注意事项

**<u>多个租户共用一个近似索引，会让其他租户的数据影响本租户的召回与延迟，并可能把别人的内容检索出来。</u>**pgvector 文档给出的做法是按 `tenant_id` 做列表分区或使用独立表；仅靠应用层 `WHERE` 而共用一张大索引，既不能保证隔离，也无法保证召回。租户标识必须来自服务端会话，绝不能取自客户端传入的参数。

**<u>删除文档不等于删除向量：近似索引中的死元组需要 vacuum 才回收，旧内容可能在一段时间内仍被检索到并被模型引用。</u>**删除流程要包含索引清理、缓存失效与检索回归验证，而不是只删业务表。

另外三点：大维度向量会让内存与备份体积膨胀，需按“向量数 × 维度 × 每元素字节”估算容量；全量重建索引期间应使用并发建索引避免阻塞写入；向量库快照包含原文片段，备份文件的访问权限与保留期必须与业务库同级管理。

## 本课总结

- **ANN 索引换的是速度，代价是可量化的召回损失；不测召回的调参只是猜测。**
- HNSW 查询快、内存与建索引成本高；IVF 省内存、建得快，但需要先有数据训练。
- 距离度量必须与索引算子一致，归一化后余弦与内积可互换。
- 近似索引下的过滤发生在扫描之后，这是“带条件检索丢结果”的根因。
- 租户隔离要做在存储结构上（分区或独立表），不能只做在 SQL 的 `WHERE` 里。

## 思考题

晴空商城的政策库要从 480 万片段增长到 3000 万，并新增“按商家 + 按商品类目”的双重过滤。你会继续用 pgvector 加分区，还是迁移到专用向量库？请给出容量估算、延迟预算的拆分（编码、检索、重排各占多少）、迁移期的双写与回滚方案，以及你会用什么指标判定迁移成功或失败。

参考思路：先估算 3000 万 × 维度 × 字节的存储与内存占用，判断是否需要量化；再判断双过滤下的候选命中率，若单次过滤后经常不足 8 条，分区或专用库的预过滤能力就是关键；迁移用影子读比对召回与延迟，以 recall@8 与 p95 延迟为成败判据。

## 小测

1. 关闭索引的精确检索召回率是多少？为什么它仍然可能不适合生产？
2. 在 pgvector 中，下列哪种写法最可能用上 HNSW 索引？  
   A. `ORDER BY 1 - (embedding <=> $1) DESC LIMIT 8`　B. `ORDER BY embedding <=> $1 LIMIT 8`　C. `WHERE embedding = $1`　D. `ORDER BY id LIMIT 8`
3. IVF 索引为什么要求“先有数据再建索引”？
4. `recall@10 = 0.84` 在你的场景里意味着什么？可以接受吗？
5. 场景题：客服反馈“搜索只返回 2 条政策，但库里明显有 6 条相关”。你最先检查什么？

## 答案与解析

1. **100%。**它逐条比对全部向量。不适合生产的原因是延迟随向量数线性增长，且无法支撑并发与过滤场景，数据量一大就超时。
2. **B。**只有“距离算子直接出现在 `ORDER BY` 且升序”时索引才可能生效。A 把距离包在表达式里并降序，索引不会用；C 是等值比较，与近邻搜索无关；D 与向量无关。
3. 因为 IVF 需要先用 k-means 把现有向量聚成若干列表，列表中心来自真实数据。空表或数据极少时训练出的中心没有代表性，召回会显著下降。
4. 意味着精确 top-10 里有 1–2 条被漏掉。是否可接受取决于漏掉的那条是否是唯一正确条款——这正是要用业务标注集评估、而不是只看均值的原因。
5. 先确认过滤条件命中率与 `ef_search`：常见组合是“高选择性 `WHERE` + 默认 `ef_search=40`”，扫描 40 个候选后只剩 2 条通过过滤。验证方法是临时去掉过滤再查一次，或开启迭代扫描对比返回条数。

## 延伸阅读与下一课

- [pgvector 官方 README（HNSW/IVFFlat 参数、过滤、多租户与迭代扫描）](https://github.com/pgvector/pgvector)，复核日期 2026-10-19。
- [pgvector 讨论的 HNSW 论文：Efficient and Robust Approximate Nearest Neighbor Search using Hierarchical Navigable Small World Graphs](https://arxiv.org/abs/1603.09320)，复核日期 2026-10-19。
- 返回[本单元目录](00-overview.md)。
- 回看上一课：[Embedding、向量与语义相似度](01-embeddings-vectors-and-similarity.md)。
- 下一课：[文档加载、解析、清洗与元数据](03-document-ingestion-and-metadata.md)。
