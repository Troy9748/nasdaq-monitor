# NASDAQ-100 Daily Monitor

一个以 NASDAQ-100（`^NDX`）为唯一标的的日线监控项目。它使用 FRED 发布、来源为 Nasdaq, Inc. 的 `NASDAQ100` 日收盘序列维护 1990 年以来的权威历史表，并用 Yahoo Finance 补充 FRED 尚未发布的最新交易日。项目同时跟踪 VXN、美国十年期国债收益率和 NASDAQ-100 成分股市场广度。

## 每日流程

1. 北京时间周二至周六 07:00 从仓库读取 FRED 历史基准，只用 Yahoo 补充最新收盘。
2. 北京时间每周一 06:00 从 FRED 全量校准 NASDAQ-100、VXN 和十年期美债历史，不发送邮件。
3. 每行记录 `Source` 和 `Is_Provisional`；FRED 为权威值，Yahoo 为待校准临时值。
4. 校验日期、价格、样本数、重复行和数据新鲜度；超过 7 天未更新时使任务失败并告警。
5. 计算趋势、动量、波动、回撤和当前成分股站上 EMA200 的比例。
6. DeepSeek/OpenAI 只基于提供的数据生成条件化风险框架，失败时退回规则分析。
7. 新交易日发送邮件并提交 CSV、网页 JSON 和分析结果；节假日不会重复发送。
8. 网页数据提交后由 GitHub 执行完整构建检查，本地 Codex 自动任务在 07:20 发布新版公开 Sites 页面。

## GitHub Secrets

- `MAIL_USERNAME`：Gmail 发件地址
- `MAIL_PASSWORD`：Gmail 应用专用密码
- `MAIL_RECEIVER`：收件地址
- `OPENAI_API_KEY`：可选；OpenAI 或 DeepSeek API key，不配置时使用规则分析

仓库变量 `OPENAI_MODEL` 用于覆盖默认模型 `gpt-5.4-mini`；使用兼容服务时再设置 `OPENAI_BASE_URL`。

设置 `OPENAI_API_KEY`：

1. 在 OpenAI 或 DeepSeek 控制台创建 API key，并立即复制保存。
2. 打开本仓库的 **Settings → Secrets and variables → Actions → New repository secret**。
3. Name 填 `OPENAI_API_KEY`，Secret 粘贴 API key，点击 **Add secret**。
4. 在 **Variables** 中新增 `OPENAI_MODEL`；DeepSeek 填 `deepseek-v4-flash`。
5. 使用 DeepSeek 时再新增变量或 Secret `OPENAI_BASE_URL`，值为 `https://api.deepseek.com`；工作流优先读取 Secret。
6. 到 **Actions → Daily NASDAQ-100 Check → Run workflow**，勾选“重新生成 AI 分析”后手动验证一次；该模式不发邮件。不要把 key 写进代码、CSV 或网页。

需要完整测试 DeepSeek、数据导出和邮件链路时，只勾选“强制完整分析并发送一封测试邮件”。两个手动选项同时勾选时，邮件测试优先。

## 本地运行

```bash
pip install -r requirements.txt
python monitor.py --no-email --force
python -m unittest discover -s tests
```

网页项目位于 `web/`，读取 `web/public/data/` 下的生成文件。

本地查看网页：

```bash
cd web
pnpm install
pnpm dev
```

打开终端提示的本地地址。顶部按钮切换 1/3/5/10 年或全历史，`对数` 用于比较长期复合增长；图表展示收盘、EMA50 与 EMA200，指标卡用于观察趋势、动量、波动率和回撤，底部可下载完整 CSV。

网页还展示：

- 最新值来自 FRED 还是 Yahoo 临时数据，以及 FRED 权威校准截止日；
- 数据新鲜度、VXN、十年期美债收益率和成分股市场广度；
- 历史回撤、RSI、波动率和多头/修复/防御状态时间轴；
- DeepSeek 条件化风险分析。网页代码或数据变更后，GitHub 会自动执行完整构建检查。
- 多头、修复和防御状态出现后的 20/60/120 日历史中位收益与正收益率；
- VXN、十年期美债和 NDX/VXN 60 日滚动相关性的历史联动；
- FRED 对 Yahoo 临时收盘的周度校准差异审计；
- 日常、注意、重要和故障四级提醒，以及最近状态切换事件。

公开网页：`https://ndx-signal-desk.lxh9748.chatgpt.site`。自动发布任务需要本机和 Codex 可运行；GitHub 上的数据更新与构建检查不依赖本机。

## 数据口径

- FRED 序列为 Nasdaq, Inc. 提供的 NASDAQ-100 每日收盘指数点位，是历史基准；Yahoo 临时行会在每周校准时被 FRED 覆盖。
- VXN 使用 FRED 的 `VXNCLS`，十年期美债使用 `DGS10`；最新未校准值可由 Yahoo 补充。
- 市场广度使用 Nasdaq 官方当前成分名单与成分股日线计算，只描述当前内部健康度，不用于历史回测，避免幸存者偏差。
- 日报以数据源返回的最新已落盘交易日为准，不使用脚本运行日冒充行情日期。
- AI 只能解释传入指标，不含新闻检索，只输出条件化风险管理框架，不构成投资建议。
