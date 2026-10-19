---
title: OpenTelemetry、Prometheus 与 Grafana
slug: opentelemetry-prometheus-grafana
module: traditional-solutions
stage: operate-and-optimize
type: core
difficulty: intermediate
duration: 55m
prerequisites:
  - correlation-id-and-request-tracing
outcomes:
  - 区分 trace、metrics、logs 三类信号各自回答的问题，并说明 OpenTelemetry 的 API、SDK 与 Collector 各承担什么职责
  - 为退款受理链路选择 counter、gauge、histogram，写出错误率与 p95 延迟的 PromQL 查询
  - 按 SLI、看板、告警三层设计 Grafana 面板，并指出两类标签风险
last_reviewed: 2026-10-19
---

# OpenTelemetry、Prometheus 与 Grafana

## 为什么需要学习

晴空商城的退款链路能记结构化日志，也能按 `request_id` 串起一次请求。但上月支付商抖动十五分钟时，值班仍说不清：错误率多少、慢在哪一跳、怎么自证清白。

三个人都在看数据，却没有同一口径：一个用日志条数除以日志总量算出 0.3%，因为分母只含被采样的部分；一个打开的支付商控制台只有月报；一个盯着 `top`，CPU 只有 12%。

> **核心结论：** 日志回答“发生了什么”，指标回答“现在是否越界”，追踪回答“慢在哪一跳”——要的是一套共享口径，而不是三个各自正确的后台。

## 学习目标

完成本课后，你能够：

- 说清 trace、metrics、logs 的分工，指出 OpenTelemetry 的 API、SDK、Collector 各负责哪一段。
- 为退款受理接口选定 `counter`、`gauge`、`histogram`，写出错误率与 p95 延迟的 PromQL。
- 设计含错误率、延迟分位、队列深度三个面板的看板，说明各面板对应的 SLI 与告警。
- 指出标签基数与敏感标签的代价，各给一个缓解手段。

## 前置知识

- 回看上一课：[Correlation ID 与请求链路](02-correlation-id-and-request-tracing.md)。
- 知道状态码 2xx、4xx、5xx 的含义，能读懂一行结构化日志。
- 会运行 `python3` 脚本，能改常量后重新执行。
- 知道平均值会掩盖长尾，理解延迟与吞吐的区别。

## 业务场景

`refund-service` 承接客服提交的退款：校验订单、调支付商接口、写退款单、通知仓库。SLO 草案：错误率低于 2%，延迟 p95 低于 2 秒。

三个信息来源都答不了 SLO：日志平台只留 7 天且按条计费；支付商控制台只有月报；服务器监控只有 CPU 与磁盘。客服要求五分钟内回答“是错还是慢、慢在支付商还是仓库”，且数据里不得出现完整手机号与卡号。预算约两名工程师一天成本。

## 核心概念

*可观测性*指只凭输出数据推断内部状态的能力；它比*监控*更宽——监控问“想好的指标是否越界”，可观测性问“没见过的问题能否查出”。

- *遥测信号*指 trace、metrics、logs 三类输出，共享上下文才能互相跳转。
- *Trace* 是一次请求的调用树，*Span* 是树上一节点，带名称、属性、起止时间与状态。
- *上下文传播*：把 `traceparent` 放进出站请求头或消息属性，让下游接上同一棵树；W3C Trace Context 是跨厂商标准。
- *OpenTelemetry* 是信号产生与传输的规范加实现：*API* 定义怎么打点，*SDK* 负责采样、聚合、导出，*Collector* 独立负责接收、加工、转发。
- *OTLP* 是 OTel 的传输协议（gRPC 4317、HTTP 4318）；Collector 用 *receiver* 收、*exporter* 发，中间串成 *pipeline*。
- *时间序列*由指标名加一组标签确定；*标签基数*是标签组合的数量，它而非数据点数决定存储成本。`/metrics` 以 *exposition 格式* 输出，一行一个样本。
- *counter* 只增不减，*gauge* 可上可下，*histogram* 用累计桶记分布，*summary* 在客户端算好分位数；*recording rule* 预计算查询，*alerting rule* 定期求值；*看板*是一组面板的集合，每个面板本质是一条按时间取样的查询。

