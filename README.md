# NASDAQ-100 Daily Monitor

一个以 NASDAQ-100（`^NDX`）为唯一标的的日线监控项目。它使用 FRED 发布、来源为 Nasdaq, Inc. 的 `NASDAQ100` 日收盘序列维护 1990 年以来的权威历史表，并用 Yahoo Finance 补充 FRED 尚未发布的最新交易日。项目计算趋势、动量与风险指标，在新交易日出现时发送邮件，并为网页仪表盘生成数据。

## 每日流程

1. 北京时间周二至周六 07:00（UTC 周一至周五 23:00）下载 FRED 历史，并从 Yahoo Finance 补充最新收盘。
2. 校验日期、价格、样本数与重复行。
3. 只有行情日期较 CSV 更新时才继续，节假日不会重复发送。
4. 计算 EMA20/50/200、SMA200、RSI14、20 日年化波动率、52 周高点距离和历史高点回撤。
5. 如已配置 OpenAI 兼容 API，则生成受指标约束的中文分析；失败时自动退回规则分析。
6. 发送邮件并提交 CSV、网页 JSON 和分析结果。

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

## 数据口径

- FRED 序列为 Nasdaq, Inc. 提供的 NASDAQ-100 每日收盘指数点位，是历史基准；Yahoo Finance 只补充日期晚于 FRED 最新日期的数据，不覆盖 FRED。
- 日报以数据源返回的最新已落盘交易日为准，不使用脚本运行日冒充行情日期。
- AI 只能解释传入指标，不含新闻检索，输出不构成投资建议。
