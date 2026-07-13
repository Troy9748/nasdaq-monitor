# NDX Signal Desk

NASDAQ-100 历史与每日风险分析仪表盘。页面读取 `public/data/` 中由仓库根目录 `monitor.py` 生成的静态 JSON 和 CSV，因此不需要数据库或浏览器端密钥。

```bash
pnpm install
pnpm run dev
pnpm run build
```

主要界面位于 `app/page.tsx`，全局样式位于 `app/globals.css`。生产数据应通过根目录监控脚本更新，不要手工编辑。