| 信号 | 数据形态 | 回答什么 | 成本驱动 | 退款链路的用法 |
| --- | --- | --- | --- | --- |
| trace | 带父子关系的 span 树 | 这次请求慢在哪一跳 | 请求量 × 采样率 × span 数 | 慢在支付商还是仓库 |
| metrics | 带标签的数值时间序列 | 错误率、延迟、饱和度是否越界 | 基数 × 抓取频率 × 保留期 | SLI 计算与告警 |
| logs | 带时间戳的事件 | 具体错误码与参数 | 字节数 × 保留期 | 拿到 `error_code` |

| 类型 | 能否减少 | 适合表达 | 关键查询 | 典型误用 |
| --- | --- | --- | --- | --- |
| counter | 不能，重启才归零 | 累计发生次数 | `rate()`、`increase()` | 直接画原始值当速率 |
| gauge | 能上下波动 | 瞬时状态，如队列深度 | 聚合、`avg_over_time()` | 拿来累计次数 |
| histogram | 桶计数只增 | 分布与分位数 | `histogram_quantile()` 配 `sum by (le)` | 对 `_bucket` 求平均 |
| summary | 客户端算好分位 | 单实例分位 | 直接读 | 跨实例求平均 |

<u>“各实例 p95 的加权平均”不是整体 p95</u>：分位数不可加，必须从桶重新计算。

## 工作原理

一次退款请求从进入服务到出现在看板上：

1. **接上下文**：入口读 `traceparent`，缺失时新建 trace，并沿用上游 `X-Request-Id`。
2. **建 span**：入口、支付商调用、写库各一个，属性用语义约定的名字（如 `refund.id`），避免自创同义字段。
3. **记指标**：counter 按 `route`、`status_class` 累加，gauge 反映队列深度，耗时进 histogram 累计桶。
4. **日志带标识**：写 `trace_id` 与 `request_id`，指标跳 trace、trace 跳日志都不用手工拼查询。
5. **导出**：SDK 按批走 OTLP 发往 Collector，失败缓冲重试；<u>缓冲不能无上限</u>，否则后端故障拖垮业务。
6. **Collector 加工**：`memory_limiter` 防自爆，`batch` 提吞吐，`attributes` 删敏感字段，尾部采样保留全部错误 trace、正常抽 10%。
7. **落地与抓取**：Prometheus 每 15 秒拉 `/metrics`（或收 remote write）；拉模型让目标存活直接体现为 `up`。
8. **规则求值**：recording rule 存下 `sum(rate(...))`；alerting rule 判断“错误率 > 2% 持续 10 分钟”，未满算 pending。
9. **告警与回查**：Alertmanager 分组、抑制重复；值班顺序是“面板确认越界 → trace 找慢的那一跳 → 用 `trace_id` 取日志”。

接缝要定死：OTel 推、Prometheus 拉，接点通常是 Collector 的 `prometheus` exporter 或 remote write；<u>两种并存会出两份口径。</u>

## 架构与选型

| 决策点 | 选项 | 适用 | 不适用 | 代价 |
| --- | --- | --- | --- | --- |
| 采集路径 | SDK 直连后端 | 单服务、已有托管 OTLP | 多语言、需脱敏或尾采样 | 密钥散落在各服务 |
| 采集路径 | SDK → 每节点 agent | Kubernetes、跨团队统一 | 需集中改写与跨节点采样 | 节点资源占用，配置须下发 |
| 采集路径 | SDK → gateway Collector | 统一鉴权、脱敏、分流 | 小规模、trace 量极低 | 多一跳，得做高可用 |
| 指标存储 | 自建 Prometheus | 单集群、保留 15 天左右 | 跨集群长期查询 | 自管容量与高可用 |
| 指标存储 | 远程写加托管时序库 | 多集群、长保留、按量付费 | 预算紧、量小 | 外部依赖与出口成本 |
| 看板 | Grafana 或代码化 provisioning | 多数据源混排、看板要评审 | 一次性探索 | 模板与权限需治理 |

