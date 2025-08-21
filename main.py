import smtplib
import csv
import os
import time
import random
import datetime
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
DAILY_LIMIT = 450  # 每个账号每日上限

# ========== 账号加载 ==========
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

# ========== 收件箱管理 ==========
RECIPIENT_FILE = "recipients.csv"
SENT_FILE = "sent.csv"

def load_recipients():
    if not os.path.exists(RECIPIENT_FILE):
        return []
    with open(RECIPIENT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)

def save_recipients(recipients):
    with open(RECIPIENT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["email","name","real_name"])
        writer.writeheader()
        writer.writerows(recipients)

def load_sent_emails():
    if not os.path.exists(SENT_FILE):
        return set()
    with open(SENT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        return {row[0] for row in reader}

def save_sent_email(email):
    with open(SENT_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([email])

# ========== 辅助 ==========
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
def send_emails_task(subject, body, interval):
    reset_daily_usage()
    recipients = load_recipients()
    sent_emails = load_sent_emails()
    results = []

    new_recipients = []

    for person in recipients:
        to_email = person.get("email")
        if not to_email or to_email in sent_emails:
            continue

        acc = get_next_account()
        if not acc:
            results.append({"email": to_email, "status": "⚠️ 所有账号今天都达到上限"})
            break

        EMAIL = acc["email"]
        APP_PASSWORD = acc["app_password"]
        real_name = person.get("real_name") or person.get("name") or "Amigo"

        # 替换模板变量
        mail_body = body.replace("{real_name}", real_name).replace("{name}", person.get("name","Amigo"))
        mail_subject = subject.replace("{real_name}", real_name).replace("{name}", person.get("name","Amigo"))

        try:
            msg = f"Subject: {mail_subject}\n\n{mail_body}"
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.sendmail(EMAIL, to_email, msg)
            server.quit()

            account_usage[EMAIL] += 1
            save_sent_email(to_email)
            results.append({"email": to_email, "status": "✅ 已发送", "account": EMAIL})
        except Exception as e:
            results.append({"email": to_email, "status": f"❌ 发送失败: {e}"})

        time.sleep(interval)

    # 更新收件箱列表，移除已发送邮箱
    for person in recipients:
        if person.get("email") not in [r["email"] for r in results if r["status"].startswith("✅")]:
            new_recipients.append(person)
    save_recipients(new_recipients)

    return results

# ========== Flask Routes ==========
# ---- 主页面 ----
@app.route("/", methods=["GET"])
def home():
    recipients = load_recipients()
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>MailBot 后台</title>
<style>
body { font-family: Arial; display:flex; margin:0; }
nav { width:200px; background:#2c3e50; color:white; min-height:100vh; padding:20px; }
nav button { display:block; width:100%; margin-bottom:10px; padding:10px; background:#34495e; border:none; color:white; cursor:pointer; }
nav button:hover { background:#1abc9c; }
main { flex:1; padding:20px; }
.card { border:1px solid #ccc; padding:10px; margin-bottom:10px; border-radius:5px; background:#f9f9f9; }
input, textarea { width:100%; margin-bottom:10px; padding:5px; }
</style>
</head>
<body>
<nav>
<button onclick="showPage('send')">发送邮件</button>
<button onclick="showPage('recipients')">收件箱管理</button>
</nav>
<main>
<div id="send" style="display:none;">
<h2>发送邮件</h2>
<label>邮件主题:</label>
<input type="text" id="subject" placeholder="例如：Olá {real_name}">
<label>邮件正文:</label>
<textarea id="body" rows="6" placeholder="正文支持 {real_name} {name}"></textarea>
<label>发送间隔秒数:</label>
<input type="number" id="interval" value="5" min="1">
<button onclick="sendEmails()">点击发送</button>
<h3>发送进度:</h3>
<div id="log"></div>
</div>

<div id="recipients" style="display:none;">
<h2>收件箱管理</h2>
<label>上传 CSV:</label>
<input type="file" id="csvfile">
<button onclick="uploadCSV()">上传</button>
<button onclick="clearAll()">一键清空收件箱</button>
<h3>收件箱列表:</h3>
<div id="recipientList"></div>
</div>
</main>

<script>
function showPage(id){
  document.getElementById('send').style.display='none';
  document.getElementById('recipients').style.display='none';
  document.getElementById(id).style.display='block';
  if(id=='recipients') loadRecipients();
}

function sendEmails(){
  const subject=document.getElementById('subject').value;
  const body=document.getElementById('body').value;
  const interval=parseInt(document.getElementById('interval').value)||5;
  if(!subject||!body){ alert("请填写主题和正文"); return; }
  if(!confirm("确认发送邮件吗？")) return;
  document.getElementById('log').innerHTML="";
  fetch("/send_emails", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({subject, body, interval})
  })
  .then(res=>res.json())
  .then(data=>{
    data.forEach(r=>{
      const div=document.createElement('div');
      div.textContent=`${r.email}: ${r.status}`;
      document.getElementById('log').appendChild(div);
    });
    alert("发送完成");
  });
}

function uploadCSV(){
  const file=document.getElementById('csvfile').files[0];
  if(!file){ alert("请选择文件"); return; }
  const formData=new FormData();
  formData.append("file",file);
  fetch("/upload_csv",{method:"POST",body:formData})
  .then(res=>res.text())
  .then(alert)
  .then(loadRecipients);
}

function loadRecipients(){
  fetch("/get_recipients")
  .then(res=>res.json())
  .then(data=>{
    const list=document.getElementById('recipientList');
    list.innerHTML="";
    data.forEach((r,i)=>{
      const div=document.createElement('div');
      div.className="card";
      div.innerHTML=`${i+1}. ${r.email} | ${r.name||""} | ${r.real_name||""} 
      <button onclick="deleteRecipient('${r.email}')">删除</button>`;
      list.appendChild(div);
    });
  });
}

function deleteRecipient(email){
  fetch("/delete_recipient",{
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({email})
  })
  .then(res=>res.text())
  .then(alert)
  .then(loadRecipients);
}

function clearAll(){
  if(!confirm("确认清空全部收件箱？")) return;
  fetch("/clear_recipients",{method:"POST"})
  .then(res=>res.text())
  .then(alert)
  .then(loadRecipients);
}
</script>
</body>
</html>
""")

# ---- 上传 CSV ----
@app.route("/upload_csv", methods=["POST"])
def upload_csv():
    file = request.files.get("file")
    if not file:
        return "❌ 没有文件"
    try:
        reader = csv.DictReader(file.stream.read().decode("utf-8").splitlines())
        recipients = []
        for row in reader:
            recipients.append({
                "email": row.get("email","").strip(),
                "name": row.get("name","").strip(),
                "real_name": row.get("real_name","").strip() or row.get("name","").strip()
            })
        save_recipients(recipients)
        return "✅ 文件上传成功"
    except Exception as e:
        return f"❌ 上传失败: {e}"

@app.route("/get_recipients", methods=["GET"])
def get_recipients():
    return jsonify(load_recipients())

@app.route("/delete_recipient", methods=["POST"])
def delete_recipient():
    data = request.get_json()
    email = data.get("email")
    recipients = load_recipients()
    recipients = [r for r in recipients if r.get("email") != email]
    save_recipients(recipients)
    return "✅ 已删除"

@app.route("/clear_recipients", methods=["POST"])
def clear_recipients():
    save_recipients([])
    return "✅ 已清空"

@app.route("/send_emails", methods=["POST"])
def trigger_send():
    data = request.get_json()
    subject = data.get("subject")
    body = data.get("body")
    interval = int(data.get("interval",5))
    results = send_emails_task(subject, body, interval)
    return jsonify(results)

if __name__ == "__main__":
    port=int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port)
