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
# 字典结构：显示名称 -> 股票代码
TARGETS = {
    "NASDAQ": "^IXIC",   # 纳斯达克综合指数
    "GOLD": "GC=F"       # 黄金期货 (COMEX Gold Futures)
}

BUFFER_PERCENT = 0.03 
CSV_FILENAME = "market_daily_data.csv" # 改个名字，因为现在包含多个市场数据

# --- 邮件发送函数 (保持不变) ---
def send_email_with_attachment(subject, content, attachment_path):
    try:
        sender = os.environ["MAIL_USERNAME"]
        password = os.environ["MAIL_PASSWORD"]
        receiver = os.environ["MAIL_RECEIVER"]
        
        # 你的SMTP服务器配置 (这里以网易163为例，Gmail为 smtp.gmail.com)
        smtp_server = "smtp.163.com"
        smtp_port = 465
        
        msg = MIMEMultipart()
        msg['From'] = Header("市场监控机器人", 'utf-8')
        msg['To'] = Header("Master", 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        
        msg.attach(MIMEText(content, 'plain', 'utf-8'))
        
        if os.path.exists(attachment_path):
            with open(attachment_path, 'rb') as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
                msg.attach(part)
                print(f"📎 已添加附件: {attachment_path}")
        
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(sender, password)
        server.sendmail(sender, [receiver], msg.as_string())
        server.quit()
        print("✅ 邮件发送成功！")
        
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

# --- 辅助函数：计算指标 ---
def calculate_indicators(df):
    """接收原始DF，返回计算好指标的DF"""
    df = df.copy()
    # EMA200
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    # Buffers
    df['Upper_Buffer'] = df['EMA200'] * (1 + BUFFER_PERCENT)
    df['Lower_Buffer'] = df['EMA200'] * (1 - BUFFER_PERCENT)
    # SMAs
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    df['SMA40'] = df['Close'].rolling(window=40).mean()
    return df.round(2)

# --- 辅助函数：获取单点数值 ---
def get_val(row, col_name):
    val = row.get(col_name) # 使用 .get 防止列不存在报错
    if val is None: return 0.0
    if hasattr(val, 'iloc'): return float(val.iloc[0])
    return float(val)

# --- 核心逻辑 ---
def job():
    print("开始获取市场数据...")
    
    combined_df = pd.DataFrame()
    email_report = []
    alert_triggered = False
    urgent_subjects = []

    # 1. 循环处理每个标的
    for name, symbol in TARGETS.items():
        print(f"正在处理: {name} ({symbol})...")
        
        # 下载数据
        df = yf.download(symbol, period="max", interval="1d", progress=False, auto_adjust=True)
        
        if len(df) < 200:
            print(f"⚠️ {name} 数据不足，跳过")
            continue

        # 计算指标
        df = calculate_indicators(df)
        
        # 重命名列，加上后缀 (例如 Close -> Close_NASDAQ) 以便合并
        # 只保留我们需要输出的列
        cols_to_keep = ['Close', 'EMA200', 'Upper_Buffer', 'Lower_Buffer', 'SMA200', 'SMA40']
        df_export = df[cols_to_keep].add_suffix(f"_{name}")
        
        # 合并到总表 (按日期索引合并)
        if combined_df.empty:
            combined_df = df_export
        else:
            combined_df = pd.merge(combined_df, df_export, left_index=True, right_index=True, how='outer')

        # --- 信号检测逻辑 ---
        # 获取最后两行数据 (注意：合并后的DF可能有空值，这里我们用原始单标的DF做逻辑判断更准确)
        today = df.iloc[-1]
        yesterday = df.iloc[-2]
        
        p_now = get_val(today, 'Close')
        p_prev = get_val(yesterday, 'Close')
        upper_now = get_val(today, 'Upper_Buffer')
        upper_prev = get_val(yesterday, 'Upper_Buffer')
        lower_now = get_val(today, 'Lower_Buffer')
        lower_prev = get_val(yesterday, 'Lower_Buffer')
        ema_now = get_val(today, 'EMA200')
        ema_prev = get_val(yesterday, 'EMA200')

        # 构建该标的的报告段落
        status_icon = "🟢"
        status_text = "趋势维持中"
        
        # 逻辑 A: 向上突破 Upper Buffer
        if p_prev < upper_prev and p_now > upper_now:
            status_icon = "🚀"
            status_text = "【警报】突破 EMA200+3% 强阻力！"
            alert_triggered = True
            urgent_subjects.append(f"{name}突破")
            
        # 逻辑 B: 站回 EMA200
        elif p_prev < ema_prev and p_now > ema_now:
            status_icon = "📈"
            status_text = "【提示】价格收回 EMA200 上方"
            alert_triggered = True
            urgent_subjects.append(f"{name}转强")

        # 逻辑 C: 跌破 Lower Buffer
        elif p_prev > lower_prev and p_now < lower_now:
            status_icon = "📉"
            status_text = "【警报】跌破 EMA200-3% 支撑！"
            alert_triggered = True
            urgent_subjects.append(f"{name}破位")
        
        # 生成段落
        report_section = (
            f"{status_icon} **{name} ({symbol})**\n"
            f"日期: {today.name.date()}\n"
            f"收盘: {p_now:.2f} | 状态: {status_text}\n"
            f"EMA200: {ema_now:.2f}\n"
            f"上轨(+3%): {upper_now:.2f} | 下轨(-3%): {lower_now:.2f}\n"
            f"------------------------------\n"
        )
        email_report.append(report_section)

    # 2. 保存合并后的 CSV
    print(f"正在保存合并数据到 {CSV_FILENAME}...")
    # 截取最近5年，按日期降序排列方便查看 (可选)
    combined_df = combined_df.tail(1260).sort_index(ascending=False)
    combined_df.to_csv(CSV_FILENAME, encoding='utf-8-sig')

    # 3. 发送邮件
    full_content = "【每日市场扫描】\n\n" + "\n".join(email_report) + "\n详细数据请查看附件 CSV。"
    
    if alert_triggered:
        subject = f"🔔 警报: {' & '.join(urgent_subjects)}"
    else:
        subject = f"日报: {datetime.now().strftime('%Y-%m-%d')} 市场平静"
        
    print(full_content)
    send_email_with_attachment(subject, full_content, CSV_FILENAME)

if __name__ == "__main__":
    job()
