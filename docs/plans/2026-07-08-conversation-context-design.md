# 对话上下文管理系统设计

**日期**: 2026-07-08
**状态**: 已批准
**分支**: master

---

## 1. 问题分析

当前做法（`qa_service.py` → `qa_agent.py`）：

| 位置 | 当前做法 |
|---|---|
| `qa_service.py:28-38` | 从 DB 取最近 **5 条** Q&A，反转顺序传入 Agent |
| `qa_agent.py:59-65` | `history[-3:]` 取最后 **3 条**，answer 截断到 300 字符 |
| `qa_agent.py:106-182` | `stream_answer` **完全没有用 history**（bug） |
| `base.py:17` | `self.history` 只存时间戳日志，不用于对话上下文 |

存在问题：

1. **按"条数"限制，而非 token 数** — 3 条长回答可能占 4000 token，3 条短回答可能只占 300 token
2. **tiktoken 在 requirements.txt 但从未被 import** — 已有依赖未利用
3. **没有摘要机制** — 历史要么全保留要么全丢弃，没有中间态
4. **Agent 基类的 self.history 浪费** — 只用于日志，不保存对话

另外，`feynman_agent.py` 也有类似的 `history[-6:]` 硬编码截取，此次改造应设计为可复用组件。

---

## 2. 方案选型

选择 **方案 B：双组件 + 协调器**（ActiveBuffer + BackgroundKnowledge + ConversationContext）。

- 方案 A（单类）被放弃：后期替换组件（tokenizer、摘要引擎）需要改动整个类
- 方案 C（Agent 级内置）被放弃：侵入 BaseAgent 太深，部分 Agent 不需要对话上下文
- 方案 B 的优势：组件边界即替换边界，每个组件可独立测试和替换

---

## 3. 设计决策

| 决策点 | 结论 |
|---|---|
| 摘要 LLM 配置 | 独立配置字段（`SUMMARY_LLM_*`），与主 LLM 解耦 |
| 生命周期 | 按项目持久化，摘要写入 DB，活跃缓冲区在内存 |
| 命名方式 | 按角色/功能命名，不描述实现方式 |
| 摘要注入位置 | system prompt（作为"已知背景"） |
| 摘要触发时机 | 驱逐时触发，立即写入 DB |

---

## 4. 架构概览

```
┌─────────────────────────────────────────────────┐
│                ConversationContext               │
│                  （对话上下文）                    │
│                                                  │
│  build_system_prompt_addition()                  │
│  build_chat_history()                            │
│  add_turn(question, answer)                      │
│  load() / flush()                                │
│                                                  │
│  ┌──────────────────┐  ┌──────────────────────┐ │
│  │   ActiveBuffer   │  │  BackgroundKnowledge │ │
│  │  （活跃缓冲区）    │  │    （背景知识）       │ │
│  │                  │  │                       │ │
│  │  token计数       │  │  摘要生成             │ │
│  │  消息进出滑动窗口  │  │  摘要持久化           │ │
│  │  溢出→触发摘要   │  │  格式化输出            │ │
│  └──────────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### 文件布局

```
backend/utils/
  context/
    __init__.py                 # 导出 ConversationContext
    active_buffer.py            # ActiveBuffer 类
    background_knowledge.py     # BackgroundKnowledge + BackgroundKnowledgeStore
    conversation_context.py     # ConversationContext 协调器
```

### 调用关系

- `backend/agents/qa_agent.py:6` → `from backend.utils.context import ConversationContext`
- `backend/agents/qa_agent.py:29` → `ctx = ConversationContext(project_id)` 在 `run()` 中
- `backend/agents/qa_agent.py:106` → 在 `stream_answer()` 中同上
- 后续 `feynman_agent.py` 同理接入

---

## 5. 组件设计

### 5.1 ActiveBuffer（活跃缓冲区）

维护滑动窗口内的完整对话原文。用 tiktoken 精确计数，窗口满时从头部溢出。

```python
class ActiveBuffer:
    def __init__(self, token_limit: int = 4000, model_name: str = "gpt-4o-mini")

    def add_turn(self, question: str, answer: str) -> list[dict] | None
    def token_count(self) -> int
    def remaining(self) -> int
    def as_messages(self) -> list[dict]
    def clear(self)
```

**驱逐策略**：
- `add_turn` 后若 `token_count > token_limit`，从头部逐条弹出
- 至少保留最后 2 条消息（1 轮 QA）不被驱逐
- 被驱逐的消息一次性返回给调用方

**Token 计数**：
- 使用 `tiktoken.encoding_for_model()` 获取编码器
- 模型名不在 tiktoken 已知列表中时，降级为 `cl100k_base`

### 5.2 BackgroundKnowledge（背景知识）

接收被驱逐的消息，增量更新摘要。调用轻量 LLM 生成结构化摘要，持久化到 DB。

```python
@dataclass
class BackgroundKnowledge:
    user_intents: str = ""         # 用户的主要问题和目标
    assistant_actions: str = ""    # 助手提供了哪些信息或执行了哪些操作
    key_facts: str = ""            # 对话中确认的重要事实、决定或偏好
    message_count: int = 0         # 已被摘要的消息总数
    last_updated: datetime = None

