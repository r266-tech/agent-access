# Agent Access

Agent Access 是给 agent 用的 Codex 插件和薄 access layer。它帮助 agent 为网站、API、本地软件、GUI 流程和重复联网任务选择合适的能力表面：优先 CLI / 结构化 API，必要时再进入浏览器、CDP 或 Computer Use。

目标是把外部网站、本地软件和网页流程打包成 agent 友好的 CLI，并在真实使用中持续进化。Agent Access 自身保持很薄：负责路由、说明、安装、升级、审计和贡献流程；具体站点和软件能力由 companion CLI 承担。

## 核心原则

- 默认 skill 要薄，按需读取 reference。
- 稳定、可复用的流程优先做成 agent-native CLI 或结构化 API。
- 浏览器/CDP/Computer Use 是开荒和兜底，不是长期默认路径。
- 用完 CLI 后要回看摩擦：能安全修就修，不能修就沉淀 focused reference。
- 登录态和用户数据只留在用户本机。
- 蜂群贡献必须显式、脱敏、经过维护者审核；不做被动遥测。
- 不上传使用经验、日志、截图、cookie、token、账号标识、本地路径或浏览器/session 材料，除非用户明确审核并同意。

## 架构

Agent Access 分四层：

1. 薄 Codex 插件：skill、registry、references、安装/升级 helper、贡献流程。
2. Companion CLIs：面向具体网站和软件的命令行能力。
3. 用户本地状态：凭据、cookie、浏览器 session、API key、本地数据库、缓存和私有 overlay。它们只存在于用户机器上。
4. 维护者上游：可公开的 registry 变更、CLI release、reference 和测试。

公开 registry 可以描述登录方式、安装方式和升级命令，但不能包含任何用户凭据、cookie、token、账号标识、浏览器 dump 或私有路径。

## 首批 CLI 包

首批公开 registry 包含：

| 目标 | 命令 | 状态 | 说明 |
| --- | --- | --- | --- |
| 微信 / WeChat 本地数据 | `wechat-cli` | 公开 release | 只读本地微信数据；不发消息，不控制 UI。 |
| Polymarket | `pmkt` | 公开契约，独立源码待发布 | 只读市场、事件、价格、订单簿等公开数据。 |
| 小宇宙 | `xyz` | 公开源码 | 只读订阅、节目、转录、搜索和历史。 |
| 豆瓣电影 | `douban` | 公开契约，独立源码待发布 | 浏览器 session 登录；标记/评分默认 dry-run，显式 apply 才写。 |
| 大众点评 | `dp` / `dianping` | 公开契约，独立源码待发布 | 浏览器/session 或 stdin cookie 导入；不导出 cookie。 |
| 小红书 / Rednote | `xhs` | 公开契约，独立源码待发布 | 用户本地 session；任何写操作都必须显式命令和用户确认。 |

`registry.json` 里的 `source_status` 是权威状态。一个 route 可以先作为公开契约存在，但 `agent-access install <name>` 不能假装已有安装器。

## 快速开始

```bash
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs list
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs info wechat-cli
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs install wechat-cli
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs doctor wechat-cli --run
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs audit-public .
```

`install` 和 `update` 默认只输出 dry-run 计划。只有确定要在本机执行时才加 `--run`。

## 在 Codex App 安装

从 GitHub 安装：

```bash
codex plugin marketplace add r266-tech/agent-access --ref main
codex plugin add agent-access --marketplace agent-access
```

从本地 checkout 安装：

```bash
codex plugin marketplace add .
codex plugin add agent-access --marketplace agent-access
```

维护者发布新的 registry、skill 或 reference 后，用户升级：

```bash
codex plugin marketplace upgrade agent-access
codex plugin add agent-access --marketplace agent-access
```

Companion CLI 通过 registry 里的升级命令更新，例如：

```bash
agent-access update wechat-cli
agent-access update wechat-cli --run
```

可以用 `AGENT_ACCESS_REGISTRY` 指向自己的私有或实验 registry。这个包也声明了 `agent-access` bin，供安装 package bin 的本地开发环境使用。

## Companion CLI 契约

推荐 companion CLI 提供：

- 面向机器稳定的 JSON stdout；
- 确定性的退出码；
- 可用的 `--help`，最好还有 `doctor`；
- 可后续读取的 ID、URL、cursor、cache ref 等句柄；
- 可脚本化的分页、过滤、排序；
- 清晰的读写边界，写操作需要显式 flag；
- 本地化 auth/session 管理；
- 失败时有可操作的 `error.next_action`。

## 浏览器 / CDP 边界

浏览器自动化是可选能力，必须由用户显式配置。公开核心不默认暴露浏览器控制服务。若实现浏览器 adapter，必须要求显式启动、只绑定 localhost、本地鉴权、能力分级，并说明站点条款和账号风险。

## License

MIT.
