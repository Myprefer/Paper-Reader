# PaperReader

> AI 驱动的学术论文管理与阅读工具

PaperReader 是一款本地优先的桌面应用，专为研究人员设计，将 PDF 阅读、双语对照、AI 笔记生成、AI 配图生成与 AI 问答整合于同一界面。所有数据存储在本地，无需云端账号。

![screenshot](docs/screenshot.png)

---

## ✨ 功能亮点

| 功能 | 描述 |
|------|------|
| **论文管理** | 树形文件夹组织，支持拖拽移动、批量导入 |
| **双语 PDF** | 中英文 PDF 并排对照阅读 |
| **AI 笔记** | 调用 Gemini 对论文生成结构化中文讲解笔记（流式输出）|
| **AI 配图** | 让 Gemini 为论文核心概念生成可视化插图 |
| **AI 问答** | 基于 PDF 全文的多轮对话，支持图片上传 |
| **插图管理** | 每篇论文的配图库，支持中英双版本对照 |
| **离线优先** | 除 AI 接口外全部本地运行，数据存于 `~/Documents/PaperReader/` |

---

## 🖥️ 技术栈

**后端**
- Python 3.10+
- Flask + Flask-CORS
- SQLite（通过标准库 `sqlite3`）
- Google Gemini API（`google-genai`）
- PyMuPDF（ArXiv ID 提取）

**前端**
- React 19 + TypeScript
- Vite 6
- Zustand（状态管理）
- marked + KaTeX + highlight.js（Markdown 渲染）

**桌面封装**
- pywebview（原生窗口）
- PyInstaller + Inno Setup（Windows 安装包）

---

## 🚀 快速开始

### 前提条件

- Python 3.10+
- Node.js 18+
- [Gemini API Key](https://aistudio.google.com/apikey)（AI 功能必需）

### 1. 克隆并安装依赖

```bash
git clone https://github.com/your-username/paper-reader.git
cd paper-reader

# Python 依赖
pip install -r requirements.txt

# 前端依赖
cd frontend
npm install
cd ..
```

### 2. 配置 API Key

```bash
# Windows (PowerShell)
$env:GEMINI_API_KEY = "your-api-key-here"

# Linux / macOS
export GEMINI_API_KEY="your-api-key-here"
```

也可在项目根目录创建 `.env` 文件：

```
GEMINI_API_KEY=your-api-key-here
```

### 3. 构建前端

```bash
cd frontend
npm run build
cd ..
```

### 4. 启动应用

**桌面模式（推荐）**

```bash
python desktop.py
```

**纯 Web 服务模式**（用浏览器访问 `http://localhost:5000`）

```bash
python -m flask --app backend.app run
```

---

## 📦 打包为 Windows 安装程序

需要先完成前端构建，然后执行：

```bash
build.bat
```

脚本将依次：
1. 构建前端（`vite build`）
2. 使用 PyInstaller 打包为 `dist/PaperReader/`
3. 使用 Inno Setup 生成 `installer_output/PaperReader_Setup_1.1.0.exe`

> Inno Setup 需单独安装：https://jrsoftware.org/isinfo.php

---

## 📁 项目结构

```
paper-reader/
├── backend/                # Flask 后端
│   ├── app.py              # 应用工厂
│   ├── config.py           # 路径与配置
│   ├── db.py               # SQLite 模式与连接管理
│   ├── routes/             # API 路由蓝图
│   │   ├── papers.py       # 论文 CRUD、PDF 服务、ArXiv 获取
│   │   ├── notes.py        # 笔记 CRUD、AI 笔记生成
│   │   ├── images.py       # 插图 CRUD、AI 图片生成
│   │   ├── chat.py         # AI 问答会话
│   │   └── tree.py         # 文件夹树
│   └── services/
│       └── gemini.py       # Gemini 客户端与限速封装
├── frontend/               # React 前端
│   ├── src/
│   │   ├── components/     # UI 组件（Sidebar、PDFPanel、RightPanel 等）
│   │   ├── store/          # Zustand 全局状态
│   │   ├── api/            # 后端 API 调用封装
│   │   └── types/          # TypeScript 类型定义
│   └── package.json
├── assets/                 # 应用图标
├── scripts/                # 开发辅助脚本
├── desktop.py              # 桌面应用入口（pywebview）
├── build.spec              # PyInstaller 打包配置
├── build.bat               # 一键打包脚本（Windows）
├── installer.iss           # Inno Setup 安装包脚本
└── requirements.txt        # Python 依赖
```

### 运行时数据目录

应用运行后，用户数据存储于 `~/Documents/PaperReader/`：

```
~/Documents/PaperReader/
├── data/papers.db    # SQLite 数据库
├── pdfs/             # 英文 PDF
├── pdfs_zh/          # 中文 PDF
├── notes/            # Markdown 笔记
├── images/           # AI 生成插图（英文）
├── images_zh/        # AI 生成插图（中文）
└── chat_images/      # 对话中上传的图片
```

---

## 🗄️ 数据迁移

如果已有按文件夹组织的 PDF，可用以下脚本导入：

```bash
# 从项目目录（pdfs/ notes/ images/ 等）导入
python import_data.py

# 从指定目录导入
python import_data.py --source D:\path\to\my-papers
```

---

## 📋 API 概览

| Method | Path | 描述 |
|--------|------|------|
| `GET` | `/api/tree` | 获取文件夹树 |
| `GET/POST` | `/api/papers` | 论文列表 / 创建 |
| `GET` | `/api/papers/:id/pdf/<lang>` | 获取 PDF（en/zh）|
| `POST` | `/api/papers/:id/fetch-zh` | 从 ArXiv 下载中文版 |
| `GET/POST` | `/api/papers/:id/notes` | 笔记列表 / 创建 |
| `POST` | `/api/notes/:id/generate` | AI 生成笔记（流式）|
| `GET/POST` | `/api/papers/:id/images` | 插图列表 / 创建 |
| `POST` | `/api/papers/:id/images/generate` | AI 生成插图 |
| `GET/POST` | `/api/papers/:id/chat-sessions` | 对话会话管理 |
| `POST` | `/api/chat-sessions/:id/messages` | 发送消息（流式）|

---

## ⚙️ 配置说明

所有配置均在 `backend/config.py` 中，主要通过环境变量覆盖：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `GEMINI_API_KEY` | `""` | Gemini API 密钥 |

数据目录、模型名称等可直接修改 `config.py`。

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m 'Add some feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 创建 Pull Request

---

## 📄 许可证

[MIT License](LICENSE)

Copyright © 2026 Myprefer
