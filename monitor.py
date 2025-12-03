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
TARGETS = {
    "NASDAQ": "^IXIC",   # 纳斯达克综合指数
    "GOLD": "GC=F"       # 黄金期货
}

# 标题显示的缩写映射 (为了保持标题简短)
SHORT_NAMES = {
    "NASDAQ": "NQ",
    "GOLD": "GOLD"
}

BUFFER_PERCENT = 0.03 
CSV_FILENAME = "market_daily_data.csv"

# --- 邮件发送函数 (Gmail 版) ---
def send_email_with_attachment(subject, content, attachment_path):
    try:
        sender = os.environ["MAIL_USERNAME"]
        password = os.environ["MAIL_PASSWORD"]
        receiver = os.environ["MAIL_RECEIVER"]
        
        smtp_server = "smtp.gmail.com"
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
        print(f"✅ 邮件已发送至 {receiver}！")
        
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

# --- 辅助函数：计算指标 ---
def calculate_indicators(df):
    df = df.copy()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    df['Upper_Buffer'] = df['EMA200'] * (1 + BUFFER_PERCENT)
    df['Lower_Buffer'] = df['EMA200'] * (1 - BUFFER_PERCENT)
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    df['SMA40'] = df['Close'].rolling(window=40).mean()
    return df.round(2)

# --- 辅助函数：获取单点数值 ---
def get_val(row, col_name):
    val = row.get(col_name)
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
    title_summaries = [] # 用于收集标题里的涨跌幅信息

    for name, symbol in TARGETS.items():
        print(f"正在处理: {name} ({symbol})...")
        
        try:
            df = yf.download(symbol, period="max", interval="1d", progress=False, auto_adjust=True)
        except Exception as e:
            print(f"⚠️ 下载失败 {name}: {e}")
            continue
        
        if len(df) < 200:
            print(f"⚠️ {name} 数据不足，跳过")
            continue

        df = calculate_indicators(df)
        
        # 数据合并准备
        cols_to_keep = ['Close', 'EMA200', 'Upper_Buffer', 'Lower_Buffer', 'SMA200', 'SMA40']
        df_export = df[cols_to_keep].add_suffix(f"_{name}")
        
        if combined_df.empty:
            combined_df = df_export
        else:
            combined_df = pd.merge(combined_df, df_export, left_index=True, right_index=True, how='outer')

        # --- 获取今日与昨日数据 ---
        today = df.iloc[-1]
        yesterday = df.iloc[-2]
        
        p_now = get_val(today, 'Close')
        p_prev = get_val(yesterday, 'Close')
        
        # --- 新增：计算涨跌幅 ---
        # 计算百分比变化
        pct_change = ((p_now - p_prev) / p_prev) * 100
        # 格式化字符串，例如 "+1.25%" 或 "-0.50%"
        pct_str = f"{pct_change:+.2f}%"
        
        # 添加到标题摘要列表 [NQ +1.2%]
        short_name = SHORT_NAMES.get(name, name)
        title_summaries.append(f"{short_name} {pct_str}")

        # 获取其他指标
        upper_now = get_val(today, 'Upper_Buffer')
        upper_prev = get_val(yesterday, 'Upper_Buffer')
        lower_now = get_val(today, 'Lower_Buffer')
        lower_prev = get_val(yesterday, 'Lower_Buffer')
        ema_now = get_val(today, 'EMA200')
        ema_prev = get_val(yesterday, 'EMA200')

        status_icon = "🟢"
        status_text = "趋势维持中"

        # --- 信号检测逻辑 ---
        # 逻辑 A: 向上突破 Upper Buffer
        if p_prev < upper_prev and p_now > upper_now:
            status_icon = "🚀"
            status_text = "【警报】突破 EMA200+3% 强阻力！可能开启加速上涨。进入大涨行情，请重仓尽快入场！"
            alert_triggered = True
            urgent_subjects.append(f"{name}突破")
            
        # 逻辑 B: 站回 EMA200
        elif p_prev < ema_prev and p_now > ema_now:
            status_icon = "📈"
            status_text = "【提示】价格收回 EMA200 上方，请注意观察，可能进入上涨行情，开始入场。"
            alert_triggered = True
            urgent_subjects.append(f"{name}转强")

        # 逻辑 C: 跌破 Lower Buffer
        elif p_prev > lower_prev and p_now < lower_now:
            status_icon = "📉"
            status_text = "【警报】跌破 EMA200-3% 支撑！请注意观察，清仓离场！"
            alert_triggered = True
            urgent_subjects.append(f"{name}破位")
        
        # 生成正文段落
        report_section = (
            f"{status_icon} **{name} ({symbol})**\n"
            f"日期: {today.name.date()}\n"
            f"收盘: {p_now:.2f} ({pct_str}) | 状态: {status_text}\n"
            f"EMA200: {ema_now:.2f}\n"
            f"上轨(+3%): {upper_now:.2f} | 下轨(-3%): {lower_now:.2f}\n"
            f"------------------------------\n"
        )
        email_report.append(report_section)

    # 保存 CSV
    print(f"正在保存合并数据到 {CSV_FILENAME}...")
    combined_df = combined_df.tail(1260).sort_index(ascending=False)
    combined_df.to_csv(CSV_FILENAME, encoding='utf-8-sig')

    # --- 构建最终标题 ---
    # 将 [NQ +1.2%] 和 [GOLD -0.5%] 拼接
    title_header = f"[{' | '.join(title_summaries)}]"
    
    if alert_triggered:
        subject = f"{title_header} 🔔 警报: {' & '.join(urgent_subjects)}"
    else:
        subject = f"{title_header} 日报: {datetime.now().strftime('%m-%d')} 市场平静"

    # 构建正文
    full_content = "【每日市场扫描】\n\n" + "\n".join(email_report) + "\n详细数据请查看附件 CSV。"
        
    print(f"拟发送标题: {subject}")
    send_email_with_attachment(subject, full_content, CSV_FILENAME)

if __name__ == "__main__":
    job()