顺序是先定 SLI 与保留期，再选存储，再选看板：SLI 决定标签，保留期决定成本。<u>没有告警规则的看板只是壁纸</u>：面板解释，告警叫醒人，两者须同源。

## 最小示例

下面用两次抓取的样本验证三件最容易记错的事：counter 重启后怎么算增量、histogram 桶怎么插出 p95、告警为什么需要“持续 N 次”。环境 Python 3.9 以上，只用标准库；两段样本隔 30 秒，导出接口的 counter 因重启回落。

```python
"""把两次抓取的 Prometheus 暴露格式样本，换算成错误率 SLI 与 p95 延迟。

等价 PromQL：
  错误率 = sum(rate(refund_requests_total{route!="/api/v1/refunds/export",status_class="5xx"}[5m]))
          / sum(rate(refund_requests_total{route!="/api/v1/refunds/export"}[5m]))
  p95   = histogram_quantile(0.95,
            sum by (le) (rate(refund_request_duration_seconds_bucket[5m])))
"""
import re

SCRAPE_T0 = """
# TYPE refund_requests_total counter
refund_requests_total{route="/api/v1/refunds",status_class="2xx"} 4201
refund_requests_total{route="/api/v1/refunds",status_class="5xx"} 31
refund_requests_total{route="/api/v1/refunds/{id}",status_class="2xx"} 1880
refund_requests_total{route="/api/v1/refunds/{id}",status_class="5xx"} 12
refund_requests_total{route="/api/v1/refunds/export",status_class="2xx"} 900
# TYPE refund_request_duration_seconds histogram
refund_request_duration_seconds_bucket{le="0.05",route="/api/v1/refunds"} 1900
refund_request_duration_seconds_bucket{le="0.1",route="/api/v1/refunds"} 3200
refund_request_duration_seconds_bucket{le="0.25",route="/api/v1/refunds"} 3900
refund_request_duration_seconds_bucket{le="0.5",route="/api/v1/refunds"} 4130
refund_request_duration_seconds_bucket{le="1",route="/api/v1/refunds"} 4200
refund_request_duration_seconds_bucket{le="2.5",route="/api/v1/refunds"} 4228
refund_request_duration_seconds_bucket{le="+Inf",route="/api/v1/refunds"} 4232
refund_request_duration_seconds_bucket{le="0.05",route="/api/v1/refunds/{id}"} 1500
refund_request_duration_seconds_bucket{le="0.1",route="/api/v1/refunds/{id}"} 1700
refund_request_duration_seconds_bucket{le="0.25",route="/api/v1/refunds/{id}"} 1820
refund_request_duration_seconds_bucket{le="0.5",route="/api/v1/refunds/{id}"} 1865
refund_request_duration_seconds_bucket{le="1",route="/api/v1/refunds/{id}"} 1885
refund_request_duration_seconds_bucket{le="2.5",route="/api/v1/refunds/{id}"} 1890
refund_request_duration_seconds_bucket{le="+Inf",route="/api/v1/refunds/{id}"} 1892
"""

SCRAPE_T1 = """
# TYPE refund_requests_total counter
refund_requests_total{route="/api/v1/refunds",status_class="2xx"} 4233
refund_requests_total{route="/api/v1/refunds",status_class="5xx"} 35
refund_requests_total{route="/api/v1/refunds/{id}",status_class="2xx"} 1890
refund_requests_total{route="/api/v1/refunds/{id}",status_class="5xx"} 13
refund_requests_total{route="/api/v1/refunds/export",status_class="2xx"} 12
# TYPE refund_request_duration_seconds histogram
refund_request_duration_seconds_bucket{le="0.05",route="/api/v1/refunds"} 1916
refund_request_duration_seconds_bucket{le="0.1",route="/api/v1/refunds"} 3222
refund_request_duration_seconds_bucket{le="0.25",route="/api/v1/refunds"} 3920
refund_request_duration_seconds_bucket{le="0.5",route="/api/v1/refunds"} 4152
refund_request_duration_seconds_bucket{le="1",route="/api/v1/refunds"} 4229
refund_request_duration_seconds_bucket{le="2.5",route="/api/v1/refunds"} 4265
refund_request_duration_seconds_bucket{le="+Inf",route="/api/v1/refunds"} 4268
refund_request_duration_seconds_bucket{le="0.05",route="/api/v1/refunds/{id}"} 1502
refund_request_duration_seconds_bucket{le="0.1",route="/api/v1/refunds/{id}"} 1708
refund_request_duration_seconds_bucket{le="0.25",route="/api/v1/refunds/{id}"} 1833
refund_request_duration_seconds_bucket{le="0.5",route="/api/v1/refunds/{id}"} 1881
refund_request_duration_seconds_bucket{le="1",route="/api/v1/refunds/{id}"} 1899
refund_request_duration_seconds_bucket{le="2.5",route="/api/v1/refunds/{id}"} 1900
refund_request_duration_seconds_bucket{le="+Inf",route="/api/v1/refunds/{id}"} 1903
"""

# 一行样本 = 指标名 + 可选 {标签} + 数值；HELP/TYPE 行不含数据
SAMPLE = re.compile(r'^(?P<name>[a-zA-Z_:][\w:]*)(?:\{(?P<labels>.*)\})?\s+(?P<value>\S+)$')


def parse(text):
    """返回 {(指标名, 标签对): 数值}；标签排序后作键，两次抓取才能逐条比对。"""
    samples = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = SAMPLE.match(line)
        if not match:
            raise ValueError(f"无法解析的样本行: {line}")
        pairs = []
        for item in (match["labels"] or "").split(","):
            if not item:
                continue
            key, _, value = item.partition("=")
            pairs.append((key.strip(), value.strip().strip('"')))
        samples[(match["name"], tuple(sorted(pairs)))] = float(match["value"])
    return samples


def increase(old, new, label):
    """counter 的增量；回落到更小值说明进程重启，按“清零后重新累加”处理。"""
    if new >= old:
        return new - old
    print(f"[reset] {label} 从 {old} 回落到 {new}，按重启处理，增量记为 {new}")
    return new


def main():
    t0, t1 = parse(SCRAPE_T0), parse(SCRAPE_T1)
    window = 30.0  # 两次抓取相隔 30 秒；生产中换成 5 分钟窗口以平滑抖动

    # 步骤 1：先求增量（顺带发现重启），再按 route 过滤出 SLO 范围
    deltas = {}
    for (name, labels), value in t1.items():
        if name != "refund_requests_total":
            continue
        tags = dict(labels)
        deltas[(tags["route"], tags["status_class"])] = increase(
            t0[(name, labels)], value, f'route="{tags["route"]}"'
        )
    errors = 0.0
    total = 0.0
    for (route, status_class), delta in deltas.items():
        if route == "/api/v1/refunds/export":  # 不在本 SLO 范围内
            continue
        total += delta
        if status_class == "5xx":
            errors += delta
    ratio = errors / total if total else 0.0
    print(f"[SLI] 退款受理错误率 = {errors}/{total} = {ratio:.2%}（阈值 2.00%）")

    # 步骤 2：告警状态机；单次命中只能 pending，连续 3 次命中才 firing
    breached = ratio > 0.02
    state = "pending（第 1 次命中，需连续 3 次才 firing）" if breached else "ok"
    print(f"[ALERT] refund_error_rate_high: {state}")

    # 步骤 3：histogram 的桶是累计值，先按 le 求和，再算每桶增量
    buckets, old_buckets = {}, {}
    for target, source in ((buckets, t1), (old_buckets, t0)):
        for (name, labels), value in source.items():
            if name != "refund_request_duration_seconds_bucket":
                continue
            key = float("inf") if dict(labels)["le"] == "+Inf" else float(dict(labels)["le"])
            target[key] = target.get(key, 0.0) + value

    ordered = sorted(buckets)
    counts, previous = [], 0.0
    for upper in ordered:
        cumulative = buckets[upper] - old_buckets[upper]
        counts.append((upper, cumulative - previous))
        previous = cumulative
    cumulative_check = [sum(c for _, c in counts[: i + 1]) for i in range(len(counts))]
    monotonic = all(a <= b for a, b in zip(cumulative_check, cumulative_check[1:]))
    print(f"[CHECK] 合并后的桶累计值单调递增：{'通过' if monotonic else '失败'}")

    # 步骤 4：histogram_quantile 在命中桶内插值；+Inf 桶作为兜底
    observations = cumulative_check[-1]
    rank = 0.95 * observations
    lower, cumulative_before = 0.0, 0.0
    for index, (upper, count) in enumerate(counts):
        reached = cumulative_check[index]
        if reached >= rank:
            span = upper - lower if upper != float("inf") else 0.0
            fraction = (rank - cumulative_before) / count if count else 0.0
            print(f"[SLI] 受理延迟 p95 = {lower + span * fraction:.2f}s（在桶 ({lower}, {upper}] 内插值）")
            break
        lower, cumulative_before = upper, reached


if __name__ == "__main__":
    main()
```

