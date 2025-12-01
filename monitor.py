import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
from datetime import datetime

# --- 配置区域 ---
# 股票代码: 纳斯达克100指数用 ^NDX，或者用 ETF 代码 QQQ
SYMBOL = "^NDX" 
# 缓冲百分比 (3%)
BUFFER_PERCENT = 0.03 

# --- 邮件发送函数 ---
def send_email(subject, content):
    sender = os.environ["MAIL_USERNAME"]
    password = os.environ["MAIL_PASSWORD"]
    receiver = os.environ["MAIL_RECEIVER"]
    
    # SMTP 服务器配置 (以 Gmail 为例，如果是 QQ 邮箱请改为 smtp.qq.com)
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = Header("纳指监控机器人", 'utf-8')
    message['To'] = Header("Master", 'utf-8')
    message['Subject'] = Header(subject, 'utf-8')
    
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, [receiver], message.as_string())
        server.quit()
        print("邮件发送成功！")
    except Exception as e:
        print(f"邮件发送失败: {e}")

# --- 主逻辑 ---
def job():
    print(f"开始获取 {SYMBOL} 数据...")
    # 获取过去 400 天的数据以确保 EMA200 计算准确
    df = yf.download(SYMBOL, period="2y", interval="1d", progress=False)
    
    if len(df) < 200:
        print("数据不足，无法计算")
        return

    # 计算 EMA200
    # 注意：pandas 的 ewm span=200 对应 TradingView 的 EMA 200
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    # 计算带缓冲的警戒线
    # 比如我们监控 EMA200 上方 3% 的线
    df['Upper_Buffer'] = df['EMA200'] * (1 + BUFFER_PERCENT)
    # 也可以监控下方 3% 的线 (如果你想低吸或止损)
    df['Lower_Buffer'] = df['EMA200'] * (1 - BUFFER_PERCENT)

    # 获取最近两天的数据 (今天和昨天)
    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    
    price_now = float(today['Close'])
    upper_line = float(today['Upper_Buffer'])
    lower_line = float(today['Lower_Buffer'])
    
    print(f"日期: {today.name.date()}")
    print(f"收盘价: {price_now:.2f}")
    print(f"EMA200: {float(today['EMA200']):.2f}")
    print(f"上轨 (+3%): {upper_line:.2f}")
    print(f"下轨 (-3%): {lower_line:.2f}")

    # --- 警报逻辑 1: 向上突破 EMA200 + 3% (强势买入信号) ---
    # 逻辑：昨天在线下，今天在线上
    if yesterday['Close'] < yesterday['Upper_Buffer'] and price_now > upper_line:
        msg = f"【警报】纳斯达克指数刚刚突破 EMA200 + 3% 缓冲线！\n\n当前价格: {price_now:.2f}\n警戒线: {upper_line:.2f}\n\n趋势可能进入加速上涨阶段。"
        send_email("🚀 买入信号：纳指突破缓冲带", msg)

    # --- 警报逻辑 2: 向下跌破 EMA200 + 3% (可能只是回调) ---
    elif yesterday['Close'] > yesterday['Upper_Buffer'] and price_now < upper_line:
         msg = f"【提示】纳斯达克指数跌回 EMA200 + 3% 缓冲线下方。\n\n当前价格: {price_now:.2f}\n警戒线: {upper_line:.2f}"
         send_email("📉 提示：纳指回调", msg)
    
    # --- 你可以添加更多逻辑，比如跌破 EMA200 ---
    else:
        print("今日无突破，未触发警报。")

if __name__ == "__main__":
    job()
