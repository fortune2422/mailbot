import os
import csv
import smtplib
import time
import datetime
import json
from flask import Flask, request, jsonify, render_template_string, send_file
from email.mime.text import MIMEText
from email.header import Header
from io import StringIO

app = Flask(__name__)

# ================== 配置 ==================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
DAILY_LIMIT = 450
RECIPIENTS_FILE = "recipients.json"
LOG_FILE = "send_log.txt"

# ================== 账号加载 ==================
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

# 收件人列表
RECIPIENTS = []
SENT_RECIPIENTS = []

# 发送控制
SEND_QUEUE = []
IS_SENDING = False
PAUSED = False

# ================== 辅助函数 ==================
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

def send_email(account, to_email, subject, body):
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = account["email"]
        msg["To"] = to_email
        msg["Subject"] = Header(subject, "utf-8")

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(account["email"], account["app_password"])
        server.sendmail(account["email"], [to_email], msg.as_string())
        server.quit()
        account_usage[account["email"]] += 1
        return True, ""
    except Exception as e:
        return False, str(e)

def save_recipients():
    with open(RECIPIENTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"pending": RECIPIENTS, "sent": SENT_RECIPIENTS}, f, ensure_ascii=False, indent=2)

def load_recipients():
    global RECIPIENTS, SENT_RECIPIENTS
    if os.path.exists(RECIPIENTS_FILE):
        with open(RECIPIENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            RECIPIENTS = data.get("pending", [])
            SENT_RECIPIENTS = data.get("sent", [])
    else:
        RECIPIENTS, SENT_RECIPIENTS = [], []

def log_message(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# ================== 前端页面 ==================
@app.route("/", methods=["GET"])
def home():
    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>MailBot 后台</title>
        <style>
            body { font-family: Arial; margin:0; padding:0; display:flex; height:100vh; background:#f5f5f5;}
            .sidebar { width:200px; background:#2f4050; color:#fff; display:flex; flex-direction:column; }
            .sidebar button { padding:15px; background:none; border:none; color:#fff; cursor:pointer; text-align:left; font-size:16px; border-bottom:1px solid #3c4b5a;}
            .sidebar button:hover { background:#1ab394;}
            .main { flex:1; padding:20px; overflow:auto;}
            .card { background:#fff; padding:15px; margin-bottom:15px; box-shadow:0 2px 5px rgba(0,0,0,0.1);}
            table { width:100%; border-collapse: collapse;}
            th, td { border:1px solid #ddd; padding:8px; text-align:left;}
            th { background:#f2f2f2;}
            .btn { padding:6px 12px; background:#1ab394; color:#fff; border:none; cursor:pointer;}
            .btn:hover { background:#18a689;}
        </style>
    </head>
    <body>
        <div class="sidebar">
            <button onclick="showPage('recipients')">收件箱管理</button>
            <button onclick="showPage('send')">邮件发送</button>
        </div>
        <div class="main">
            <div id="recipientsPage">
                <h2>收件箱管理</h2>
                <input type="file" id="csvFile">
                <button class="btn" onclick="uploadCSV()">上传 CSV</button>
                <button class="btn" onclick="clearRecipients()">一键清空列表</button>
                <button class="btn" onclick="downloadTemplate()">下载 CSV 模板</button>
                <button class="btn" onclick="exportPending()">导出未发送收件人</button>
                <button class="btn" onclick="exportSent()">导出已发送收件人</button>
                <button class="btn" onclick="continueTask()">继续上次任务</button>
                <div class="card" style="margin-top:10px;">
                    <h3>收件箱列表</h3>
                    <table id="recipientsTable">
                        <thead><tr><th>Email</th><th>Name</th><th>Real Name</th><th>操作</th></tr></thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
            <div id="sendPage" style="display:none;">
                <h2>邮件发送</h2>
                <div class="card">
                    <label>主题:</label><br>
                    <input type="text" id="subject" style="width:100%" placeholder="请输入主题, 可用 {name} {real_name}">
                    <br><br>
                    <label>正文:</label><br>
                    <textarea id="body" style="width:100%;height:150px;" placeholder="请输入正文, 可用 {name} {real_name}"></textarea>
                    <br><br>
                    <label>发送间隔(秒):</label>
                    <input type="number" id="interval" value="5" style="width:60px;">
                    <button class="btn" onclick="startSend()">开始发送</button>
                    <button class="btn" onclick="pauseSend()">暂停</button>
                    <button class="btn" onclick="resumeSend()">继续</button>
                    <button class="btn" onclick="stopSend()">停止</button>
                </div>
                <div class="card" style="margin-top:10px;">
                    <h3>实时发送进度</h3>
                    <ul id="sendLog"></ul>
                    <h3>账号发送统计</h3>
                    <ul id="accountUsage"></ul>
                </div>
            </div>
        </div>
        <script>
            function showPage(page){
                document.getElementById('recipientsPage').style.display = page==='recipients'?'block':'none';
                document.getElementById('sendPage').style.display = page==='send'?'block':'none';
                if(page==='recipients'){ loadRecipients(); }
            }

            function uploadCSV(){
                const file = document.getElementById('csvFile').files[0];
                if(!file){ alert("请选择文件"); return; }
                const formData = new FormData();
                formData.append('file', file);
                fetch('/upload-csv', {method:'POST', body:formData})
                .then(res=>res.json())
                .then(data=>{
                    alert(data.message);
                    loadRecipients();
                });
            }

            function loadRecipients(){
                fetch('/recipients').then(res=>res.json()).then(data=>{
                    const tbody = document.querySelector('#recipientsTable tbody');
                    tbody.innerHTML = '';
                    data.pending.forEach((r,i)=>{
                        const tr = document.createElement('tr');
                        tr.innerHTML = `<td>${r.email}</td><td>${r.name||''}</td><td>${r.real_name||''}</td>
                        <td><button onclick="deleteRecipient('${r.email}')">删除</button></td>`;
                        tbody.appendChild(tr);
                    });
                });
            }

            function deleteRecipient(email){
                fetch('/delete-recipient', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email})})
                .then(res=>res.json()).then(data=>{ alert(data.message); loadRecipients(); });
            }

            function clearRecipients(){
                fetch('/clear-recipients', {method:'POST'}).then(res=>res.json()).then(data=>{ alert(data.message); loadRecipients(); });
            }

            function downloadTemplate(){ window.location.href="/download-template"; }
            function exportPending(){ window.location.href="/download-recipients?status=pending"; }
            function exportSent(){ window.location.href="/download-recipients?status=sent"; }
            function continueTask(){ window.location.href="/continue-task"; }

            let evtSource;
            function startSend(){
                const subject = document.getElementById('subject').value;
                const body = document.getElementById('body').value;
                const interval = parseInt(document.getElementById('interval').value);
                if(!subject || !body){ alert("请填写主题和正文"); return; }
                fetch('/send', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({subject,body,interval})})
                .then(res=>res.json()).then(data=>{ alert(data.message); });
                startEventSource();
            }

            function startEventSource(){
                evtSource = new EventSource('/send-stream');
                const log = document.getElementById('sendLog');
                const usage = document.getElementById('accountUsage');
                log.innerHTML=''; usage.innerHTML='';
                evtSource.onmessage = function(e){
                    const d = JSON.parse(e.data);
                    if(d.log) log.innerHTML += `<li>${d.log}</li>`;
                    if(d.usage){
                        usage.innerHTML='';
                        for(const acc in d.usage){
                            usage.innerHTML += `<li>${acc}: ${d.usage[acc]}</li>`;
                        }
                    }
                }
            }

            function pauseSend(){ fetch('/pause-send', {method:'POST'}); }
            function resumeSend(){ fetch('/resume-send', {method:'POST'}); }
            function stopSend(){ fetch('/stop-send', {method:'POST'}); }
        </script>
    </body>
    </html>
    """
    return render_template_string(template)

# ================== 继续上次任务接口 ==================
@app.route("/continue-task")
def continue_task():
    global SEND_QUEUE, IS_SENDING, PAUSED
    if RECIPIENTS:
        SEND_QUEUE.append({"subject":"继续上次任务","body":"继续上次任务邮件","interval":5})
        IS_SENDING = True
        PAUSED = False
    return jsonify({"message":"已加载上次未完成任务，可开始发送"})


# ================== 以下接口和之前版本一样 ==================
# /upload-csv /recipients /delete-recipient /clear-recipients
# /download-template /download-recipients
# /send /pause-send /resume-send /stop-send /send-stream
# ... （省略，为节省篇幅，可直接沿用我上一个完整版本）
# 启动
if __name__ == "__main__":
    load_recipients()
    port = int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
