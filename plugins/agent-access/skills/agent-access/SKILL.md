---
name: agent-access
license: MIT
github: https://github.com/r266-tech/agent-access
description:
  Agent Access 是通用 agent 薄访问层：给 Claude Code、Codex、Cursor、OpenClaw、Hermes 等 agent 把网站、GUI 软件、本地 app、API 和重复联网流程路由到 agent-native CLI、结构化检索、浏览器/CDP 兜底、Computer Use 或显式贡献草稿。
metadata:
  author: Agent Access 贡献者
  version: "0.2.4"
---

# Agent Access Skill

Agent Access 是通用薄访问层，不替代模型判断。它面向 Claude Code、Codex、Cursor、OpenClaw、Hermes 和自定义本地 agent；Codex 插件只是一个分发 adapter。它负责提醒 agent 先发现可用能力，再选择最合适的表面：现有 CLI、可生成或可优化的 CLI、结构化 API、浏览器/CDP 兜底、Computer Use，以及必要 reference。

## L0 Contract

1. 先明确目标：用户要信息、证据、页面状态、本地软件动作，还是外部动作。
2. 先发现能力：已登记 agent CLI、本地命令、结构化 API、搜索/抓取工具、浏览器兜底和 Computer Use。
3. 稳定、可复用的任务优先走 CLI 或 API。
4. 浏览器/GUI 自动化是开荒和兜底，不是长期默认路径。
5. 开荒时同步沉淀：稳定 endpoint、schema、文件格式和操作序列进 CLI；浏览器或 GUI 特有陷阱进 focused reference。
6. 用完 CLI 后回看摩擦：能安全当场改就改，并重新跑真实 flow；不能靠 CLI 合理覆盖的，写成 focused reference 或贡献草稿。
7. 贡献外发必须显式。经验、站点 pattern 和 CLI patch 默认只留在本地，只有用户审核并同意后才提交。
8. 登录态留在本机。凭据、cookie、token、验证码、浏览器 session、本地数据库和账号标识不得进入 prompt 外的普通日志、memory、公开仓库或贡献草稿。
9. 升级要可控：Agent Access 核心可通过 git/npm/插件包更新；Codex 插件通过 Codex marketplace 升级；companion CLI 通过 registry 声明的 update 命令升级。

## Runtime Fit

- Claude Code：使用本 repo 的 CLI、registry、SKILL 和 references；不要把全部 reference 塞进常驻 prompt。
- Codex：可安装 `plugins/agent-access` 作为 Codex plugin，也可直接调用 `agent-access` CLI。
- Cursor / OpenClaw / Hermes / custom agents：把 Agent Access 当作 registry + CLI contract + thin instruction package；按需读取 reference。
- 任何 runtime 都应优先执行 `agent-access list/info/doctor` 或本地等价命令，而不是凭记忆猜某个站点是否已有工具。

## Initial Routes

```bash
command -v agent-access
agent-access list
agent-access info wechat-cli
agent-access info pmkt
agent-access info xyz
agent-access info douban
agent-access info dp
agent-access info xhs
agent-access run pmkt -- --help
```

首批公开 registry route：

- `wechat-cli` / `wx-cli`：读取本地微信/WeChat 数据；公开 release；不发消息，不控制 UI。
- `pmkt`：Polymarket 公开市场、事件、价格、订单簿研究；只读；插件内置。
- `xyz`：小宇宙 FM 读取；公开源码；登录态只留本机。
- `douban`：豆瓣电影读取、想看/看过/评分；浏览器 session 登录；写操作默认 dry-run，显式 apply 才执行；插件内置。
- `dp` / `dianping`：大众点评店铺和评价读取；浏览器/session 或 stdin cookie 导入；不导出 cookie；插件内置。
- `xhs`：小红书 / Rednote 读取；公开 PyPI 包；用户 session 留本机；写操作必须显式命令和用户确认。

