# 贡献指南

Agent Access 欢迎有意图、可审查的贡献：CLI 契约改进、registry 条目、focused references、文档、测试和安全 adapter。

贡献前请先：

1. 运行公开审计：

   ```bash
   node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs audit-public .
   ```

2. 移除所有 secret 和私有标识。
3. 提供来源证据和复现步骤。
4. 保持默认 skill 很薄，细节放进 references。
5. CLI 行为变更需要真实 dogfood 输出或测试。

不要提交原始运行日志、截图、cookie、token、HAR 文件、个人浏览历史、私有公司 URL，或会暴露用户身份的本地路径。

## 蜂群贡献原则

使用者可以把新站点经验、CLI 摩擦、site pattern 和修复建议整理成 contribution draft。但 draft 默认只在本地，必须先脱敏、人工审核，再由维护者决定是否合并。Agent Access 不做被动遥测，不自动上传用户经验。
