import smtplib
import csv
import os
import time
import random
import datetime
from flask import Flask, jsonify, render_template_string, request, redirect, url_for

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
DAILY_LIMIT = 450  # 每个账号每日上限
RECIPIENT_FILE = "recipient.csv"  # 收件箱列表文件

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
def load_recipients():
    if not os.path.exists(RECIPIENT_FILE):
        return []
    with open(RECIPIENT_FILE, newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)

def save_recipients(recipients):
    with open(RECIPIENT_FILE, "w", newline='', encoding="utf-8") as f:
        fieldnames = ["email", "name", "real_name"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(recipients)

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
    recipients = load_recipients()
    if not recipients:
        return ["❌ 收件箱列表为空"]

    results = []
    remaining_recipients = []
    for idx, person in enumerate(recipients, start=1):
        to_email = person.get("email")
        if not to_email:
            continue

        acc = get_next_account()
        if not acc:
            results.append("⚠️ 所有账号今天都达到上限，停止发送")
            remaining_recipients.extend(recipients[idx-1:])
            break

        EMAIL = acc["email"]
        APP_PASSWORD = acc["app_password"]
        name = person.get("name", "Amigo")
        real_name = person.get("real_name", name)

        msg = MIMEMultipart()
        msg["From"] = EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject_template.replace("{name}", name).replace("{real_name}", real_name)

        body = body_template.replace("{name}", name).replace("{real_name}", real_name)
        msg.attach(MIMEText(body, "plain"))

        try:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.sendmail(EMAIL, to_email, msg.as_string())
            server.quit()

            account_usage[EMAIL] += 1
            results.append(f"✅ {idx}. 已发送: {to_email} （账号 {EMAIL}，今日已发 {account_usage[EMAIL]} 封）")
        except Exception as e:
            results.append(f"❌ {idx}. 发送失败: {to_email}, 错误: {e}")
            remaining_recipients.append(person)
            continue

        time.sleep(random.randint(3, 7))  # 简化等待时间

    # 保存剩余未发送的收件人
    save_recipients(remaining_recipients)
    return results

# ========== Flask 路由 ==========

# 主页面
@app.route("/", methods=["GET"])
def home():
    return render_template_string(HOME_HTML)

# 上传 CSV
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"status": "error", "message": "未选择文件"}), 400

    rows = []
    try:
        reader = csv.DictReader(file.stream.read().decode("utf-8").splitlines())
        for row in reader:
            rows.append({
                "email": row.get("email", "").strip(),
                "name": row.get("name", "").strip(),
                "real_name": row.get("real_name", "").strip()
            })
        existing = load_recipients()
        # 去重
        emails_existing = {r["email"] for r in existing}
        new_rows = [r for r in rows if r["email"] not in emails_existing]
        all_rows = existing + new_rows
        save_recipients(all_rows)
    except Exception as e:
        return jsonify({"status": "error", "message": f"解析文件失败: {e}"}), 400

    return jsonify({"status": "success", "message": f"成功上传 {len(new_rows)} 条收件人"})

# 发送邮件
@app.route("/send", methods=["POST"])
def trigger_send():
    subject = request.form.get("subject", "")
    body = request.form.get("body", "")
    results = send_emails(subject, body)
    return jsonify({"status": "success", "results": results})

# 查看收件箱
@app.route("/recipient", methods=["GET"])
def recipient():
    recipients = load_recipients()
    return render_template_string(RECIPIENT_HTML, recipients=recipients)

# 删除收件人
@app.route("/delete_recipient", methods=["POST"])
def delete_recipient():
    email = request.form.get("email")
    if not email:
        return jsonify({"status": "error", "message": "未指定邮箱"}), 400

    recipients = load_recipients()
    recipients = [r for r in recipients if r["email"] != email]
    save_recipients(recipients)
    return jsonify({"status": "success", "message": f"{email} 已删除"})

# 获取账号使用情况
@app.route("/stats", methods=["GET"])
def stats():
    reset_daily_usage()
    return jsonify(account_usage)

# ========== 前端模板 ==========

