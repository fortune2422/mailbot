import smtplib
import csv
import os
import time
import random
import datetime
from flask import Flask, jsonify
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# 每个账号每日上限（可以自己改）
DAILY_LIMIT = 450

# 自动加载所有账号
def load_accounts():
    accounts = []
    i = 1
    while True:
        email = os.getenv(f"EMAIL{i}")
        app_password = os.getenv(f"APP_PASSWORD{i}")
        if email and app_password:
            accounts.append({"email": email, "app_password": app_password})
            i += 1
        else:
            break
    return accounts

ACCOUNTS = load_accounts()
current_index = 0

# 统计每个账号的发送量
account_usage = {acc["email"]: 0 for acc in ACCOUNTS}
last_reset_date = datetime.date.today()

def reset_daily_usage():
    """每天零点重置统计"""
    global account_usage, last_reset_date
    today = datetime.date.today()
    if today != last_reset_date:
        account_usage = {acc["email"]: 0 for acc in ACCOUNTS}
        last_reset_date = today

def get_next_account():
    """获取下一个可用账号（轮流 + 上限保护）"""
    global current_index
    for _ in range(len(ACCOUNTS)):  # 最多循环一圈
        acc = ACCOUNTS[current_index]
        current_index = (current_index + 1) % len(ACCOUNTS)
        if account_usage[acc["email"]] < DAILY_LIMIT:
            return acc
    return None  # 如果所有账号都超限，就返回 None

def send_emails():
    reset_daily_usage()  # 每次触发时先检查是否需要清零

    recipients = []
    try:
        with open("emails.csv", newline='', encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                recipients.append(row)
    except FileNotFoundError:
        return ["❌ emails.csv 文件未找到"]

    results = []

    for idx, person in enumerate(recipients, start=1):
        acc = get_next_account()
        if not acc:
            results.append("⚠️ 所有账号今天都达到上限，停止发送")
            break

        EMAIL = acc["email"]
        APP_PASSWORD = acc["app_password"]

        to_email = person.get("email")
        if not to_email:
            continue
        name = person.get("name", "Amigo")
        real_name = person.get("name2", name)

        msg = MIMEMultipart()
        msg["From"] = EMAIL
        msg["To"] = to_email
        msg["Subject"] = f"Olá {real_name}, sua recompensa VIP da JILI707 está disponível"

        body = f"""👋 Olá {real_name},

Detectamos que você ainda não resgatou sua recompensa do mês de agosto.

👉 Por favor, acesse sua conta e clique no ícone de promoções na parte inferior da página inicial para resgatar sua recompensa.

💰 Lembrete: a recompensa será creditada automaticamente todo dia 1º de cada mês.

✨ Quanto mais você evoluir sua conta, maiores serão os benefícios que poderá receber.

📈 Continue evoluindo sua conta para desbloquear recompensas ainda maiores!

— Equipe JILI707。vip
"""
        msg.attach(MIMEText(body, "plain"))

        try:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.sendmail(EMAIL, to_email, msg.as_string())
            server.quit()

            # 更新统计
            account_usage[EMAIL] += 1

            results.append(
                f"✅ {idx}. 已发送: {to_email} （账号 {EMAIL}，今日已发 {account_usage[EMAIL]} 封）"
            )
        except Exception as e:
            results.append(f"❌ {idx}. 发送失败: {to_email}, 错误: {e}")

        # 随机延时 5~15 秒，更自然
        time.sleep(random.randint(5, 15))

    return results

@app.route("/", methods=["GET"])
def home():
    return "服务正常运行 🚀"

@app.route("/send", methods=["GET"])
def trigger_send():
    results = send_emails()
    return jsonify(results)

@app.route("/stats", methods=["GET"])
def stats():
    reset_daily_usage()
    return jsonify(account_usage)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
