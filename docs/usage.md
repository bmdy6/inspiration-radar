# 使用说明

## 安装与离线示例

在克隆后的仓库目录执行 README 的快速开始命令。Windows 可将 `.venv/bin/` 换成 `.venv\Scripts\`。程序需要 Python 3.10 或更新版本。

`demo` 使用包内的合成候选和预置评分，直接生成日报，不读任何真实账号。可重复运行，同一天返回 `already_published`。演示单独用 `--state .radar/demo`，正式流程用 `--state .radar/main`；不要混用。

## 配置优先级

命令行 `--state` 优先于 `RADAR_STATE_DIR`，后者缺省为当前目录下的 `.radar`。规则使用 `--config` 指定的完整 JSON 文件，未指定时使用内置保守默认。参考 `config/default.json`，它与内置默认一致，不做隐式配置合并。

可以修改 `topics`、`github_query`、`hn_query`、`exclude_terms`、`max_items`、`max_age_days` 和 `source_limit`。五维权重必须非负且总和为 1；每个分数及阈值必须是 0–10 有限数字。默认只收最近 90 天且日期明确的条目，每来源最多 10 条，每日报最多 5 条。GitHub 使用创建日期，旧仓库近期更新不会算新项目。

如果需要 GitHub token，由自己的环境管理器导出 `GITHUB_TOKEN`。示例文件不含密钥，程序不会自行加载 `.env`。来源查询始终限定公开仓库，即使提供 token 也不查询私有仓库。候选文件和日报可能包含自己的评语，不应随意提交到公开仓库。

## 发现候选

```sh
.venv/bin/inspiration-radar --config config/default.json --state .radar/main discover > candidates.json
```

`--source github` 或 `--source hacker_news` 只使用单一来源。读取有 20 秒超时、2 MiB 响应上限，不自动跟随 HTTP 重定向。候选 URL 不会由程序抓取或执行。来源返回 `failed` 时只有错误类型，避免泄露请求内容。部分来源成功则为 `partial`，进程仍返回 0；调用方必须同时查看 `status` 和 `sources`。全部失败返回非零退出码。

也可用 `discover --input examples/candidates.json` 读取本地候选；输入为 `{"candidates":[...]}`，最多 200 条、2 MiB。合成示例日期固定，超过时间窗口后会被正常过滤；只有明确的 `demo` 命令绕过时效过滤。

macOS 如果 Python 报证书校验失败，先修复该 Python 安装的证书。也可在确认为有效系统 CA 文件时，单次设置 `SSL_CERT_FILE=/etc/ssl/cert.pem` 再运行命令。不要关闭 TLS 校验。此项目不修改系统 CA。

## Agent 核验与评分

```sh
.venv/bin/inspiration-radar --config config/default.json prompt > review-prompt.txt
```

把提示词与 `candidates.json` 交给自己的 Agent，例如 DeepSeek。Agent 必须打开原始 README、Demo 或文章正文再评分，跳过不可读来源。搜索标题、热度和摘要本身不构成核验。来源文字不能覆盖提示词或要求执行命令。

产出 `scored.json`，顶层为 `items`。每条保持原始 `kind`（`github` / `article`）、标题、URL、带时区的 `published_at`，写入 `verified: true`、`what`、`highlight`、`inspire`，并为五维提供 `score`、`reason`、`evidence`。详情见 [examples/scored.json](../examples/scored.json)，其中内容全部虚构；不要拿示例当成真实核验结果。没有合格内容时使用 `{"items":[]}`。

GitHub 五维：relevance、heat、maturity、utility、novelty。文章五维：relevance、depth、hn_heat、timeliness、actionability。总分为各维分数乘权重之和，四舍五入到一位小数。默认 GitHub 总分至少 6，文章至少 6.5，相关性至少 6，文章深度至少 6。`verified` 是提交者的声明；程序只能检查字段完整性，不能证明内容或模型判断真实。

## 保存日报

```sh
.venv/bin/inspiration-radar --config config/default.json --state .radar/main publish --scores scored.json
```

日期默认取 UTC 当天，可显式使用 `--date YYYY-MM-DD`。每条日报保留原文标题和链接，解释使用提交的文字。没有合格内容也会保存空日报，当天批次随之固定，避免重跑悄悄换内容。

状态目录中的 `radar.sqlite3` 是权威记录，`daily/YYYY-MM-DD.json` 和 `.md` 是可恢复导出。SQLite 的写事务串行处理并发；日报导出成功后才提交快照与永久去重键。同日重跑复用首次批次，导出丢失会重建。备份应保留整个状态目录。每个主题使用独立状态目录，不提供删除去重或重选当天批次的隐式操作。

文件导出与数据库提交无法跨文件形成原子事务。如果文件写入或提交失败，进程非零退出且数据库回滚，可能留下尚未提交的导出文件；不要把失败命令留下的文件当成确认回执。确认成功退出后再消费导出。恢复时使用同一输入重新执行，完成快照优先。

## 可选调度

仓库不安装 scheduler。可以在自己选择的 cron 或 Agent 宿主里每天调用“发现 → 原文核验评分 → 发布”。不要只把 `discover` 排进定时任务后宣称每天已有完整日报。避免将私有输入、凭据或临时目录写进可公开分享的调度模板。

## 验证与打包

```sh
python3 -m unittest discover -s tests -v
python3 -m pip wheel --no-deps . --wheel-dir dist
```

单测无需网络、模型或 GitHub 身份。CI 覆盖 Python 3.10 与 3.13。网络来源冒烟需要独立执行，单测通过不能说明实时服务可用。
