import os
import csv
import smtplib
import time
import random
import datetime
from flask import Flask, request, jsonify, render_template_string

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

# 收件箱列表（内存存储）
RECIPIENTS = []

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

# ========== Flask 路由 ==========
@app.route("/", methods=["GET"])
def home():
    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>MailBot 后台</title>
        <style>
            body { font-family: Arial, sans-serif; margin:0; padding:0; display:flex; height:100vh; background:#f5f5f5;}
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
                    data.forEach((r,i)=>{
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

            function startSend(){
                const subject = document.getElementById('subject').value;
                const body = document.getElementById('body').value;
                const interval = parseInt(document.getElementById('interval').value);
                if(!subject || !body){ alert("请填写主题和正文"); return; }
                fetch('/send', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({subject,body,interval})})
                .then(res=>res.json()).then(data=>{ alert(data.message); });
                const evtSource = new EventSource('/send-stream');
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
        </script>
    </body>
    </html>
    """
    return render_template_string(template)

# ========== 收件箱管理接口 ==========
@app.route("/upload-csv", methods=["POST"])
def upload_csv():
    global RECIPIENTS
    file = request.files.get('file')
    if not file: return jsonify({"message":"未上传文件"})
    try:
        stream = file.stream.read().decode('utf-8').splitlines()
        reader = csv.DictReader(stream)
        RECIPIENTS = []
        for row in reader:
            RECIPIENTS.append({
                "email": row.get("email"),
                "name": row.get("name"),
                "real_name": row.get("real_name")
            })
        return jsonify({"message":f"成功上传 {len(RECIPIENTS)} 条"})
    except Exception as e:
        return jsonify({"message":f"上传失败: {e}"})

@app.route("/recipients", methods=["GET"])
def get_recipients():
    return jsonify(RECIPIENTS)

@app.route("/delete-recipient", methods=["POST"])
def delete_recipient():
    global RECIPIENTS
    email = request.json.get('email')
    RECIPIENTS = [r for r in RECIPIENTS if r['email'] != email]
    return jsonify({"message":"已删除"})

@app.route("/clear-recipients", methods=["POST"])
def clear_recipients():
    global RECIPIENTS
    RECIPIENTS = []
    return jsonify({"message":"列表已清空"})

# ========== 邮件发送接口 ==========
SEND_QUEUE = []
@app.route("/send", methods=["POST"])
def start_send():
    global SEND_QUEUE
    data = request.json
    subject = data.get("subject")
    body = data.get("body")
    interval = data.get("interval", 5)
    if not subject or not body:
        return jsonify({"message":"主题或正文为空"})
    SEND_QUEUE = [{"subject":subject,"body":body,"interval":interval}]
    return jsonify({"message":"开始发送，请查看下方实时进度"})

@app.route("/send-stream")
def send_stream():
    def generate():
        global SEND_QUEUE, RECIPIENTS
        reset_daily_usage()
        while SEND_QUEUE:
            task = SEND_QUEUE.pop(0)
            subject_template = task['subject']
            body_template = task['body']
            interval = task['interval']
            new_recipients = RECIPIENTS.copy()
            for idx, person in enumerate(new_recipients, start=1):
                email = person['email']
                name = person.get('name') or ''
                real_name = person.get('real_name') or name
                acc = get_next_account()
                if not acc:
                    yield f"data:{jsonify({'log':'⚠️ 所有账号今日已达到上限','usage':account_usage}).get_data(as_text=True)}\n\n"
                    return
                msg = f"Olá {real_name}, 这是测试邮件"
                try:
                    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                    server.starttls()
                    server.login(acc["email"], acc["app_password"])
                    server.sendmail(acc["email"], email, msg)
                    server.quit()
                    account_usage[acc["email"]] += 1
                    RECIPIENTS = [r for r in RECIPIENTS if r['email'] != email]
                    log = f"✅ {idx}. 已发送 {email} （账号 {acc['email']}，今日已发 {account_usage[acc['email']]}）"
                except Exception as e:
                    log = f"❌ {idx}. 发送失败 {email}, 错误: {e}"
                yield f"data:{jsonify({'log':log,'usage':account_usage}).get_data(as_text=True)}\n\n"
                time.sleep(interval)
    return app.response_class(generate(), mimetype='text/event-stream')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