class BackgroundKnowledgeStore:
    def __init__(self, project_id: str)
    async def load(self) -> BackgroundKnowledge | None
    async def save(self, knowledge: BackgroundKnowledge)
    async def update(self, evicted_messages: list[dict]) -> BackgroundKnowledge
    def format_for_prompt(self, knowledge: BackgroundKnowledge) -> str
```

**摘要 LLM 策略**：
- 优先使用轻量 LLM（`SUMMARY_LLM_*` 配置）
- 连接超时/不可达时降级为主 LLM（`LLM_*` 配置）
- 摘要 prompt 要求输出 JSON 格式的三个维度（user_intents, assistant_actions, key_facts）

**DB 表**: `project_background_knowledge`

| 字段 | 类型 | 示例值 |
|---|---|---|
| `project_id` | String(36), PK, FK | `"abc123-def456"` |
| `user_intents` | Text | `"用户想理解量子力学中的波函数坍缩概念"` |
| `assistant_actions` | Text | `"助手用薛定谔的猫思想实验解释了测量问题"` |
| `key_facts` | Text | `"用户已掌握薛定谔方程的基本形式"` |
| `message_count` | Integer | `12` |
| `updated_at` | DateTime | `"2026-07-08T14:30:00"` |

### 5.3 ConversationContext（对话上下文）

组合 ActiveBuffer + BackgroundKnowledgeStore，对外提供唯一入口。

```python
class ConversationContext:
    def __init__(self, project_id: str, token_limit: int = 4000,
                 model_name: str = "gpt-4o-mini")

    async def add_turn(self, question: str, answer: str)
    def build_system_prompt_addition(self) -> str
    def build_chat_history(self) -> list[dict]
    async def flush(self)
```

---

## 6. 使用方式

### Agent 中

```python
# qa_agent.py
async def run(self, input_data: dict) -> dict:
    project_id = input_data.get("project_id", "")
    question = input_data.get("question", "")

    ctx = ConversationContext(project_id)

    # 背景知识注入 system prompt
    system_prompt = QA_SYSTEM_PROMPT + ctx.build_system_prompt_addition()

    # 活跃缓冲区拼入用户 prompt
    prompt_parts = [f"用户问题: {question}\n"]
    active_history = ctx.build_chat_history()
    if active_history:
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in active_history
        )
        prompt_parts.append(f"## 最近对话\n{history_text}")
    # ... 摘要、RAG、网络搜索

    answer = await self.think(prompt, system_prompt=system_prompt)
    await ctx.add_turn(question, answer)
    return {"answer": answer, ...}
```

### 服务层变化

- `qa_service.py` 不再手动取 DB 的 5 条记录、截断、传 history
- 替换为：从 DB 取历史 → 改为 Agent 内部通过 ConversationContext 处理

---

## 7. 配置项

新增到 `.env.example` 和 `config.py`：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `CONTEXT_BUFFER_TOKENS` | `4000` | 活跃缓冲区 token 上限 |
| `SUMMARY_LLM_PROVIDER` | `ollama` | 摘要 LLM 提供商 |
| `SUMMARY_LLM_MODEL` | `qwen2.5:3b` | 摘要 LLM 模型名 |
| `SUMMARY_LLM_BASE_URL` | `http://localhost:11434/v1` | 摘要 LLM API 地址 |
| `SUMMARY_LLM_API_KEY` | `""` | 摘要 LLM API key（Ollama 可为空） |
| `SUMMARY_LLM_TIMEOUT` | `15` | 摘要 LLM 超时秒数 |

---

## 8. 影响范围

| 文件 | 变更 |
|---|---|
| `backend/utils/context/` | **新增** — 子包，三个模块 |
| `backend/utils/context_manager.py` | **删除** — 替换为新实现 |
| `backend/models/database.py` | **修改** — 新增 `ProjectBackgroundKnowledge` 表 |
| `backend/core/config.py` | **修改** — 新增 `SummaryLLMConfig`，`CONTEXT_BUFFER_TOKENS` |
| `backend/core/llm_adapter.py` | **修改** — 支持创建独立的摘要 LLM 适配器 |
| `backend/agents/qa_agent.py` | **修改** — 集成 ConversationContext |
| `backend/services/qa_service.py` | **修改** — 移除手动取历史逻辑 |
| `.env.example` | **修改** — 新增 6 个配置项 |
