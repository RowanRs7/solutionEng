---
title: Web 与网络
slug: web-and-network-overview
module: traditional-solutions
stage: design
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - discovery-and-requirements-overview
outcomes:
  - 画出一次 Web 请求从客户端到服务端的分层路径，并指出每层的排障入口
  - 解读 HTTP 请求、响应、头部、Cookie 与缓存策略，并判断跨域与登录态失效的成因
  - 用 curl 与既有日志定位一次集成故障，并给出带验证步骤的修复方案
last_reviewed: 2026-10-19
---

# Web 与网络

## 单元目标

学完本单元，你能把一次"页面打不开""接口 500""登录后又被踢出"的模糊报障，还原成客户端、网络、服务端三段可验证的链路。你会读懂 HTTP 报文与状态码，判断 TLS、Cookie、缓存、跨域等机制在何处生效，并用 curl 与诊断工具取证。最终你能为一项集成需求写出可被开发和运维共同执行的网络方案要点。

## 学习路线

预计学习时间为 **7–9 小时**。课程按以下顺序学习，每篇都配有练习：

1. [Web 架构与分层](01-web-architecture-and-layers.md)：客户端、服务端与网络分层，先建立全局地图。
2. [TCP/IP、DNS 与防火墙](02-tcp-ip-dns-and-firewall.md)：连接为何连不上，以及先查 DNS 还是先查端口。
3. [HTTP 请求与响应](03-http-request-response.md)：方法、报文结构与状态码的语义。
4. [Header、Cookie 与缓存](04-headers-cookies-and-caching.md)：会话如何维持、缓存为何命中失败。
5. [HTTPS、TLS 与证书](05-https-tls-and-certificates.md)：握手过程、证书校验与常见告警。
6. [JSON、XML、CSV 与字符编码](06-json-xml-and-encoding.md)：报文格式与乱码问题的边界。
7. [CORS、CSRF 与浏览器安全](07-cors-csrf-and-browser-security.md)：跨域预检、同源策略与请求伪造防护。
8. [curl 与网络诊断](08-curl-and-network-diagnostics.md)：用命令行复现问题并留存证据。
9. [反向代理、负载均衡与 CDN](09-reverse-proxy-load-balancer-cdn.md)：流量入口的职责划分与常见错配。
10. [Web 与网络阶段综合测评](10-stage-assessment.md)：检验本单元掌握程度。

## 贯穿场景

晴空商城的退款流程要同时对接支付网关、订单服务与客服工单。用户提交退款后，客服看到"请求超时"，支付方看到"回调未达"，订单状态却停在"退款中"。本单元从网络侧面拆解这一问题：请求在哪一层被截断，DNS 与防火墙是否放行，代理是否正确透传 Header，TLS 证书是否过期，回调地址是否被跨域与 Cookie 策略挡住，以及如何用 curl 逐跳验证。

## 必交成果

- 一张端到端请求路径图，标注每层的排障命令与观测点。
- 一份退款接口的 HTTP 报文分析，含方法、状态码、关键 Header 与缓存策略判断。
- 一份 curl 复现脚本与诊断记录，证明故障发生在哪一跳。
- 一份跨域与登录态问题的成因说明及修复建议。
- 一份流量入口方案说明，涵盖反向代理、负载均衡与 CDN 的分工。

## 完成规则

先完成九篇课程及其中的练习，再进入阶段测评。测评达到 **80 分**视为掌握；**60–79 分**应按复习路线回到对应课程补课并重做练习；**低于 60 分**需重新完成核心练习后再测一次。

返回[传统解决方案模块](../00-overview.md)。
