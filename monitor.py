import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
from datetime import datetime

# --- 配置区域 ---
# 修改为纳斯达克综合指数 (Nasdaq Composite)
SYMBOL = "^IXIC" 
BUFFER_PERCENT = 0.03 

# --- 邮件发送函数 ---
def send_email(subject, content):
    try:
        sender = os.environ["MAIL_USERNAME"]
        password = os.environ["MAIL_PASSWORD"]
        receiver = os.environ["MAIL_RECEIVER"]
        
        # 默认使用 Gmail。如果是 QQ 邮箱请改为 smtp.qq.com
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = Header("纳指监控机器人", 'utf-8')
        message['To'] = Header("Master", 'utf-8')
        message['Subject'] = Header(subject, 'utf-8')
    
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, [receiver], message.as_string())
        server.quit()
        print("邮件发送成功！")
    except Exception as e:
        print(f"邮件发送失败: {e}")

# --- 辅助函数：安全获取数值 ---
def get_val(row, col_name):
    val = row[col_name]
    if hasattr(val, 'iloc'): 
        return float(val.iloc[0])
    return float(val)

# --- 主逻辑 ---
def job():
    print(f"开始获取 {SYMBOL} 数据...")
    # 获取数据
    df = yf.download(SYMBOL, period="2y", interval="1d", progress=False, auto_adjust=True)
    
    if len(df) < 200:
        print("数据不足，无法计算")
        return

    # 计算指标
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    df['Upper_Buffer'] = df['EMA200'] * (1 + BUFFER_PERCENT)
    df['Lower_Buffer'] = df['EMA200'] * (1 - BUFFER_PERCENT)

    # 获取今日与昨日数据
    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    
    # 提取数值
    price_now = get_val(today, 'Close')
    upper_line_now = get_val(today, 'Upper_Buffer')
    lower_line_now = get_val(today, 'Lower_Buffer')
    ema_now = get_val(today, 'EMA200')
    
    price_yesterday = get_val(yesterday, 'Close')
    upper_line_yesterday = get_val(yesterday, 'Upper_Buffer')

    # --- 1. 构建基础邮件内容 (无论发什么邮件，这部分都有) ---
    base_msg = (
        f"开始获取 {SYMBOL} 数据...\n"
        f"日期: {today.name.date()}\n"
        f"收盘价: {price_now:.2f}\n"
        f"EMA200: {ema_now:.2f}\n"
        f"上轨 (+3%): {upper_line_now:.2f}\n"
        f"下轨 (-3%): {lower_line_now:.2f}\n"
        f"------------------------------\n"
    )

    # --- 2. 判断逻辑 & 确定标题 ---
    subject = ""
    status_msg = ""

    # 逻辑 A: 向上突破
    if price_yesterday < upper_line_yesterday and price_now > upper_line_now:
        subject = "🚀 警报：纳指突破 EMA200+3% 缓冲线！"
        status_msg = "【警报触发】价格刚刚站上强趋势线，可能开启加速上涨。"

    # 逻辑 B: 向下跌破
    elif price_yesterday > upper_line_yesterday and price_now < upper_line_now:
        subject = "📉 提示：纳指跌回 EMA200+3% 下方"
        status_msg = "【提示触发】价格回调跌破缓冲线，请注意观察。"
    
    # 逻辑 C: 无事发生 (这就是你要的日常状态)
    else:
        subject = "今日无突破，未触发警报。"
        status_msg = "今日无特殊信号，市场运行在现有趋势中。"

    # --- 3. 组合并发送邮件 ---
    final_content = base_msg + status_msg
    
    # 打印到控制台方便查看日志
    print(final_content)
    
    # 发送邮件 (强制发送)
    send_email(subject, final_content)

if __name__ == "__main__":
    job()
