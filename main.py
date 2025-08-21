import smtplib
import csv
import os
import time
import datetime
from threading import Thread
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
DAILY_LIMIT = 450
SENT_FILE = "sent.csv"
RECIPIENT_FILE = "emails.csv"

# ========== 账号 ==========
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

# ========== 收件箱 ==========
def load_recipients():
    if not os.path.exists(RECIPIENT_FILE):
        return []
    with open(RECIPIENT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)

def save_recipients(recipients):
    with open(RECIPIENT_FILE, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["email", "name", "real_name"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
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

# ========== 实时发送 ==========
sending_log = []
sending_flag = False

def send_emails_task(subject, body, interval):
    global sending_log, sending_flag
    sending_flag = True
    sending_log = []
    reset_daily_usage()
    recipients = load_recipients()
    sent_emails = load_sent_emails()
    new_recipients = []

    for person in recipients:
        to_email = person.get("email")
        if not to_email or to_email in sent_emails:
            continue

        acc = get_next_account()
        if not acc:
            sending_log.append({"email": to_email, "status": "⚠️ 所有账号今天上限"})
            break

        EMAIL = acc["email"]
        APP_PASSWORD = acc["app_password"]
        real_name = person.get("real_name") or person.get("name") or "Amigo"
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
            sending_log.append({"email": to_email, "status": "✅ 已发送"})
        except Exception as e:
            sending_log.append({"email": to_email, "status": f"❌ 发送失败: {e}"})

        time.sleep(interval)

    # 更新收件箱列表
    for person in recipients:
        if person.get("email") not in [r["email"] for r in sending_log if r["status"].startswith("✅")]:
            new_recipients.append(person)
    save_recipients(new_recipients)
    sending_flag = False

# ========== Flask 路由 ==========
@app.route("/")
def index():
    return render_template_string(TEMPLATE)

@app.route("/upload_recipients", methods=["POST"])
def upload_recipients():
    file = request.files.get("file")
    if file:
        content = file.read().decode("utf-8").splitlines()
        reader = csv.DictReader(content)
        recipients = list(reader)
        save_recipients(recipients)
        return jsonify({"success": True})
    return jsonify({"success": False, "msg":"未上传文件"})

@app.route("/delete_recipient", methods=["POST"])
def delete_recipient():
    email = request.json.get("email")
    recipients = load_recipients()
    recipients = [r for r in recipients if r["email"] != email]
    save_recipients(recipients)
    return jsonify({"success": True})

@app.route("/clear_recipients", methods=["POST"])
def clear_recipients():
    save_recipients([])
    return jsonify({"success": True})

@app.route("/send_emails", methods=["POST"])
def send_emails():
    data = request.json
    subject = data.get("subject","")
    body = data.get("body","")
    interval = int(data.get("interval",5))
    thread = Thread(target=send_emails_task, args=(subject, body, interval))
    thread.start()
    return jsonify({"success": True})

@app.route("/get_log")
def get_log():
    return jsonify(sending_log)

@app.route("/get_recipients")
def get_recipients():
    return jsonify(load_recipients())

@app.route("/get_account_usage")
def get_account_usage():
    reset_daily_usage()
    return jsonify(account_usage)

# ========== 前端模板 ==========
TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MailBot 后台</title>
<style>
body { font-family: Arial, sans-serif; margin:0; background:#f5f5f5; display:flex; }
.nav { width:200px; background:#1f2937; color:white; height:100vh; position:fixed; display:flex; flex-direction:column; }
.nav button { width:100%; padding:15px; border:none; background:#1f2937; color:white; cursor:pointer; text-align:left; }
.nav button.active { background:#4b5563; }
.main { margin-left:200px; padding:20px; flex:1; }
.card { background:white; padding:10px; margin:5px 0; border-radius:5px; box-shadow:0 1px 3px rgba(0,0,0,0.1); }
input, textarea, select { width:100%; padding:8px; margin:5px 0; }
button { padding:8px 12px; margin:5px 0; cursor:pointer; }
#log { max-height:300px; overflow:auto; background:white; padding:10px; border-radius:5px; }
.fixed_panel { position:fixed; top:0; right:0; width:250px; background:#f3f4f6; padding:10px; height:100vh; overflow:auto; box-shadow:-2px 0 5px rgba(0,0,0,0.1); }
.search { margin-bottom:10px; padding:5px; width:100%; }
.pagination { margin-top:10px; text-align:center; }
.page-btn { margin:0 3px; padding:3px 7px; cursor:pointer; border:1px solid #ccc; border-radius:3px; }
.page-btn.active { background:#4b5563; color:white; border:none; }
</style>
</head>
<body>
<div class="nav">
  <button id="btn_recipients" class="active" onclick="showPage('recipients')">收件箱管理</button>
  <button id="btn_send" onclick="showPage('send')">发送任务</button>
</div>
<div class="main">
  <div id="recipients_page">
    <h2>收件箱管理</h2>
    <input type="file" id="recipients_file">
    <button onclick="uploadRecipients()">上传 CSV</button>
    <button onclick="clearRecipients()">一键清空列表</button>
    <input class="search" id="recipient_search" placeholder="搜索收件箱">
    <div id="recipients_list"></div>
    <div class="pagination" id="recipient_pagination"></div>
  </div>
  <div id="send_page" style="display:none;">
    <h2>发送任务</h2>
    <input type="text" id="subject" placeholder="邮件主题 (可用 {name}, {real_name})">
    <textarea id="body" placeholder="邮件正文 (可用 {name}, {real_name})" rows="6"></textarea>
    <input type="number" id="interval" placeholder="发送间隔秒数" value="5">
    <button onclick="sendEmails()">开始发送</button>
    <input class="search" id="log_search" placeholder="搜索发送日志">
    <div id="log"></div>
    <div class="pagination" id="log_pagination"></div>
  </div>
</div>
<div class="fixed_panel">
  <h3>账号状态</h3>
  <div id="account_usage"></div>
</div>
<script>
function showPage(page){
  document.getElementById('recipients_page').style.display = page=='recipients'?'block':'none';
  document.getElementById('send_page').style.display = page=='send'?'block':'none';
  document.getElementById('btn_recipients').classList.toggle('active', page=='recipients');
  document.getElementById('btn_send').classList.toggle('active', page=='send');
  loadRecipients();
  loadAccountUsage();
}

// ========== 收件箱 ==========
let recipients_data = [];
let recipients_page = 1;
const recipients_per_page = 10;

function uploadRecipients(){
  const file=document.getElementById('recipients_file').files[0];
  if(!file){ alert('请选择文件'); return; }
  const formData=new FormData();
  formData.append('file', file);
  fetch('/upload_recipients',{method:'POST',body:formData})
  .then(r=>r.json()).then(d=>{ if(d.success){ alert('✅ 上传成功'); loadRecipients(); }});
}

function clearRecipients(){
  if(!confirm('确认清空收件箱列表吗？')) return;
  fetch('/clear_recipients',{method:'POST'}).then(r=>r.json()).then(d=>{ if(d.success){ alert('✅ 已清空'); loadRecipients(); }});
}

function loadRecipients(){
  fetch('/get_recipients').then(r=>r.json()).then(data=>{
    recipients_data = data;
    recipients_page = 1;
    renderRecipients();
  });
}

function renderRecipients(){
  const search = document.getElementById('recipient_search').value.toLowerCase();
  const filtered = recipients_data.filter(r=>r.email.toLowerCase().includes(search)|| (r.name||'').toLowerCase().includes(search));
  const total_pages = Math.ceil(filtered.length/recipients_per_page);
  if(recipients_page>total_pages) recipients_page=total_pages||1;
  const start = (recipients_page-1)*recipients_per_page;
  const page_data = filtered.slice(start,start+recipients_per_page);

  const div = document.getElementById('recipients_list'); div.innerHTML='';
  page_data.forEach(r=>{
    const card=document.createElement('div'); card.className='card';
    card.innerHTML=`<b>${r.email}</b> | ${r.name} | ${r.real_name||r.name} <button onclick="deleteRecipient('${r.email}')">删除</button>`;
    div.appendChild(card);
  });

  // 分页按钮
  const pagDiv = document.getElementById('recipient_pagination'); pagDiv.innerHTML='';
  for(let i=1;i<=total_pages;i++){
    const btn = document.createElement('span'); btn.className='page-btn'+(i===recipients_page?' active':''); btn.textContent=i;
    btn.onclick = ()=>{ recipients_page=i; renderRecipients(); };
    pagDiv.appendChild(btn);
  }
}
document.getElementById('recipient_search').addEventListener('input', renderRecipients);

function deleteRecipient(email){
  fetch('/delete_recipient',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})})
  .then(r=>r.json()).then(d=>{ if(d.success) loadRecipients(); });
}

// ========== 发送任务 ==========
let sending_data = [];
let sending_page = 1;
const sending_per_page = 10;
let pollingInterval;

function sendEmails(){
  const subject=document.getElementById('subject').value;
  const body=document.getElementById('body').value;
  const interval=parseInt(document.getElementById('interval').value)||5;
  if(!subject||!body){ alert('请填写主题和正文'); return; }
  if(!confirm('确认发送邮件吗？')) return;
  document.getElementById('log').innerHTML='';
  clearInterval(pollingInterval);
  pollingInterval=setInterval(loadLog,1000);
  fetch('/send_emails',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({subject,body,interval})
  }).then(r=>r.json()).then(d=>{
    alert('✅ 发送任务启动');
  });
}

function loadLog(){
  fetch('/get_log').then(r=>r.json()).then(data=>{
    sending_data = data;
    renderLog();
  });
}

function renderLog(){
  const search = document.getElementById('log_search').value.toLowerCase();
  const filtered = sending_data.filter(r=>r.email.toLowerCase().includes(search)||r.status.includes(search));
  const total_pages = Math.ceil(filtered.length/sending_per_page);
  if(sending_page>total_pages) sending_page=total_pages||1;
  const start = (sending_page-1)*sending_per_page;
  const page_data = filtered.slice(start,start+sending_per_page);

  const logDiv=document.getElementById('log'); logDiv.innerHTML='';
  page_data.forEach(r=>{
    const div=document.createElement('div'); div.className='card';
    div.textContent=`${r.email}: ${r.status}`;
    logDiv.appendChild(div);
  });
  logDiv.scrollTop=logDiv.scrollHeight;

  const pagDiv = document.getElementById('log_pagination'); pagDiv.innerHTML='';
  for(let i=1;i<=total_pages;i++){
    const btn = document.createElement('span'); btn.className='page-btn'+(i===sending_page?' active':''); btn.textContent=i;
    btn.onclick = ()=>{ sending_page=i; renderLog(); };
    pagDiv.appendChild(btn);
  }
}
document.getElementById('log_search').addEventListener('input', renderLog);

// ========== 账号状态 ==========
function loadAccountUsage(){
  fetch('/get_account_usage').then(r=>r.json()).then(data=>{
    const div=document.getElementById('account_usage'); div.innerHTML='';
    for(const [k,v] of Object.entries(data)){
      const d=document.createElement('div'); d.className='card';
      d.textContent=`${k}: 今日已发送 ${v} 封`;
      div.appendChild(d);
    }
  });
}
setInterval(loadAccountUsage,5000);

loadRecipients();
loadAccountUsage();
</script>
</body>
</html>
"""

if __name__=="__main__":
    port=int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port)
