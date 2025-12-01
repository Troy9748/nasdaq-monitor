import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
from datetime import datetime

# --- 配置区域 ---
SYMBOL = "^NDX" 
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
        print(f"邮件发送失败 (请检查密码或服务器设置): {e}")

# --- 辅助函数：安全获取数值 ---
def get_val(row, col_name):
    """
    解决 FutureWarning 和 ValueError。
    强制将 Pandas Series 对象转换为纯 float 数字。
    """
    val = row[col_name]
    # 如果是 Series (比如 yfinance 返回了多级索引)，取第一个值
    if hasattr(val, 'iloc'): 
        return float(val.iloc[0])
    return float(val)

# --- 主逻辑 ---
def job():
    print(f"开始获取 {SYMBOL} 数据...")
    # 修复 Warning: 显式设置 auto_adjust=True
    df = yf.download(SYMBOL, period="2y", interval="1d", progress=False, auto_adjust=True)
    
    if len(df) < 200:
        print("数据不足，无法计算")
        return

    # 计算 EMA200
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    # 计算带缓冲的警戒线
    df['Upper_Buffer'] = df['EMA200'] * (1 + BUFFER_PERCENT)
    df['Lower_Buffer'] = df['EMA200'] * (1 - BUFFER_PERCENT)

    # 获取最近两天的数据
    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    
    # --- 关键修复：提前全部转为 float ---
    # 这样比较时就是纯数字比大小，不会报错
    price_now = get_val(today, 'Close')
    upper_line_now = get_val(today, 'Upper_Buffer')
    lower_line_now = get_val(today, 'Lower_Buffer')
    
    price_yesterday = get_val(yesterday, 'Close')
    upper_line_yesterday = get_val(yesterday, 'Upper_Buffer')
    
    ema_now = get_val(today, 'EMA200')

    print(f"日期: {today.name.date()}")
    print(f"收盘价: {price_now:.2f}")
    print(f"EMA200: {ema_now:.2f}")
    print(f"上轨 (+3%): {upper_line_now:.2f}")
    print(f"下轨 (-3%): {lower_line_now:.2f}")

    # --- 警报逻辑 1: 向上突破 EMA200 + 3% ---
    if price_yesterday < upper_line_yesterday and price_now > upper_line_now:
        msg = f"【警报】纳斯达克指数刚刚突破 EMA200 + 3% 缓冲线！\n\n当前价格: {price_now:.2f}\n警戒线: {upper_line_now:.2f}\n\n趋势可能进入加速上涨阶段。"
        send_email("🚀 买入信号：纳指突破缓冲带", msg)

    # --- 警报逻辑 2: 向下跌破 EMA200 + 3% ---
    elif price_yesterday > upper_line_yesterday and price_now < upper_line_now:
         msg = f"【提示】纳斯达克指数跌回 EMA200 + 3% 缓冲线下方。\n\n当前价格: {price_now:.2f}\n警戒线: {upper_line_now:.2f}"
         send_email("📉 提示：纳指回调", msg)
    
    else:
        print("今日无突破，未触发警报。")

if __name__ == "__main__":
    job()
