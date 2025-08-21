import smtplib
import csv
import os
import time
import random
import datetime
from flask import Flask, jsonify, send_file, request, render_template_string

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
DAILY_LIMIT = 450  # 每个账号每日上限

# ========== 加载账号 ==========
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
account_usage = {acc["email"]: 0 for acc in ACCOUNTS}
last_reset_date = datetime.date.today()

# ========== 收件箱列表 ==========
INBOX_FILE = "inbox.csv"

def load_inbox():
    if not os.path.exists(INBOX_FILE):
        return []
    with open(INBOX_FILE, newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)

def save_inbox(data):
    with open(INBOX_FILE, "w", newline='', encoding="utf-8") as f:
        if data:
            fieldnames = data[0].keys()
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        else:
            f.write("")  # 空文件

# ========== 已发送邮箱的记录 ==========
SENT_FILE = "sent.csv"

def load_sent_emails():
    if not os.path.exists(SENT_FILE):
        return set()
    with open(SENT_FILE, newline='', encoding="utf-8") as f:
        reader = csv.reader(f)
        return {row[0] for row in reader}

def save_sent_email(email):
    with open(SENT_FILE, "a", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([email])

# ========== 辅助函数 ==========
def reset_daily_usage():
    global account_usage, last_reset_date
    today = datetime.date.today()
    if today != last_reset_date:
        account_usage = {acc["email"]: 0 for acc in ACCOUNTS}
        last_reset_date = today

def get_next_account():
    global current_index
    for _ in range(len(ACCOUNTS)):
        acc = ACCOUNTS[current_index]
        current_index = (current_index + 1) % len(ACCOUNTS)
        if account_usage[acc["email"]] < DAILY_LIMIT:
            return acc
    return None

# ========== 发送邮件 ==========
def send_emails(subject_template, body_template):
    reset_daily_usage()
    sent_emails = load_sent_emails()
    inbox = load_inbox()
    results = []

    for person in inbox:
        to_email = person.get("email")
        if not to_email or to_email in sent_emails:
            continue

        acc = get_next_account()
        if not acc:
            results.append("⚠️ 所有账号今天都达到上限，停止发送")
            break

        EMAIL = acc["email"]
        APP_PASSWORD = acc["app_password"]
        name = person.get("name", "Amigo")
        real_name = person.get("real_name", name)

        subject = subject_template.replace("{name}", name).replace("{real_name}", real_name)
        body = body_template.replace("{name}", name).replace("{real_name}", real_name)

        msg = MIMEMultipart()
        msg["From"] = EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.sendmail(EMAIL, to_email, msg.as_string())
            server.quit()

            account_usage[EMAIL] += 1
            save_sent_email(to_email)
            results.append(f"✅ 已发送: {to_email} （账号 {EMAIL}，今日已发 {account_usage[EMAIL]} 封）")
        except Exception as e:
            results.append(f"❌ 发送失败: {to_email}, 错误: {e}")
            continue

        time.sleep(random.randint(5, 15))

    # 更新收件箱
    inbox = [p for p in inbox if p.get("email") not in load_sent_emails()]
    save_inbox(inbox)
    return results

# ========== Flask 路由 ==========
TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>MailBot 后台</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { margin: 20px; }
        textarea { resize: none; }
        .log { background: #f8f9fa; padding: 10px; height: 250px; overflow-y: auto; border-radius: 5px; margin-top: 10px; }
        .table-container { max-height: 300px; overflow-y: auto; }
    </style>
</head>
<body>
<div class="container">
    <h1 class="mb-4">MailBot 后台</h1>

    <div class="mb-3">
        <form id="uploadForm" enctype="multipart/form-data" class="d-flex gap-2">
            <input class="form-control" type="file" name="file" required>
            <button class="btn btn-primary" type="submit">上传 CSV</button>
        </form>
    </div>

    <div class="mb-3">
        <label class="form-label">主题模板</label>
        <input class="form-control" type="text" id="subject" value="Olá {real_name}, sua recompensa VIP da JILI707 está disponível">
    </div>

    <div class="mb-3">
        <label class="form-label">正文模板</label>
        <textarea class="form-control" id="body" rows="10">👋 Olá {real_name},

Detectamos que você ainda não resgatou sua recompensa do mês de agosto.

👉 Por favor, acesse sua conta e clique no ícone de promoções na parte inferior da página inicial para resgatar sua recompensa.

💰 Lembrete: a recompensa será creditada automaticamente todo dia 1º de cada mês.

✨ Quanto mais você evoluir sua conta, maiores serão os benefícios que poderá receber.

📈 Continue evoluindo sua conta para desbloquear recompensas ainda maiores!

— Equipe JILI707。vip
</textarea>
    </div>

    <div class="mb-3 d-flex gap-2">
        <button class="btn btn-success" id="sendBtn">发送邮件</button>
        <button class="btn btn-warning" id="downloadBtn">下载已发送邮箱</button>
    </div>

    <h3>收件箱列表</h3>
    <div class="table-container">
        <table class="table table-bordered table-striped" id="inboxTable">
            <thead>
                <tr><th>Email</th><th>Name</th><th>Real Name</th></tr>
            </thead>
            <tbody></tbody>
        </table>
    </div>

    <h3>发送日志</h3>
    <div class="log" id="sendLog"></div>
</div>

<script>
async function loadInbox() {
    const resp = await fetch("/get-inbox");
    const data = await resp.json();
    const tbody = document.querySelector("#inboxTable tbody");
    tbody.innerHTML = "";
    data.forEach(person => {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${person.email}</td><td>${person.name}</td><td>${person.real_name}</td>`;
        tbody.appendChild(tr);
    });
}

document.getElementById("uploadForm").onsubmit = async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const resp = await fetch("/upload", { method: "POST", body: formData });
    const result = await resp.text();
    alert(result);
    loadInbox();
};

document.getElementById("sendBtn").onclick = async () => {
    const subject = document.getElementById("subject").value;
    const body = document.getElementById("body").value;
    const resp = await fetch(`/send?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`);
    const results = await resp.json();
    const log = document.getElementById("sendLog");
    results.forEach(r => {
        const div = document.createElement("div");
        div.textContent = r;
        log.appendChild(div);
    });
    loadInbox();
};

document.getElementById("downloadBtn").onclick = () => {
    window.open("/download-sent");
};

window.onload = loadInbox;
</script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def home():
    return render_template_string(TEMPLATE)

@app.route("/upload", methods=["POST"])
def upload_csv():
    file = request.files.get("file")
    if not file:
        return "❌ 未选择文件", 400
    file.save(INBOX_FILE)
    return "✅ 文件上传成功"

@app.route("/get-inbox", methods=["GET"])
def get_inbox():
    inbox = load_inbox()
    return jsonify(inbox)

@app.route("/send", methods=["GET"])
def trigger_send():
    subject = request.args.get("subject", "")
    body = request.args.get("body", "")
    results = send_emails(subject, body)
    return jsonify(results)

@app.route("/download-sent", methods=["GET"])
def download_sent():
    if not os.path.exists(SENT_FILE):
        with open(SENT_FILE, "w", newline='', encoding="utf-8") as f:
            f.write("")
    return send_file(SENT_FILE, as_attachment=True, download_name="sent.csv", mimetype="text/csv")

@app.route("/stats", methods=["GET"])
def stats():
    reset_daily_usage()
    return jsonify(account_usage)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
