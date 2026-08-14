# Recall AI 错题本 · 云端部署保姆级教程（路径 B）

> 目标：把"能用的 Recall"发布到公网，让任何人（同学/老师）打开链接就能用 **AI 答疑、拍照识题、AI 解析**。
> 全程只用浏览器 + GitHub 账号，约 20 分钟。看不懂就照做，每一步都有"✅ 做对了的样子"。

---

## 准备（3 分钟）

- [x] 一个 **GitHub 账号**（没有就去 https://github.com 用邮箱注册，验证邮箱）
- [x] 一个 **硅基流动账号 + API Key**（登录 https://cloud.siliconflow.cn → 密钥管理 → 创建密钥，`sk-` 开头）
- [x] 本地文件：`recall-backend-deploy.zip`（我给你的部署包）和 `recall-test.html`（单文件前端）

---

## 第 1 步：把后端代码传到 GitHub（8 分钟）

1. 打开 https://github.com → 登录
2. 右上角 **`+`** → **New repository**
3. 填：
   - Repository name：`recall-backend`（小写英文）
   - 选 **Public**
   - 勾选 **Add a README file**
   - 点绿色 **Create repository**
4. 进入新仓库页面 → 点 **Add file** → **Upload files**
5. **先把 `recall-backend-deploy.zip` 解压**（右键 → 全部解压缩），得到一个 `recall-backend-deploy` 文件夹
6. 把解压出来的**文件夹**直接拖进浏览器上传区（GitHub 会自动保留 app/ 子文件夹结构）
7. 页面下方 Commit message 随便填（如 `first deploy`）→ 点绿色 **Commit changes**
8. 等几秒，仓库里应能看到：`app/`（文件夹）、`requirements.txt`、`Procfile`、`railway.json`、`run.py`

✅ 成功标志：仓库首页能看到 `app` 文件夹和 `requirements.txt`
❌ 常见坑：只传了 zip 文件本身没解压 → 重新解压后再拖文件夹

---

## 第 2 步：在 Railway 部署后端（8 分钟）

1. 打开 https://railway.app → 点 **Login** → 选 **GitHub** 登录（会跳转授权，点 Approve）
2. 首次进入点 **New Project** → 选 **Deploy from GitHub repo**
3. 在仓库列表里选 **`recall-backend`** → 点 **Deploy Now**
4. 进入项目页面，看到 **Deployments** 面板在转圈构建（约 2-5 分钟），**点进最新一条看日志**（右上角 View Logs）
5. 日志末尾出现 `Application startup complete.` = 构建+启动成功

✅ 成功标志：Deployments 显示 **Active**，日志有 `Application startup complete`
❌ 常见坑：日志出现 `ModuleNotFoundError` → 把完整报错贴给我，我帮你改

---

## 第 3 步：配置 API Key（2 分钟）

1. 在项目页面左侧菜单点 **Variables**
2. 填两组：
   - **Variable Name**：`DEEPSEEK_API_KEY`，Value：粘贴你的硅基流动 `sk-...` Key
   - **Variable Name**：`DEEPSEEK_MODEL`，Value：`deepseek-ai/DeepSeek-V3.2`
3. 点 **Add**，Railway 会自动重新部署一次（等 Deployments 再次 Active）

> 说明：代码已支持从环境变量读 Key，云端不用写配置文件，Key 也不会出现在代码里。

---

## 第 4 步：生成公网域名（1 分钟）

1. 项目页面左侧菜单点 **Settings**
2. 找到 **Networking** 区域 → 点 **Generate Domain**
3. 生成类似 `https://recall-backend-production-xxxx.up.railway.app` 的地址
4. **复制这个地址，保存好**（后面要用）

✅ 成功标志：浏览器打开这个地址，显示 `{"status":"ok","ai_mode":"deepseek",...}`
❌ 常见坑：打开显示错误页面 → 回 Deployments 看日志；也可能只是还没部署完，等 1 分钟刷新

---

## 第 5 步：发布前端页面到 GitHub Pages（5 分钟）

1. 回到 GitHub → 右上角 `+` → **New repository** → 名字填 `recall` → Public → 勾 README → Create
2. 进仓库 → **Add file → Upload files** → 把 `recall-test.html` 拖进去，**重命名为 `index.html`** → Commit
3. 仓库顶部 **Settings** → 左侧 **Pages**
4. **Build and deployment** → Source 选 **Deploy from a branch** → Branch 选 `main`、目录 `/ (root)` → **Save**
5. 等 1-2 分钟，页面顶部出现：**Your site is live at `https://你的用户名.github.io/recall/`**

✅ 成功标志：打开该链接能看到 Recall 界面（此时 AI 功能还连不上，正常）

---

## 第 6 步：让前端连上云端后端（2 分钟）

1. 打开你的 Pages 链接（如 `https://你的用户名.github.io/recall/`）
2. 页面右下角找到 **🔧 测试面板**
3. 找到 **API 地址** 输入框 → 填入第 4 步保存的云端域名（**去掉结尾的 /api**，例如 `https://recall-backend-production-xxxx.up.railway.app`）
4. 点保存 → 刷新页面
5. 再打开测试面板 → 点 **一键测试 API 连接**

✅ 成功标志：显示 **"✅ 连接成功（X.X 秒）"**，AI 答疑能正常回复
❌ 常见坑：显示失败 → 检查地址有没有多打 `/api`；确认第 3 步 Key 填对了

---

## 第 7 步：验收 & 分享（2 分钟）

1. 在 AI 答疑发一道题 → 应流式回复（约 2-5 秒）
2. 拍照/上传/粘贴图片 → 应能 OCR 识别
3. 把 `https://你的用户名.github.io/recall/` 发给同学——他们打开就能用全部 AI 功能（不需要装任何东西）

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| Pages 打开但 AI 全挂 | 后端没连上 | 重做第 6 步，检查测试面板地址 |
| Railway 一直构建失败 | 依赖装不上 | 把构建日志（View Logs）发我 |
| 云端没有我本地的错题 | SQLite 在各自服务器 | 需要时我用脚本帮你迁移 `data/recall.db` |
| 想换 Key | 环境变量改了就行 | Variables 里更新 DEEPSEEK_API_KEY，自动重部署 |
| 免费额度用完 | Railway 每月 500 小时 | 学生一般够用；不够再上 Render/云服务器 |

---

**完成 🎉**：现在你有两个链接——
- 前端页面：`https://你的用户名.github.io/recall/`（给人看的）
- 后端 API：`https://recall-backend-production-xxxx.up.railway.app`（机器用的）

哪一步卡住了，把截图或日志贴给我，我帮你排。