运行 `python3 sli_calc.py` 后实际输出：

```text
[reset] route="/api/v1/refunds/export" 从 900.0 回落到 12.0，按重启处理，增量记为 12.0
[SLI] 退款受理错误率 = 5.0/47.0 = 10.64%（阈值 2.00%）
[ALERT] refund_error_rate_high: pending（第 1 次命中，需连续 3 次才 firing）
[CHECK] 合并后的桶累计值单调递增：通过
[SLI] 受理延迟 p95 = 1.62s（在桶 (1.0, 2.5] 内插值）
```

三点说明。`increase()` 的回落判断对应 PromQL 的 counter 重置，<u>直接对原始 counter 做减法会在重启时算出负速率</u>。桶必须先按 `le` 求和再差分，否则两个 `route` 的分布会被当成两条曲线。`p95 = 1.62s` 来自桶 `(1, 2.5]` 的线性插值，<u>p95 精度不会好于桶宽</u>，桶边界要贴着 SLO。告警只出 `pending`，因为“持续 10 分钟”要靠多次求值累积。

## 动手实验

### 前置条件

Python 3.9 以上与一份可写目录；可选步骤需要本机 Docker，不需外网。

### 步骤

1. 写一个假服务 `refund_metrics.py`，监听 `127.0.0.1:9464`，只开放 `/metrics`：

   ```python
   """晴空商城退款服务的 /metrics 端点：只用标准库，暴露 counter、gauge 和 histogram 桶。"""
   import random
   from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

   BUCKETS = [0.05, 0.1, 0.25, 0.5, 1.0, 2.5]   # 桶边界对齐 SLO，不用库默认值
   LATENCY = [0] * (len(BUCKETS) + 1)           # 累计计数，最后一项是 +Inf 桶
   REQUESTS = {}                                # (route, status_class) -> 累计次数
   QUEUE = [240]                                # 用列表模拟可变状态


   def observe(route, status_class, seconds):
       """一次请求同时更新 counter 与 histogram。"""
       REQUESTS[(route, status_class)] = REQUESTS.get((route, status_class), 0) + 1
       for index, upper in enumerate(BUCKETS):
           if seconds <= upper:
               LATENCY[index] += 1              # 桶是累计值：小于等于边界的都要加
       LATENCY[-1] += 1                        # +Inf 桶必然累加


   def tick():
       """模拟 40 笔新退款；故障时 5xx 比例升高，延迟随之变长。"""
       for _ in range(40):
           route = random.choice(["/api/v1/refunds", "/api/v1/refunds/{id}"])
           slow = random.random() < 0.15
           status_class = "5xx" if slow and random.random() < 0.4 else "2xx"
           observe(route, status_class, random.uniform(0.6, 2.4) if slow else random.uniform(0.01, 0.4))
       QUEUE[0] = max(0, QUEUE[0] + random.randint(-40, 60))


   def render():
       """按暴露格式输出，每行一个样本。"""
       lines = ["# TYPE refund_requests_total counter"]
       for (route, status_class), count in sorted(REQUESTS.items()):
           lines.append(
               f'refund_requests_total{{route="{route}",status_class="{status_class}"}} {count}'
           )
       lines.append("# TYPE refund_queue_depth gauge")
       lines.append(f"refund_queue_depth {QUEUE[0]}")
       lines.append("# TYPE refund_request_duration_seconds histogram")
       for upper, count in zip(BUCKETS + [float("inf")], LATENCY):
           le = "+Inf" if upper == float("inf") else str(upper)
           lines.append(f'refund_request_duration_seconds_bucket{{le="{le}"}} {count}')
       return "\n".join(lines) + "\n"


   class Handler(BaseHTTPRequestHandler):
       def do_GET(self):
           if self.path != "/metrics":          # 只开放一个路径，其余一律 404
               self.send_error(404)
               return
           tick()
           body = render().encode("utf-8")
           self.send_response(200)
           self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
           self.send_header("Content-Length", str(len(body)))
           self.end_headers()
           self.wfile.write(body)

       def log_message(self, *args):
           pass                                 # 关掉抓取访问日志，避免刷屏


   if __name__ == "__main__":
       print("metrics 已监听 http://127.0.0.1:9464/metrics")
       ThreadingHTTPServer(("127.0.0.1", 9464), Handler).serve_forever()
```

