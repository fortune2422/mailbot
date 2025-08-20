import smtplib
import csv
import os
import time
from flask import Flask, jsonify
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL = os.getenv("jilicsone@gmail.com")
APP_PASSWORD = os.getenv("rwfc xnul qrtr uowx")

def send_emails():
    recipients = []
    with open("emails.csv", newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            recipients.append(row)

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(EMAIL, APP_PASSWORD)

    results = []
    for idx, person in enumerate(recipients, start=1):
        to_email = person["email"]
        name = person.get("name", "朋友")

        msg = MIMEMultipart()
        msg["From"] = EMAIL
        msg["To"] = to_email
        msg["Subject"] = "Python + Render 自动邮件测试"

        body = f"你好 {name},\n\n这是一封来自 Render 免费 Web 服务触发的测试邮件。\n\n祝好！"
        msg.attach(MIMEText(body, "plain"))

        try:
            server.sendmail(EMAIL, to_email, msg.as_string())
            results.append(f"✅ {idx}. 已发送: {to_email}")
        except Exception as e:
            results.append(f"❌ {idx}. 发送失败: {to_email}, 错误: {e}")

        time.sleep(5)

    server.quit()
    return results

@app.route("/send", methods=["GET"])
def trigger_send():
    results = send_emails()
    return jsonify(results)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
