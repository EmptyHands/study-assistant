# Study Assistant — 智能学习辅助工具

基于多智能体架构的本地学习助手，前后端分离，支持多种学习材料导入，自动生成结构化讲解，提供问答和费曼学习法交互。

## 能做什么

### 导入学习材料

支持三种方式导入学习项目：

- **本地文件** — 上传 PDF 教材、DOCX 论文、TXT 笔记、代码文件、图片，或整个项目文件夹
- **Git 仓库** — 提供仓库地址，自动克隆并解析所有代码文件
- **概念/主题** — 直接输入一个概念（如"RAG 检索增强生成"），AI 围绕它构建学习内容

### 智能可学性判断

导入后 Agent 先判断内容是否值得学习。适合学习的内容会被识别（教材、论文、代码项目、结构化文档等），不适合的会被拒绝（发票、广告、资源汇总仓库、零散笔记等），并给出理由。

### 框架分析

Agent 自动提取学习项目的整体结构。对于算法概念会画出逻辑流程，对于教材会梳理章节脉络，对于代码项目会分析模块关系和 API 架构。

### SQ3R 结构化讲解

按 SQ3R 阅读法组织内容：

1. **Survey（概览）** — 学习目标与整体结构
2. **Question（问题引导）** — 围绕主题的核心问题，带着问题去读
3. **Read（详细讲解）** — 分章节的深入讲解，支持 Markdown、代码块、表格
4. **Recite（要点回顾）** — 关键知识点总结
5. **Review（复习建议）** — 练习建议与自测题目

所有讲解内容持久化存储，关闭重启后可直接阅读。

### 智能问答

基于三层体系的问答：

- **学习摘要层** — 直接从已生成的结构化讲解中回答
- **RAG 检索层** — 查询原始文档的向量索引，回答细节问题
- **网络搜索层** — 联网搜索补充最新信息

问答记录自动保存，方便回溯。

### 费曼学习法

AI 扮演一个完全不了解该主题但充满好奇心的学生。它会从最基础的问题开始，由浅入深地追问。用户作为"老师"来讲解，AI 会：

- 指出讲解中不准确的地方并纠正
- 追问模糊的概念
- 在用户表示不清楚时耐心解答
- 结束后总结薄弱点

对话记录全部保存，作为学习日志的一部分。

### 学习日志

每次使用问答或费曼学习后，Agent 自动整理：

- 知识点掌握情况梳理
- 薄弱点识别与针对性建议
- 学习进度评级
- 按日期组织的时间线

### 内容更新

一键触发 Agent 补充之前的学习讲解。只做补充，不做修改，不删除原有内容。Agent 还会检查讲解和日志的新鲜度，如果太久没更新会提醒。

### 多项目管理

支持创建多个学习项目，可重命名、删除、切换。所有数据（讲解、问答历史、费曼记录、日志）按项目隔离存储。

## 项目结构

```
study-assistant/
├── backend/
│   ├── main.py                    # FastAPI 入口，生命周期管理
│   ├── core/
│   │   ├── config.py              # 配置管理（.env + dataclass）
│   │   ├── database.py            # SQLAlchemy + SQLite
│   │   ├── exceptions.py          # 异常体系
│   │   ├── llm_adapter.py         # LLM 抽象层（OpenAI 兼容）
│   │   └── vector_store.py        # Qdrant 向量存储（支持 local/ollama/openai embedding）
│   ├── agents/
│   │   ├── base.py                # Agent 基类（含鲁棒 JSON 解析）
│   │   ├── learnability_agent.py  # 可学性判断
│   │   ├── framework_agent.py     # 框架分析
│   │   ├── explanation_agent.py   # SQ3R 讲解生成
│   │   ├── qa_agent.py            # 三层问答（摘要+RAG+搜索）
│   │   ├── feynman_agent.py       # 费曼学习法（提问+评估+总结）
│   │   └── log_agent.py           # 学习日志整理+内容补充
│   ├── workflows/
│   │   ├── states.py              # LangGraph TypedDict 状态定义
│   │   └── learning_pipeline.py   # 主学习流程 (parse->check->framework->explain->save)
│   ├── api/routes/
│   │   ├── projects.py            # 项目管理 API
│   │   ├── learning.py            # 学习内容 API
│   │   ├── qa.py                  # 问答 API
│   │   ├── feynman.py             # 费曼学习 API
│   │   └── logs.py                # 学习日志 API
│   ├── services/                  # 业务逻辑层
│   ├── models/database.py         # ORM 模型（5 张表）
│   └── utils/
│       ├── file_parser.py         # PDF/DOCX/图片/TXT/代码解析
│       ├── git_handler.py         # Git 仓库克隆
│       └── web_search.py          # Tavily 网络搜索
├── frontend/
│   ├── index.html                 # SPA 主页面
│   └── static/
│       ├── css/style.css          # 完整样式系统（响应式布局）
│       └── js/app.js              # 前端应用逻辑
├── tests/                         # 测试用例
├── data/                          # 运行时数据（自动创建）
├── .env.example                   # 环境变量模板
├── requirements.txt               # Python 依赖
└── README.md
```