HOME_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>邮件发送工具</title>
<style>
body { font-family: Arial, sans-serif; margin: 20px; background:#f5f5f5; }
.container { max-width: 800px; margin:auto; padding:20px; background:white; border-radius:8px; box-shadow:0 0 10px rgba(0,0,0,0.1);}
input, textarea, button { width: 100%; margin:5px 0; padding:8px; border-radius:4px; border:1px solid #ccc;}
button { background:#4CAF50; color:white; border:none; cursor:pointer; }
button:hover { background:#45a049; }
.log { margin-top:10px; background:#eee; padding:10px; max-height:300px; overflow-y:auto; white-space:pre-wrap; }
a { display:inline-block; margin-top:10px; text-decoration:none; color:#333; }
</style>
</head>
<body>
<div class="container">
<h2>邮件发送工具</h2>
<label>上传收件箱 CSV：</label>
<input type="file" id="fileInput">
<button onclick="uploadFile()">上传</button>

<label>邮件主题（支持 {name} / {real_name}）：</label>
<input type="text" id="subject" placeholder="输入邮件主题">

<label>邮件正文（支持 {name} / {real_name}）：</label>
<textarea id="body" rows="6" placeholder="输入邮件正文"></textarea>
<button onclick="sendMail()">发送邮件</button>

<div class="log" id="sendLog"></div>

<a href="/recipient">查看收件箱列表</a>
</div>

<script>
function uploadFile() {
    const file = document.getElementById('fileInput').files[0];
    if(!file){ alert("请选择文件"); return; }
    const formData = new FormData();
    formData.append("file", file);

    fetch("/upload", { method:"POST", body:formData })
    .then(res=>res.json()).then(data=>{
        alert(data.message);
    }).catch(err=>{ alert("上传失败"); });
}

function sendMail() {
    const subject = document.getElementById('subject').value;
    const body = document.getElementById('body').value;
    fetch("/send", {
        method:"POST",
        headers: {'Content-Type':'application/x-www-form-urlencoded'},
        body: `subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
    })
    .then(res=>res.json()).then(data=>{
        if(data.results){
            const log = document.getElementById("sendLog");
            log.innerText = data.results.join("\\n");
            alert("发送完成");
        }
    }).catch(err=>{ alert("发送失败"); });
}
</script>
</body>
</html>
"""

RECIPIENT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>收件箱列表</title>
<style>
body { font-family: Arial, sans-serif; margin: 20px; background:#f5f5f5; }
.container { max-width: 900px; margin:auto; padding:20px; background:white; border-radius:8px; box-shadow:0 0 10px rgba(0,0,0,0.1);}
.card { border:1px solid #ccc; padding:10px; margin:5px; border-radius:6px; display:flex; justify-content:space-between; align-items:center; background:#fafafa;}
button { background:#f44336; color:white; border:none; padding:5px 10px; border-radius:4px; cursor:pointer;}
button:hover { background:#d32f2f; }
a { display:inline-block; margin-top:10px; text-decoration:none; color:#333; }
</style>
</head>
<body>
<div class="container">
<h2>收件箱列表</h2>
<div id="recipientList">
{% for r in recipients %}
<div class="card" id="card-{{r.email}}">
    <div>
        <strong>Email:</strong> {{r.email}}<br>
        <strong>Name:</strong> {{r.name}}<br>
        <strong>Real Name:</strong> {{r.real_name or ""}}
    </div>
    <button onclick="deleteRecipient('{{r.email}}')">删除</button>
</div>
{% endfor %}
</div>
<a href="/">返回主页面</a>
</div>

<script>
function deleteRecipient(email){
    if(!confirm("确认删除 "+email+" ?")) return;
    fetch("/delete_recipient", {
        method:"POST",
        headers: {'Content-Type':'application/x-www-form-urlencoded'},
        body:`email=${encodeURIComponent(email)}`
    }).then(res=>res.json()).then(data=>{
        alert(data.message);
        if(data.status==="success"){
            const card = document.getElementById("card-"+email);
            if(card) card.remove();
        }
    }).catch(err=>{ alert("删除失败"); });
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
