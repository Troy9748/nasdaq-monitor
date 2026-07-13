import type { Metadata } from "next";
import "./globals.css";

const siteUrl = "https://www.lxh9748.fun/nasdaq-monitor";
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const title = "NDX Signal Desk · NASDAQ-100 市场分析";
const description = "从 1990 年开始追踪 NASDAQ-100 趋势、收益、波动、回撤、市场环境与 AI 风险解读。";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title,
  description,
  icons: { icon: `${basePath}/favicon.svg` },
  openGraph: { title, description, images: [{ url: `${siteUrl}/og.png`, width: 1200, height: 630 }] },
  twitter: { card: "summary_large_image", title, description, images: [`${siteUrl}/og.png`] },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
