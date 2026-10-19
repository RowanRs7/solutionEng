---
title: 身份、权限与安全
slug: identity-and-security-overview
module: traditional-solutions
stage: design
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - api-and-integration-overview
outcomes:
  - 画出目标链路的身份流转图，标注信任边界与凭据传递路径
  - 为给定业务场景选出认证、令牌与授权模型，并写明取舍理由
  - 给出权限矩阵、密钥管理方案与数据分级清单
last_reviewed: 2026-10-19
---

# 身份、权限与安全

## 单元目标

本单元帮你在设计阶段回答一个绕不开的问题：**谁在什么条件下能对什么数据做什么事**。你会从认证、授权与审计的基本模型出发，掌握 JWT、OAuth 2.0 与 OIDC、SSO 以及 RBAC/ABAC 的适用边界，并把凭据管理、数据分级与攻击面防护纳入方案。学完之后，你能为一条真实业务链路画出身份流转图与权限矩阵，并对每个安全决策给出可评审的取舍理由。

## 学习路线

预计学习时间为 **8–10 小时**。课程按顺序推进，每课先读完正文、完成练习，再进入下一课：

1. [认证、授权与审计](01-authentication-authorization-and-audit.md)：认证、授权与审计，分清三者的职责边界。
2. [密码、MFA、Session 与 API Key](02-passwords-mfa-session-and-apikeys.md)：密码、MFA、Session 与 API Key 的存储与生命周期。
3. [JWT 结构、签发与校验](03-jwt-structure-and-validation.md)：JWT 结构、签发与校验，识别常见校验漏洞。
4. [OAuth 2.0 授权流程与 PKCE](04-oauth2-flows-and-pkce.md)：OAuth 2.0 授权流程与 PKCE，按客户端类型选流程。
5. [OpenID Connect 与身份令牌](05-openid-connect-and-id-tokens.md)：OpenID Connect 与身份令牌，把认证叠加到 OAuth 之上。
6. [SSO、SAML 与企业身份接入](06-sso-saml-and-enterprise-identity.md)：SSO、SAML 与企业身份接入，对接客户方 IdP。
7. [RBAC、ABAC 与多租户权限](07-rbac-abac-and-multi-tenant-permissions.md)：RBAC、ABAC 与多租户权限，设计可扩展的授权模型。
8. [Secret、证书与密钥管理](08-secrets-and-key-management.md)：Secret、证书与密钥管理，落地轮换与最小暴露。
9. [常见 Web/API 攻击与安全设计](09-web-api-attacks-and-secure-design.md)：常见 Web/API 攻击与对应的安全设计对策。
10. [数据分类、脱敏与合规基础](10-data-classification-encryption-and-compliance.md)：数据分类、脱敏与合规基础，界定可存、可传、可展示。
11. [身份与安全阶段综合测评](11-stage-assessment.md)：身份与安全阶段综合测评。

## 贯穿场景

晴空商城的退款一直由客服手工处理：客服后台要调用订单服务查询、调用支付渠道发起退款，还要留痕以备对账与审计。这条链路暴露了本单元的每个侧面——客服与系统之间如何认证、服务之间用什么凭据、退款接口对第三方开放到什么粒度、哪些角色可以批准超额退款、密钥泄露会波及哪些数据。你会围绕同一条退款链路，逐步补齐身份、令牌、授权与数据保护的设计。

## 必交成果

- 退款链路的身份流转图，标注信任边界与凭据传递路径。
- 认证方式与 MFA、会话策略的选型对比表，含放弃项与理由。
- 令牌方案说明：JWT 声明设计、校验清单与过期/撤销策略。
- 权限矩阵与多租户隔离规则，覆盖客服、财务、运营等角色。
- Secret 与密钥的存放、轮换、应急轮转方案。
- 数据分级与脱敏清单，附威胁—对策对照。

## 完成规则

先完成十篇课程及其中的练习，再进入 `11-stage-assessment.md`。阶段测评达到 **80 分**视为掌握；**60–79 分**按测评给出的复习路线回到对应课程补课，补完后再测一次；**低于 60 分**需重新完成核心练习，从认证与授权基础重新梳理，再申请测评。

返回[传统解决方案模块](../00-overview.md)。