2. 启动服务后另开终端抓两份样本：先 `curl -s http://127.0.0.1:9464/metrics > a.txt`，等 15 秒再抓一份存成 `b.txt`。
3. 把最小示例改成读这两个文件（`window = 15.0`），算出本服务自己的错误率与 p95。
4. 用下面的脚本检查标签里有没有混入订单号或手机号：

   ```python
   """检查指标标签里是否混入了订单号、手机号之类的高基数或敏感值。"""
   import re
   import sys
   import urllib.request

   # 命中即认为不适合做维度：4 位以上数字、UUID 片段、手机号段
   ID_LIKE = re.compile(r"\d{4,}|[0-9a-f]{8}-[0-9a-f]{4}|1[3-9]\d{9}|SO-")
   PAIRS = re.compile(r'(\w+)="([^"]*)"')


   def audit(url):
       text = urllib.request.urlopen(url, timeout=5).read().decode("utf-8")  # 只读一次抓取结果
       problems = []
       for line in text.splitlines():
           if line.startswith("#") or not line.strip():
               continue
           name = line.split("{")[0].split(" ")[0]
           for key, value in PAIRS.findall(line):
               if key == "le":
                   continue                     # le 是桶边界，天然低基数
               if ID_LIKE.search(value):
                   problems.append((name, key, value))
       return problems


   if __name__ == "__main__":
       url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9464/metrics"
       found = audit(url)
       if not found:
           print("[OK] 所有标签值都是低基数枚举，可以安全写入长期存储")
       for name, key, value in found:
           print(f'[RISK] {name} 的标签 {key}="{value}" 看起来是具体 ID，会撑爆基数')
       sys.exit(1 if found else 0)
```

