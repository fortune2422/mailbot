import smtplib
import csv
import os
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Gmail 配置 (环境变量中设置)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL = os.getenv("jilicsone@gmail.com")          # 你的 Gmail 地址
APP_PASSWORD = os.getenv("rwfc xnul qrtr uowx")  # Gmail 应用专用密码

if not EMAIL or not APP_PASSWORD:
    raise ValueError("请在 Render 的环境变量里设置 EMAIL 和 APP_PASSWORD")

# 读取收件人列表
recipients = []
with open("emails.csv", newline='', encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        recipients.append(row)

# 登录 Gmail SMTP
server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
server.starttls()
server.login(EMAIL, APP_PASSWORD)

# 循环发送邮件
for idx, person in enumerate(recipients, start=1):
    to_email = person["email"]
    name = person.get("name", "朋友")

    msg = MIMEMultipart()
    msg["From"] = EMAIL
    msg["To"] = to_email
    msg["Subject"] = "Python + Render 自动邮件测试"

    # 邮件正文
    body = f"你好 {name},\n\n这是一封来自 Render 自动运行 Python 脚本的测试邮件。\n\n祝好！"
    msg.attach(MIMEText(body, "plain"))

    try:
        server.sendmail(EMAIL, to_email, msg.as_string())
        print(f"✅ {idx}. 已发送: {to_email}")
    except Exception as e:
        print(f"❌ {idx}. 发送失败: {to_email}, 错误: {e}")

    time.sleep(5)  # 每封邮件间隔 5 秒，防止 Gmail 限流

server.quit()
print("📨 全部邮件发送完成！")
