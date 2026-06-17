# Agent Access 给 Agent 的入口

Agent Access 是面向中文开发者和中文用户的通用 agent 薄访问层。Claude Code、Codex、
Cursor、OpenClaw、Hermes 或自定义本地 agent 需要访问网站、App、API、本地软件、
登录态页面或重复联网流程时，优先按这里的契约路由。

## Runtime 契约

1. 优先使用已登记的 companion CLI 和结构化 API。
2. 只有 CLI/API 覆盖不了任务时，才进入浏览器、CDP 或 GUI 自动化。
3. 稳定发现要沉淀成 CLI、registry 条目或 focused reference。
4. 凭据、cookie、浏览器 profile、token、账号 ID、原始日志、HAR、截图和私有路径
   不得进入公开输出。
5. Codex 插件文件只是一个 adapter，不是项目边界。

## 首选命令

```bash
agent-access list
agent-access info <target>
agent-access contract --target <target-or-url> --task "<task>"
agent-access verify <target>
agent-access install <target>
agent-access doctor <target> --run
agent-access check-manifest
agent-access audit-overlay
```

`install` 和 `update` 默认只输出 dry-run 计划。只有用户明确要修改本机环境时才加
`--run`。

装插件后自带的是核心 `agent-access` CLI、registry 和 `cli-manifest.json` 发现索引。站点/软件 companion CLI
按需发现、安装、验证；如果没装，先用 `info/install/verify` 给用户和 agent 明确下一步。
如果用户配置了私有 registry/overlay，先用 `audit-overlay` 判断它是否遮蔽了打包 route。

如果 `agent-access` 不在 PATH，直接运行 helper：

```bash
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs list
```

## 关键文件

- `plugins/agent-access/skills/agent-access/registry.json`：公开 companion CLI
  registry。
- `plugins/agent-access/skills/agent-access/cli-manifest.json`：由 registry 生成的
  发现索引；发布前用 `check-manifest` 防止 route 静默消失。
- `plugins/agent-access/skills/agent-access/SKILL.md`：薄路由 skill。
- `plugins/agent-access/skills/agent-access/references/source-contracts.md`：route
  source strategy 和稳定性契约。
- `plugins/agent-access/skills/agent-access/references/cli-errors.md`：CLI 错误和
  exit code 契约。
- `plugins/agent-access/skills/agent-access/references/cli-generation.md`：如何把重复
  网站/App 流程沉淀成 agent-native CLI。
- `plugins/agent-access/skills/agent-access/references/auth-sessions.md`：本地 auth/session
  边界。
- `plugins/agent-access/skills/agent-access/references/contribution-flow.md`：脱敏贡献流程。

## 公开仓库保护

发布前运行：

```bash
npm test
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs audit-public .
```