5. 可选：写 `prometheus.yml` 指向本服务，加一条告警规则，再在 Grafana 建三个面板：

```yaml
# prometheus.yml
global:
  scrape_interval: 15s        # 与规则求值节奏对齐，避免窗口空一半
rule_files:
  - rules.yml
scrape_configs:
  - job_name: refund-service
    static_configs:
      - targets: ["127.0.0.1:9464"]
```

```yaml
# rules.yml
groups:
  - name: refund-slo
    rules:
      - record: refund:error_ratio5m
        expr: |
          sum(rate(refund_requests_total{status_class="5xx"}[5m]))
          /
          sum(rate(refund_requests_total[5m]))
      - alert: refund_error_rate_high
        expr: refund:error_ratio5m > 0.02
        for: 10m              # 单次越界只算 pending，防止抖动触发
        labels:
          severity: page
        annotations:
          summary: "退款受理错误率超过 2%"
```

三个面板的查询如下，粘进 Grafana 的 PromQL 输入框即可：

| 面板 | 查询 | 说明 |
| --- | --- | --- |
| 受理错误率 | `sum(rate(refund_requests_total{status_class="5xx"}[5m])) / sum(rate(refund_requests_total[5m]))` | 与告警同源 |
| 受理延迟 p95 | `histogram_quantile(0.95, sum by (le) (rate(refund_request_duration_seconds_bucket[5m])))` | 桶边界要覆盖 2 秒 |
| 队列深度 | `refund_queue_depth` | 饱和信号，配 `for: 10m` |

