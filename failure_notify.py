import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr


def build_message() -> EmailMessage:
    workflow = os.getenv("WORKFLOW_NAME", "NASDAQ-100 automation")
    run_url = os.getenv("RUN_URL", "—")
    message = EmailMessage()
    message["From"] = formataddr(("NASDAQ-100 自动化告警", os.environ["MAIL_USERNAME"]))
    message["To"] = os.environ["MAIL_RECEIVER"]
    message["Subject"] = f"[故障] {workflow} 执行失败"
    message.set_content(
        "\n".join(
            [
                "NASDAQ-100 自动任务未正常完成。",
                f"工作流：{workflow}",
                f"分支：{os.getenv('GITHUB_REF_NAME', '—')}",
                f"提交：{os.getenv('GITHUB_SHA', '—')[:12]}",
                f"运行详情：{run_url}",
                "请打开运行详情查看首个失败步骤；本邮件由独立故障通道发送。",
            ]
        )
    )
    return message


def main() -> None:
    required = ("MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_RECEIVER")
    if any(not os.getenv(name) for name in required):
        print("邮件 Secret 不完整，跳过故障通知")
        return
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(os.environ["MAIL_USERNAME"], os.environ["MAIL_PASSWORD"])
        server.send_message(build_message())
    print("✅ 故障通知邮件已发送")


if __name__ == "__main__":
    main()
