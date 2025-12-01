import yfinance as yf
import pandas as pd
import smtplib
import os
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header

# --- 配置区域 ---
SYMBOL = "^IXIC"    # 纳斯达克综合指数
BUFFER_PERCENT = 0.03 
CSV_FILENAME = "nasdaq_daily_data.csv"

# --- 邮件发送函数 (带附件版) ---
def send_email_with_attachment(subject, content, attachment_path):
    try:
        sender = os.environ["MAIL_USERNAME"]
        password = os.environ["MAIL_PASSWORD"]
        receiver = os.environ["MAIL_RECEIVER"]
        
        # 网易 163 配置
        smtp_server = "smtp.163.com"
        smtp_port = 465
        
        # 创建由多部分组成的邮件对象
        msg = MIMEMultipart()
        msg['From'] = Header("纳指监控机器人", 'utf-8')
        msg['To'] = Header("Master", 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        
        # 1. 添加正文文本
        msg.attach(MIMEText(content, 'plain', 'utf-8'))
        
        # 2. 添加 CSV 附件
        if os.path.exists(attachment_path):
            with open(attachment_path, 'rb') as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
                # 设置附件头信息
                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
                msg.attach(part)
                print(f"📎 已添加附件: {attachment_path}")
        else:
            print("⚠️ 未找到附件文件，将只发送文本。")

        # 发送
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(sender, password)
        server.sendmail(sender, [receiver], msg.as_string())
        server.quit()
        print("✅ 邮件(含附件)发送成功！")
        
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

# --- 辅助函数：安全获取数值 ---
def get_val(row, col_name):
    val = row[col_name]
    if hasattr(val, 'iloc'): 
        return float(val.iloc[0])
    return float(val)

# --- 主逻辑 ---
def job():
    print(f"开始获取 {SYMBOL} 全部历史数据 (Max)...")
    
    # 1. 获取数据 (使用 max 确保 EMA 精度与 TradingView 一致)
    df = yf.download(SYMBOL, period="max", interval="1d", progress=False, auto_adjust=True)
    
    if len(df) < 200:
        print("数据不足，无法计算")
        return

    # 2. 计算各项指标
    # EMA200 (指数移动平均)
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    # EMA200 上下缓冲带
    df['Upper_Buffer'] = df['EMA200'] * (1 + BUFFER_PERCENT)
    df['Lower_Buffer'] = df['EMA200'] * (1 - BUFFER_PERCENT)
    
    # SMA200 (简单移动平均 - 长期趋势参考)
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    # SMA40 (简单移动平均 - 也就是周线级别的 MA40/日线MA200的变体)
    df['SMA40'] = df['Close'].rolling(window=40).mean()

    # 3. 准备 CSV 文件
    print("正在生成 CSV 文件...")
    # 我们只保留最近 5 年的数据写入 CSV，避免文件太大，方便查看
    # 如果你想保存全部，去掉 .tail(1260) 即可
    output_df = df[['Close', 'EMA200', 'Upper_Buffer', 'Lower_Buffer', 'SMA200', 'SMA40']].tail(1260).copy()
    
    # 格式化一下数字，保留2位小数
    output_df = output_df.round(2)
    # 导出到 CSV
    output_df.to_csv(CSV_FILENAME, encoding='utf-8-sig') # utf-8-sig 防止 Excel 打开乱码

    # 4. 获取今日与昨日数据用于判断逻辑
    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    
    price_now = get_val(today, 'Close')
    upper_line_now = get_val(today, 'Upper_Buffer')
    lower_line_now = get_val(today, 'Lower_Buffer')
    ema_now = get_val(today, 'EMA200')
    sma200_now = get_val(today, 'SMA200')
    sma40_now = get_val(today, 'SMA40')
    
    price_yesterday = get_val(yesterday, 'Close')
    upper_line_yesterday = get_val(yesterday, 'Upper_Buffer')

    # 5. 构建邮件内容
    base_msg = (
        f"数据来源: {SYMBOL} (全量历史数据)\n"
        f"日期: {today.name.date()}\n"
        f"收盘价: {price_now:.2f}\n"
        f"------------------------------\n"
        f"【核心参考】\n"
        f"EMA200: {ema_now:.2f}\n"
        f"上轨 (+3%): {upper_line_now:.2f}\n"
        f"下轨 (-3%): {lower_line_now:.2f}\n"
        f"------------------------------\n"
        f"【辅助参考】\n"
        f"SMA200: {sma200_now:.2f}\n"
        f"SMA40:  {sma40_now:.2f}\n"
        f"------------------------------\n"
        f"详细数据请查看附件 CSV。\n"
    )

    # 6. 判断逻辑 & 确定标题
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
    
    # 逻辑 C: 无事发生
    else:
        subject = f"日报: {today.name.date()} 无突破信号"
        status_msg = "今日无特殊信号，市场运行在现有趋势中。"

    # 7. 发送邮件
    final_content = base_msg + status_msg
    print(final_content)
    
    send_email_with_attachment(subject, final_content, CSV_FILENAME)

if __name__ == "__main__":
    job()