### 预期结果

`curl` 输出 12 行样本：counter 四条、gauge 一条、桶七条；`le` 从 `0.05` 递增到 `+Inf`，计数单调不减且 `+Inf` 等于总请求数。基数脚本输出 `[OK] 所有标签值都是低基数枚举，可以安全写入长期存储` 并返回 0；把 `route` 换成带订单号的值再抓，会输出 `[RISK] ... 看起来是具体 ID` 并返回 1。三个面板分别显示错误率、p95 与队列深度。

### 验证方法

- `curl -s http://127.0.0.1:9464/metrics | grep -c '^refund_'` 应得 `12`。
- `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9464/debug` 应为 `404`，说明没有多余调试路径。
- 把 `b.txt` 某个桶改小再跑，应打印 `[CHECK] ...：失败`，这是打点写错的信号。
- 可选步骤中 `/alerts` 里该告警满 10 分钟后由 `pending` 变 `firing`。

### 清理方法

`Ctrl-C` 结束服务，删除 `refund_metrics.py`、`label_audit.py`、`sli_calc.py`、`a.txt`、`b.txt`；可选步骤执行 `docker compose down -v`。`lsof -i :9464` 无输出即端口已释放。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| p95 是直线，故障时也不动 | 对 `_bucket` 求平均，或对 summary 分位做 `avg` | 看有没有 `histogram_quantile` 与 `sum by (le)` | 改成 `histogram_quantile(0.95, sum by (le) (rate(..._bucket[5m])))` |
| 重启后错误率出现负值或尖刺 | 直接对 counter 原始值做减法 | 对同一序列查 `resets()`，比对发布记录 | 统一用 `rate()`、`increase()` |
| 内存与磁盘持续上涨、查询变慢 | 标签写了订单号、用户 ID、原始 URL | `count by (route) (refund_requests_total)` 看取值种类 | 路由模板化成 `/refunds/{id}` |
| 服务全挂了却没有告警 | 只对业务指标配规则，没监控 `up` | 查 `up{job="refund-service"} == 0` 有无规则 | 增加 `up` 与 `absent()` 告警，抓取失败进首屏 |
| 面板显示 0.3%，事故却不断 | 分母被过滤或采样，与告警窗口不一致 | 对比面板查询与规则表达式 | 面板改读 recording rule |
| trace 只有入口一个 span | 出站与消息生产没注入 `traceparent` | 比对响应与下游的 `trace_id` | 在客户端与生产端注入，消费端恢复上下文 |

## 安全与生产注意事项

**<u>不要把手机号、卡号、订单号、令牌写进指标标签、span 属性或 `/metrics` 路径。</u>** 这些端点在内网明文暴露且不鉴权，敏感值会随抓取扩散到长期存储、备份和截图。缓解三条：标签只用枚举值；Collector 的 `attributes` 处理器删除未知属性并哈希必要标识；端口只绑内网地址并加网络策略。

**<u>不要把 OTLP 接收端和 Grafana 暴露在公网，或与业务域名复用入口。</u>** OTLP 默认无认证，能连上的人都能写入伪造指标，让真实告警被抑制或误触发；Grafana 暴露等于公开拓扑与业务量。缓解：Collector 前置 mTLS、按租户拆接收端、Grafana 走 SSO 与最小权限。

## 本课总结