`registry.json` 里的 `source_status` 说明 route 是否已有公开安装器、是否随插件内置，还是仅有公开契约、独立源码待发布。`agent-access list/info` 里的 `install.state` 是用户可用性的直接信号：`installable` 才能按 registry 安装或直接运行 bundled CLI；`contract-only` 只能当公开契约和贡献目标，不能假设用户机器已有可运行 CLI。`cli-manifest.json` 是 registry 的确定性发现索引；发布前必须通过 `agent-access check-manifest`，避免 route 静默消失。若用户配置了 `AGENT_ACCESS_REGISTRY` 或 `~/.agent-access/registry*.json` 私有覆盖，先跑 `agent-access audit-overlay` 看清本地条目是否遮蔽了打包 route。

## Capability Discovery

```bash
command -v agent-access
agent-access list
agent-access info <name>
agent-access install <name>        # dry-run plan
agent-access install <name> --run  # 只有明确要执行时才加
agent-access update <name>         # dry-run plan
agent-access doctor <name> --run
agent-access check-manifest
agent-access audit-overlay

# 如果 bin 不在 PATH，从当前 skill 目录运行：
node scripts/agent-access.mjs list
```

热路由不清楚时读 `references/tool-routing.md`。创建或系统性升级 CLI 前读 `references/cli-generation.md`。涉及登录、扫码、验证码、账号密码或 session 刷新时读 `references/auth-sessions.md`。准备外发贡献前读 `references/contribution-flow.md`。

## CLI Evolution Loop

- 输出稳定 JSON。
- 错误要可诊断，并给出可操作 next action。
- 返回 ID、URL、cursor、cache ref 等后续可读句柄。
- 分页、过滤、排序要可脚本化。
- 读写边界要清楚，写操作需要显式 flag。
- 声称 route ready 前要 dogfood 真实 agent flow。
- 优先改进 CLI，而不是长期累积浏览器点击 recipes。
- CLI 无法合理覆盖时，写 focused reference。

## Auth And Sessions

需要登录态时，优先使用 CLI 或 Agent Access 的 auth/session 设计，而不是让每个 CLI 随意散落 cookie。首次使用或过期时，agent 应能引导用户选择合适方式：

- QR code / 扫码登录；
- SMS 手机号 + 验证码；
- OAuth / device code；
- 用户已登录的浏览器 session；
- 账号密码写入本机安全存储。

任何凭据都只应进入用户本机安全存储或明确的本地私有状态；不要进入公开仓库、日志、PR、issue、memory 或贡献草稿。

## Swarm Governance

用户和 agent 可以发现更好的 selector、schema、CLI flag、site pattern 和恢复流程。Agent Access 应把这些变成本地显式草稿，先脱敏，再由维护者审核后合并。没有被动遥测，没有自动上传。

## Browser / GUI Fallback

只有判断 CLI/API 不覆盖当前任务后，才进入浏览器、CDP 或 GUI 兜底。浏览器控制必须由用户显式配置，不应由公开核心隐式启动。

进入浏览器兜底前，读 `references/cdp-api.md`；如果目标域名有用户安装的 site-pattern package，再读取对应站点经验。

## Source Discipline

- 核实类任务优先找一手来源：官网、官方公告、原始论文、原始页面、源码或官方文档。
- 搜索引擎和聚合平台是发现入口，不是最终证明。
- 工具能力和用法不猜：查官方文档、源码、`--help` 或本地 README。

## References

| 文件 | 何时读取 |
|------|----------|
| `references/tool-routing.md` | 热路由不够、需要完整能力边界 |
| `references/cli-generation.md` | 需要新建或系统性升级 agent-only CLI |
| `references/cli-registry.md` | 需要登记、发现、安装、打包 companion CLI |
| `references/auth-sessions.md` | 需要登录、扫码、验证码、账号密码、刷新 session、凭据存储 |
| `references/contribution-flow.md` | 需要把本地经验、CLI patch、site-pattern 显式贡献出去 |
| `references/cdp-api.md` | 已决定进入浏览器/CDP/GUI 兜底 |
