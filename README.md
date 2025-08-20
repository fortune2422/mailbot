# Python Gmail Mailer (Render 部署版)

## 使用方法
1. Fork 或上传此仓库到 GitHub
2. 在 Render 创建 **Cron Job**，绑定此仓库
3. 在 Render 的 Environment 里添加环境变量：
   - `EMAIL=你的Gmail账号`
   - `APP_PASSWORD=你的应用专用密码`
4. 上传或编辑 `emails.csv`，格式：
5. 设置 Cron 任务，例如 `0 9 * * *`（每天上午9点执行）
6. 部署完成后，每天会自动发邮件