- **三类信号分工不同**：指标判断是否越界，追踪定位慢在哪一跳，日志解释错误。
- **OpenTelemetry 不是后端**：API 打点、SDK 导出、Collector 分流。
- **四类指标各有边界**：counter 用 `rate`、gauge 看瞬时值、histogram 用 `histogram_quantile` 配 `sum by (le)`，分位不可跨实例平均。
- **告警靠持续性判断，成本由基数决定**：`for` 挡住抖动，模板化路由与属性白名单压住成本与风险。

## 思考题

客服希望“每笔慢下来的退款都能立刻看完整调用链”，有人提议把 trace 采样率从 10% 提到 100%、保留 30 天。请从 SLO、成本、采样策略、数据敏感性四方面分析，给出替代方案与判断依据。

参考思路：先确认“每一笔”是否真是需求——多数场景是“出错或超时的请求必须可查”，对应尾部采样而非全量头部采样。成本按 span 数估：全量把存储与 Collector 内存放大十倍，保留 30 天让成本线性增长。敏感性上，全量保存会让订单号、金额、地址长期留存，要先做属性白名单与脱敏。用复盘数据回答：过去三个月靠现有采样找到根因的比例是多少。

## 小测

1. 判断：histogram 每个桶记录的是落在该区间内的独立计数，对还是错？
2. “退款队列当前等待笔数”该用哪种类型？  
   A. counter　B. gauge　C. histogram　D. summary
3. `rate(refund_requests_total{status_class="5xx"}[5m])` 的返回值是？  
   A. 5 分钟错误总数　B. 每秒错误数　C. 当前累计错误数　D. 错误占比
4. 简答：为什么不能把三个实例的 p95 求平均当作整体 p95？
5. 场景题：告警说“退款变慢”，首屏 p95 平稳，日志里 500 在增多。你会先看哪三个面板，为什么？

## 答案与解析

1. **错。** 桶是累计值，`le="0.5"` 包含所有不超过 0.5 秒的请求，必须先按 `le` 求和再差分；当成独立计数会得到矛盾的直方图，分位偏小。
2. **B。** 队列深度可增可减，重启后不该延续旧值。A 只增不减，表达深度会永不下降；C 表达分布而非瞬时；D 在客户端算分位，可聚合性差。
3. **B。** `rate` 返回每秒平均增长率，`[5m]` 只决定取哪些样本。A 是 `increase` 语义；C 是读原始 counter；D 还须再除总速率。
4. 分位数不可加：整体分布不是各实例分布的算术组合，请求量与长尾位置不同时平均会系统性低估。正确做法是按 `le` 求和后用 `histogram_quantile` 重算。
5. 参考方向：先按 `route` 拆延迟，看是否只有某条路径变慢；再按 `payment_provider` 分组看错误率与延迟，判断是否支付商抖动；再看队列深度、连接池、重试是否被放大。

### 动手实验参考

输出随随机流量变化，结构须满足：counter 四条、gauge 一条、桶七条且 `+Inf` 等于总请求数，`le` 严格递增，`[SLI]` 分母等于各 `status_class` 增量之和。把 `b.txt` 某桶改小后必须报 `失败`，这是检查工具是否真在检查的对照。基数脚本在 `route="/api/v1/refunds/{id}"` 时输出 `[OK]`，换成带订单号的值后输出 `[RISK]`。

## 延伸阅读与下一课

- OpenTelemetry 官方文档：[Signals](https://opentelemetry.io/docs/concepts/signals/)、[Collector](https://opentelemetry.io/docs/collector/)。
- W3C 标准：[Trace Context](https://www.w3.org/TR/trace-context/)。
- Prometheus 官方文档：[Metric types](https://prometheus.io/docs/concepts/metric_types/)、[Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)、[Exposition formats](https://prometheus.io/docs/instrumenting/exposition_formats/)。
- Grafana 官方文档：[Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)。
- Google SRE Book：[Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[Correlation ID 与请求链路](02-correlation-id-and-request-tracing.md)。
- 下一课：[SLI、SLO、SLA 与错误预算](04-sli-slo-sla-and-error-budget.md)。
