[IMPORTANT: You are running as a scheduled cron job. DELIVERY: Your final response will be automatically delivered to the user if it contains content. If there is genuinely nothing new to report, respond with exactly "[SILENT]" and nothing else. Do not use send_message.]

你是 `IBeanCN/a-stock-data-skillpack` 的每周上游同步任务。工作目录必须是：

`/home/agent/.hermes/workspace/a-stock-data`

每周一 00:00 运行。目标：检查上游主仓库 `https://github.com/simonlin1212/a-stock-data` 是否发布了新的最高版本 tag。我们的版本号必须始终与上游最高 tag 保持一致。

## 必做流程

1. 进入工作目录并确认仓库干净：
   - `git status --short`
   - 如果不干净，停止，输出错误报告，不要覆盖未知改动。

2. 执行预检脚本：
   - `python3 scripts/check_upstream_release.py`
   - 如果 stdout 为空，最终回复必须只输出 `[SILENT]`。
   - 如果 stdout 是 JSON，解析其中的 `tag`、`previous_released_tag`、`unreleased_upstream_tags_after_previous`。

3. 拉取上游 diff：
   - 确认或新增 remote：`upstream=https://github.com/simonlin1212/a-stock-data.git`
   - `git fetch upstream --tags`
   - `git fetch origin --tags`
   - 使用 `previous_released_tag..tag` 获取上游变更；如果 `previous_released_tag` 为空，则比较上游上一个 tag 到 `tag`。
   - 保存一份机器可读/人工可读 diff 摘要到临时文件，例如 `/tmp/a-stock-data-upstream-${tag}-diff.md`。

4. 同步策略：
   - 不要把上游单文件 `SKILL.md` 直接覆盖到本仓库。
   - 需要吸收上游新增/修复的端点、数据源、字段、限流/备用源策略。
   - 保持本仓库的渐进式披露结构：
     - `SKILL.md` 轻量路由器。
     - `scripts/a_stock_client.py` 集中实现。
     - `references/*.md` 只放端点说明、字段语义、估值公式、工作流、FAQ/故障处理。
   - 保留 README 中对上游项目和 Apache License 2.0 的致谢与协议说明。
   - 不要恢复 `.github/FUNDING.yml`、捐赠图片或 Donate/Sponsor 文案。

5. 修改完成后必须验证：
   - `python3 -m py_compile scripts/a_stock_client.py scripts/validate_env.py scripts/smoke_test_endpoints.py scripts/check_upstream_release.py`
   - `python3 scripts/smoke_test_endpoints.py`
   - 搜索确认没有恢复捐赠/赞助内容：`donate|sponsor|funding|打赏|赞助|buy me|wechat|bmc|捐赠|ifdian`
   - `git diff --check`

6. 如果验证失败：
   - 不要提交、不要 tag、不要 Release。
   - 输出失败原因、已做改动、需要人工处理的位置。

7. 如果验证通过且有实际改动：
   - 提交：`chore: sync upstream ${tag}`
   - 推送到 `origin main`。
   - 在当前提交上创建/移动本仓库 tag `${tag}`，并推送 tag。
   - 创建 GitHub Release，版本号和 title 都是 `${tag}`。

8. 如果上游有新 tag，但检查后无需代码改动：
   - 仍需确认当前 main 代表该版本兼容状态。
   - 可创建空提交 `chore: mark upstream ${tag} compatibility`，通过同样验证后 tag + Release。

## Release 内容格式

Release body 必须分为中文和英文两部分，中文在上，英文在下。推荐结构：

```markdown
## 中文

### 上游版本
- 同步上游 `simonlin1212/a-stock-data` `${tag}`。

### 本 fork 变更
- 说明本次吸收的端点、数据源、字段、修复或文档变化。

### 验证
- 列出实际通过的命令。

### 致谢与许可
- 本项目 fork 并改造自 `simonlin1212/a-stock-data`，感谢 Simon Lin 和原项目社区。
- 继续遵守 Apache License 2.0。

## English

### Upstream Version
- Synced upstream `simonlin1212/a-stock-data` `${tag}`.

### Changes in This Fork
- Summarize absorbed endpoints, data sources, fields, fixes, or documentation updates.

### Verification
- List commands that actually passed.

### Attribution and License
- Forked and adapted from `simonlin1212/a-stock-data`. Thanks to Simon Lin and the original community.
- Continues to follow Apache License 2.0.
```

## 最终回复

- 无新版本：只输出 `[SILENT]`。
- 有新版本且发布成功：用中文简短报告 tag、提交、Release URL、验证命令。
- 失败：用中文明确报告失败点，不要伪造成功。
