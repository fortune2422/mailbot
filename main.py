import smtplib
import csv
import os
import time
import random
import datetime
from flask import Flask, jsonify, send_file, request, Response, stream_with_context
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
DAILY_LIMIT = 450
SENT_FILE = "sent.csv"
UPLOAD_FOLDER = 'uploads'
TEMPLATE_FILE = 'email_template.txt'
LOG_FILE = 'send_log.txt'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MIN_DELAY = 5
MAX_DELAY = 15

# ---------- 账号加载 ----------
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

# ---------- 已发送邮箱 ----------
def load_sent_emails():
    if not os.path.exists(SENT_FILE):
        return set()
    with open(SENT_FILE, newline='', encoding="utf-8") as f:
        return {row[0] for row in csv.reader(f)}

def save_sent_email(email):
    with open(SENT_FILE, "a", newline='', encoding="utf-8") as f:
        csv.writer(f).writerow([email])

def log_message(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def clear_log():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

# ---------- 辅助 ----------
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

# ---------- 邮件发送生成器 ----------
def send_emails_generator(min_delay=MIN_DELAY, max_delay=MAX_DELAY):
    reset_daily_usage()
    sent_emails = load_sent_emails()

    recipients_file = os.path.join(UPLOAD_FOLDER, "emails.csv")
    if not os.path.exists(recipients_file):
        yield "❌ emails.csv 文件未找到<br>"
        return

    recipients = []
    with open(recipients_file, newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            recipients.append(row)

    # 邮件模板
    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            try:
                subject, body_template = f.read().split("\n---\n")
            except ValueError:
                subject = "Olá {real_name}, sua recompensa VIP da JILI707 está disponível"
                body_template = "Olá {real_name},\n\nConteúdo da mensagem aqui."
    else:
        subject = "Olá {real_name}, sua recompensa VIP da JILI707 está disponível"
        body_template = "Olá {real_name},\n\nConteúdo da mensagem aqui."

    for idx, person in enumerate(recipients, start=1):
        to_email = person.get("email")
        if not to_email or to_email in sent_emails:
            continue

        acc = get_next_account()
        if not acc:
            yield "⚠️ 所有账号今天都达到上限，停止发送<br>"
            break

        EMAIL = acc["email"]
        APP_PASSWORD = acc["app_password"]
        name = person.get("name", "Amigo")
        real_name = person.get("name2", name)

        msg = MIMEMultipart()
        msg["From"] = EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject.replace("{name}", name).replace("{real_name}", real_name)
        body = body_template.replace("{name}", name).replace("{real_name}", real_name)
        msg.attach(MIMEText(body, "plain"))

        try:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.sendmail(EMAIL, to_email, msg.as_string())
            server.quit()

            account_usage[EMAIL] += 1
            save_sent_email(to_email)
            msg_out = f"✅ {idx}. 已发送: {to_email} （账号 {EMAIL}，今日已发 {account_usage[EMAIL]} 封）<br>"
            log_message(msg_out)
            yield msg_out
        except Exception as e:
            msg_err = f"❌ {idx}. 发送失败: {to_email}, 错误: {e}<br>"
            log_message(msg_err)
            yield msg_err

        time.sleep(random.randint(min_delay, max_delay))

    yield "<script>alert('✅ 邮件发送完成');</script>"

# ---------- Flask 路由 ----------
@app.route("/", methods=["GET"])
def home():
    return "服务正常运行 🚀"

@app.route("/stats", methods=["GET"])
def stats():
    reset_daily_usage()
    return jsonify(account_usage)

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return "❌ 没有文件", 400
    file = request.files["file"]
    if file.filename == "":
        return "❌ 未选择文件", 400
    file.save(os.path.join(UPLOAD_FOLDER, "emails.csv"))
    return "✅ 文件上传成功"

@app.route("/compose", methods=["POST"])
def compose_email():
    subject = request.form.get("subject")
    body = request.form.get("body")
    with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
        f.write(subject + "\n---\n" + body)
    return "✅ 邮件模板保存成功"

@app.route("/reset-sent", methods=["POST"])
def reset_sent():
    if os.path.exists(SENT_FILE):
        os.remove(SENT_FILE)
    clear_log()
    return "✅ 已发送记录已重置"

@app.route("/send-stream")
def send_stream():
    min_delay = int(request.args.get("min_delay", MIN_DELAY))
    max_delay = int(request.args.get("max_delay", MAX_DELAY))
    return Response(stream_with_context(send_emails_generator(min_delay, max_delay)))

@app.route("/download-sent")
def download_sent():
    if os.path.exists(SENT_FILE):
        return send_file(SENT_FILE, as_attachment=True)
    else:
        return "❌ sent.csv 不存在", 404

@app.route("/log")
def get_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return "<br>".join(f.read().splitlines())
    return "日志为空"

@app.route("/clear-log", methods=["POST"])
def clear_log_route():
    clear_log()
    return "✅ 日志已清空"

# ---------- 后台页面 ----------
@app.route("/admin")
def admin_home():
    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            template = f.read().split("\n---\n")
            subject = template[0] if len(template) > 0 else ""
            body = template[1] if len(template) > 1 else ""
    else:
        subject = ""
        body = ""

    return f'''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>📧 邮件后台管理</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<div class="container py-5">
<h1 class="mb-4">📧 邮件后台管理</h1>

<div class="card mb-3">
  <div class="card-header">上传 emails.csv</div>
  <div class="card-body">
    <form id="uploadForm" enctype="multipart/form-data" class="d-flex gap-2">
      <input type="file" name="file" class="form-control" required>
      <button type="submit" class="btn btn-primary">上传</button>
    </form>
  </div>
</div>

<div class="card mb-3">
  <div class="card-header">编辑邮件模板</div>
  <div class="card-body">
    <form id="composeForm">
      <div class="mb-2">
        <label class="form-label">主题</label>
        <input type="text" name="subject" class="form-control" value="{subject}" required>
      </div>
      <div class="mb-2">
        <label class="form-label">正文</label>
        <textarea name="body" rows="8" class="form-control" required>{body}</textarea>
      </div>
      <button type="submit" class="btn btn-success">保存模板</button>
    </form>
    <small class="text-muted">可使用占位符: {{name}}, {{real_name}}</small>
  </div>
</div>

<div class="card mb-3">
  <div class="card-header">发送邮件进度</div>
  <div class="card-body">
    <div class="d-flex gap-2 mb-2">
      <button id="sendBtn" class="btn btn-warning">开始发送</button>
      <input type="number" id="minDelay" class="form-control" style="width:80px;" placeholder="最小秒" value="{MIN_DELAY}">
      <input type="number" id="maxDelay" class="form-control" style="width:80px;" placeholder="最大秒" value="{MAX_DELAY}">
    </div>
    <div id="sendLog" style="height: 300px; overflow-y: scroll; background: #f8f9fa; padding: 10px; border: 1px solid #dee2e6;"></div>
  </div>
</div>

<div class="card mb-3">
  <div class="card-header">发送日志</div>
  <div class="card-body">
    <div class="d-flex gap-2 mb-2">
      <button id="refreshLog" class="btn btn-info">刷新日志</button>
      <button id="clearLog" class="btn btn-danger">清空日志</button>
    </div>
    <div id="logPanel" style="height: 200px; overflow-y: scroll; background: #f8f9fa; padding: 10px; border: 1px solid #dee2e6;"></div>
  </div>
</div>

<div class="card mb-3">
  <div class="card-header">其他操作</div>
  <div class="card-body d-flex gap-2">
    <a href="/download-sent" class="btn btn-info">下载已发送邮箱</a>
    <a href="/stats" class="btn btn-secondary" target="_blank">查看账号使用情况</a>
    <button id="resetBtn" class="btn btn-danger">重置已发送记录</button>
  </div>
</div>

<footer class="text-center mt-4 text-muted">
  © 2025 邮件后台管理
</footer>
</div>

<script>
// 上传 CSV
document.getElementById("uploadForm").addEventListener("submit", function(e){
    e.preventDefault();
    const formData = new FormData(this);
    fetch("/upload", {method:"POST", body: formData})
        .then(res => res.text())
        .then(msg => alert(msg));
});

// 保存模板
document.getElementById("composeForm").addEventListener("submit", function(e){
    e.preventDefault();
    const data = new FormData(this);
    fetch("/compose", {method:"POST", body:data})
        .then(res => res.text())
        .then(msg => alert(msg));
});

// 重置已发送
document.getElementById("resetBtn").addEventListener("click", function(){
    if(confirm("确定要重置已发送记录吗？此操作不可撤销！")){
        fetch("/reset-sent", {method:"POST"})
            .then(res => res.text())
            .then(msg => alert(msg));
    }
});

// 开始发送
document.getElementById("sendBtn").addEventListener("click", function(){
    const log = document.getElementById("sendLog");
    log.innerHTML = "";
    const minDelay = document.getElementById("minDelay").value || {MIN_DELAY};
    const maxDelay = document.getElementById("maxDelay").value || {MAX_DELAY};
    fetch(`/send-stream?min_delay=${minDelay}&max_delay=${maxDelay}`).then(response => {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        function read(){
            reader.read().then(({done, value})=>{
                if(done) return;
                log.innerHTML += decoder.decode(value);
                log.scrollTop = log.scrollHeight;
                read();
            });
        }
        read();
    });
});

// 日志操作
function refreshLog(){
    fetch("/log").then(res => res.text()).then(html => {
        document.getElementById("logPanel").innerHTML = html;
    });
}
document.getElementById("refreshLog").addEventListener("click", refreshLog);
document.getElementById("clearLog").addEventListener("click", function(){
    if(confirm("确定要清空日志吗？")){
        fetch("/clear-log", {method:"POST"})
            .then(res => res.text())
            .then(msg => { alert(msg); refreshLog(); });
    }
});

// 初始化日志
refreshLog();
</script>
</body>
</html>
'''

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