## 部署指南

### 环境要求

| 组件 | 说明 |
|------|------|
| Python | 3.10+ |
| Qdrant | 向量数据库，本地部署 |
| Ollama | （可选）本地 LLM 和 Embedding 模型 |
| Tesseract OCR | （可选）图片文字提取 |

### 1. 安装依赖

```bash
cd study-assistant
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入必要的配置：

```ini
# LLM（必填）
LLM_PROVIDER=openai
LLM_MODEL=deepseek-v4-pro
LLM_API_KEY=sk-your-api-key
LLM_BASE_URL=https://api.openai.com/v1

# Embedding（必填）
# 三种模式可选：local / ollama / openai
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_BASE_URL=http://localhost:11434

# Qdrant（必填）
QDRANT_HOST=localhost
QDRANT_PORT=6333

# 网络搜索（可选，不填则仅使用摘要和 RAG 回答）
SEARCH_API_KEY=tvly-your-key
```

### 3. 启动 Qdrant

```bash
# Docker 方式
docker run -p 6333:6333 qdrant/qdrant

# 或从 https://qdrant.tech/documentation/quickstart/ 下载本地二进制
```

### 4. 启动 Ollama（如使用本地模型）

```bash
# 拉取 embedding 模型
ollama pull nomic-embed-text

# Ollama 默认运行在 http://localhost:11434
```

### 5. 启动应用

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

浏览器打开 `http://127.0.0.1:8000` 即可使用。

### 6. 运行测试

```bash
pytest tests/ -v
```

## Embedding 模式对比

| 模式 | 配置值 | 推荐模型 | 优点 | 缺点 |
|------|--------|---------|------|------|
| Ollama 本地 | `ollama` | `nomic-embed-text` (768维) | 完全本地，不消耗 API | 需安装 Ollama |
| sentence-transformers | `local` | `all-MiniLM-L6-v2` (384维) | 纯 Python，自动下载 | 首次需下载模型 |
| OpenAI 兼容 API | `openai` | `text-embedding-3-small` (1536维) | 质量高，无需本地算力 | 消耗 API 额度 |

## API 速查

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/projects/import/file` | 上传本地文件 |
| POST | `/api/v1/projects/import/git` | 导入 Git 仓库 |
| POST | `/api/v1/projects/import/concept` | 创建概念项目 |
| GET | `/api/v1/projects` | 项目列表 |
| GET | `/api/v1/projects/{id}` | 项目详情（含学习内容） |
| PUT | `/api/v1/projects/{id}` | 重命名项目 |
| DELETE | `/api/v1/projects/{id}` | 删除项目 |
| POST | `/api/v1/learning/{id}/start` | 启动学习流程（LangGraph Pipeline） |
| GET | `/api/v1/learning/{id}/content` | 获取 SQ3R 内容 |
| POST | `/api/v1/learning/{id}/update` | 补充更新内容 |
| POST | `/api/v1/qa/{id}/ask` | 提问 |
| GET | `/api/v1/qa/{id}/history` | 问答历史 |
| POST | `/api/v1/feynman/{id}/start` | 开始费曼会话 |
| POST | `/api/v1/feynman/{id}/answer` | 提交回答 |
| POST | `/api/v1/feynman/{id}/confused` | 表示不清楚 |
| GET | `/api/v1/logs/{id}` | 学习日志列表 |
| POST | `/api/v1/logs/{id}/generate` | 生成本次学习日志 |
| GET | `/api/v1/logs/{id}/latest` | 最新学习摘要 |
| GET | `/health` | 健康检查 |

## 技术栈

- **后端框架** FastAPI + Uvicorn
- **AI 编排** LangGraph（状态图工作流）
- **LLM** OpenAI 兼容接口（支持 DeepSeek、Qwen、GPT、Ollama 等）
- **向量数据库** Qdrant（本地部署）
- **Embedding** 支持 Ollama / sentence-transformers / OpenAI 三种后端
- **关系数据库** SQLite（默认，可切换 PostgreSQL）
- **前端** 原生 JavaScript SPA（零框架依赖）
- **文件解析** pdfplumber + python-docx + Pillow + pytesseract

## 设计原则

- **分层架构** API -> Service -> Agent -> Core，职责清晰，易于扩展
- **异常处理** 全链路异常捕获，Agent 失败不阻塞主流程
- **持久化优先** 所有生成内容即时存储，重启不丢失
- **增量更新** 内容更新只补充不删除，保留用户的学习历史
- **模块化 Agent** 每个 Agent 职责单一，可独立替换或升级
