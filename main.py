import smtplib
import csv
import os
import time
from flask import Flask, jsonify
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

# Gmail SMTP 配置
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL = os.getenv("EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")

# 批量发送邮件函数
def send_emails():
    recipients = []
    try:
        with open("emails.csv", newline='', encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                recipients.append(row)
    except FileNotFoundError:
        return ["❌ emails.csv 文件未找到"]

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    try:
        server.login(EMAIL, APP_PASSWORD)
    except smtplib.SMTPAuthenticationError:
        return ["❌ 邮箱登录失败，请检查账号或应用密码"]

    results = []
    for idx, person in enumerate(recipients, start=1):
        to_email = person.get("email")
        if not to_email:
            continue
        name = person.get("name", "朋友")
        real_name = person.get("name2", name)

        msg = MIMEMultipart()
        msg["From"] = EMAIL
        msg["To"] = to_email
        msg["Subject"] = f"Olá {real_name}, sua recompensa VIP da JILI707 está disponível"

        body = f"""Olá {name},

        Detectamos que você ainda não resgatou sua recompensa do mês de agosto.

        Por favor, acesse sua conta e clique no ícone de promoções na parte inferior da página inicial para resgatar sua recompensa.

        Lembrete: a recompensa será creditada automaticamente todo dia 1º de cada mês.

        Quanto mais você evoluir sua conta, maiores serão os benefícios que poderá receber.

        Atenciosamente,
        Equipe JILI707。vip
        """
        msg.attach(MIMEText(body, "plain"))

        try:
            server.sendmail(EMAIL, to_email, msg.as_string())
            results.append(f"✅ {idx}. 已发送: {to_email}")
        except Exception as e:
            results.append(f"❌ {idx}. 发送失败: {to_email}, 错误: {e}")

        time.sleep(5)  # 避免一次性发太快被 Gmail 限制

    server.quit()
    return results

# 健康检查接口
@app.route("/", methods=["GET"])
def home():
    return "服务正常运行 🚀"

# 邮件触发接口
@app.route("/send", methods=["GET"])
def trigger_send():
    results = send_emails()
    return jsonify(results)

if __name__ == "__main__":
    # Render 免费层要求绑定 $PORT 环境变量
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
