import smtplib
import csv
import os
import time
import random
import datetime
from flask import Flask, jsonify, send_file, request, render_template_string, flash
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Response

app = Flask(__name__)
app.secret_key = "secret_key_for_flash"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
DAILY_LIMIT = 450  # 每个账号每日上限
SENT_FILE = "sent.csv"  # 记录已发送邮箱

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

# ========== 已发送邮箱的去重记录 ==========
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

def reset_sent_emails():
    if os.path.exists(SENT_FILE):
        os.remove(SENT_FILE)

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
def send_email_to_person(acc, person, idx):
    EMAIL = acc["email"]
    APP_PASSWORD = acc["app_password"]
    name = person.get("name", "Amigo")
    real_name = person.get("real_name", name)
    to_email = person.get("email")

    msg = MIMEMultipart()
    msg["From"] = EMAIL
    msg["To"] = to_email
    subject_template = person.get("subject", f"Olá {real_name}, sua recompensa VIP está disponível")
    body_template = person.get("body", f"Olá {real_name},\n\nDetectamos que você ainda não resgatou sua recompensa do mês.\n")
    msg["Subject"] = subject_template.format(name=name, real_name=real_name)
    msg.attach(MIMEText(body_template.format(name=name, real_name=real_name), "plain"))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL, APP_PASSWORD)
        server.sendmail(EMAIL, to_email, msg.as_string())
        server.quit()
        account_usage[EMAIL] += 1
        save_sent_email(to_email)
        return f"✅ {idx}. 已发送: {to_email} （账号 {EMAIL}，今日已发 {account_usage[EMAIL]} 封）\n"
    except Exception as e:
        return f"❌ {idx}. 发送失败: {to_email}, 错误: {e}\n"

def send_emails_stream(min_delay=5, max_delay=15):
    reset_daily_usage()
    sent_emails = load_sent_emails()
    recipients = []
    try:
        with open("emails.csv", newline='', encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                recipients.append(row)
    except FileNotFoundError:
        yield "❌ emails.csv 文件未找到\n"
        return

    for idx, person in enumerate(recipients, start=1):
        to_email = person.get("email")
        if not to_email or to_email in sent_emails:
            continue
        acc = get_next_account()
        if not acc:
            yield "⚠️ 所有账号今天都达到上限，停止发送\n"
            break
        yield send_email_to_person(acc, person, idx)
        time.sleep(random.randint(min_delay, max_delay))

# ========== Flask 路由 ==========
@app.route("/", methods=["GET"])
def admin_home():
    MIN_DELAY = 5
    MAX_DELAY = 15
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>📧 邮件后台管理</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<div class="container py-5">
<h1>📧 邮件后台管理</h1>
<hr>
<div class="mb-3">
<form id="uploadForm" enctype="multipart/form-data">
<input type="file" name="file" id="fileInput" class="form-control mb-2" required>
<button type="submit" class="btn btn-primary">上传 emails.csv</button>
</form>
</div>
<div class="mb-3">
<label>最小延迟（秒）:</label>
<input type="number" id="minDelay" value="{MIN_DELAY}" class="form-control">
<label>最大延迟（秒）:</label>
<input type="number" id="maxDelay" value="{MAX_DELAY}" class="form-control">
<button id="sendBtn" class="btn btn-success mt-2">开始发送</button>
<button id="resetBtn" class="btn btn-warning mt-2">重置已发送列表</button>
</div>
<pre id="sendLog" style="height:300px; overflow:auto; background:#f8f9fa; padding:10px;"></pre>
</div>

<script>
function showAlert(msg){{
    alert(msg);
}}

document.getElementById("uploadForm").addEventListener("submit", function(e){{
    e.preventDefault();
    var file = document.getElementById("fileInput").files[0];
    var formData = new FormData();
    formData.append("file", file);
    fetch("/upload", {{method:"POST", body:formData}}).then(res => res.text()).then(data => showAlert(data));
}});

document.getElementById("resetBtn").addEventListener("click", function(){{
    fetch("/reset").then(res => res.text()).then(data => showAlert(data));
}});

document.getElementById("sendBtn").addEventListener("click", function(){{
    const log = document.getElementById("sendLog");
    log.innerHTML = "";
    const minDelay = document.getElementById("minDelay").value || {MIN_DELAY};
    const maxDelay = document.getElementById("maxDelay").value || {MAX_DELAY};
    fetch(`/send-stream?min_delay=${{minDelay}}&max_delay=${{maxDelay}}`).then(response => {{
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        function read(){{
            reader.read().then(result => {{
                if(result.done) return;
                log.innerHTML += decoder.decode(result.value);
                log.scrollTop = log.scrollHeight;
                read();
            }});
        }}
        read();
    }});
}});
</script>
</body>
</html>
"""
    return render_template_string(html)

@app.route("/upload", methods=["POST"])
def upload_emails():
    if "file" not in request.files:
        return "❌ 未上传文件"
    file = request.files["file"]
    if file.filename == "":
        return "❌ 文件名为空"
    file.save("emails.csv")
    return "✅ 文件上传成功"

@app.route("/reset", methods=["GET"])
def reset_sent():
    reset_sent_emails()
    return "✅ 已发送列表已重置"

@app.route("/send-stream", methods=["GET"])
def send_stream():
    min_delay = int(request.args.get("min_delay", 5))
    max_delay = int(request.args.get("max_delay", 15))
    return Response(send_emails_stream(min_delay, max_delay), mimetype="text/plain")

@app.route("/download-sent", methods=["GET"])
def download_sent():
    if os.path.exists(SENT_FILE):
        return send_file(SENT_FILE, as_attachment=True)
    else:
        return "❌ sent.csv 不存在", 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
