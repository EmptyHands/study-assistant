# 对话上下文管理系统 — 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将对话历史管理从"按条数截取"改造为基于 token 计数的滑动窗口 + 摘要双层结构（ActiveBuffer + BackgroundKnowledge + ConversationContext）。

**Architecture:** 双组件 + 协调器模式。ActiveBuffer 负责滑动窗口 + tiktoken 精确计数，BackgroundKnowledge 负责摘要生成（轻量 LLM 优先、降级主 LLM）与 DB 持久化，ConversationContext 组合两者对外提供统一入口。

**Tech Stack:** Python 3.10+, tiktoken, SQLAlchemy, OpenAI-compatible API, pytest

---

## 依赖顺序

```
Task 1: 配置层     ──► Task 3: LLM Adapter
Task 2: DB Model   ──► Task 5: BackgroundKnowledgeStore
Task 4: ActiveBuffer ──► Task 6: ConversationContext
Task 5: BackgroundKnowledgeStore ──► Task 6: ConversationContext
Task 6: ConversationContext ──► Task 7, 8, 9, 10
```

---

### Task 1: 配置层 — SummaryLLMConfig + CONTEXT_BUFFER_TOKENS

**Files:**
- Modify: `backend/core/config.py`
- Modify: `.env.example`

**Step 1: 在 config.py 中新增 SummaryLLMConfig**

在 `LLMConfig` dataclass 之后（约第 37 行后），添加：

```python
@dataclass
class SummaryLLMConfig:
    """摘要 LLM 独立配置 — 用于 BackgroundKnowledge 增量摘要"""
    enabled: bool = True
    provider: str = "ollama"
    model_name: str = "qwen2.5:3b"
    api_key: Optional[str] = None
    base_url: str = "http://localhost:11434/v1"
    timeout: int = 15
```

**Step 2: 在 AppConfig 中新增字段**

在 `AppConfig` dataclass（约第 64 行）添加：

```python
summary_llm: SummaryLLMConfig = field(default_factory=SummaryLLMConfig)
context_buffer_tokens: int = 4000
```

**Step 3: 在 AppConfig.__post_init__ 中加载环境变量**

在 `__post_init__` 末尾（约第 117 行后）添加：

```python
self.summary_llm.enabled = os.getenv("SUMMARY_LLM_ENABLED", "true").lower() == "true"
self.summary_llm.provider = os.getenv("SUMMARY_LLM_PROVIDER", "ollama")
self.summary_llm.model_name = os.getenv("SUMMARY_LLM_MODEL", "qwen2.5:3b")
self.summary_llm.api_key = os.getenv("SUMMARY_LLM_API_KEY", "")
self.summary_llm.base_url = os.getenv("SUMMARY_LLM_BASE_URL", "http://localhost:11434/v1")
self.summary_llm.timeout = int(os.getenv("SUMMARY_LLM_TIMEOUT", "15"))
self.context_buffer_tokens = int(os.getenv("CONTEXT_BUFFER_TOKENS", "4000"))
```

**Step 4: 更新 .env.example**

在 `AGENT_TIMEOUT=300` 之后添加：

```ini
# --- 对话上下文管理 ---
# 活跃缓冲区 token 上限
CONTEXT_BUFFER_TOKENS=4000
# 摘要 LLM（轻量模型，优先 Ollama 本地部署）
SUMMARY_LLM_ENABLED=true
SUMMARY_LLM_PROVIDER=ollama
SUMMARY_LLM_MODEL=qwen2.5:3b
SUMMARY_LLM_BASE_URL=http://localhost:11434/v1
SUMMARY_LLM_API_KEY=
SUMMARY_LLM_TIMEOUT=15
```

**Step 5: 验证**

Run: `python -c "from backend.core.config import get_config; c = get_config(); print(c.summary_llm); print(c.context_buffer_tokens)"`
Expected: 输出 SummaryLLMConfig 对象，context_buffer_tokens=4000

**Step 6: Commit**

```bash
git add backend/core/config.py .env.example
git commit -m "feat: add SummaryLLMConfig and context_buffer_tokens to config

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: DB Model — ProjectBackgroundKnowledge 表

**Files:**
- Modify: `backend/models/database.py`
- Modify: `backend/core/database.py:19`

**Step 1: 添加 ORM 模型**

在 `database.py` 末尾的 `DocumentChunk` 类之后，添加：

```python
class ProjectBackgroundKnowledge(Base):
    """项目背景知识 — 对话历史摘要持久化"""
    __tablename__ = "project_background_knowledge"

    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"),
                        primary_key=True, nullable=False)
    user_intents = Column(Text, default="")
    assistant_actions = Column(Text, default="")
    key_facts = Column(Text, default="")
    message_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
```

**Step 2: 在 init_database() 中注册**

修改 `backend/core/database.py` 第 19 行，在 import 列表中加入 `ProjectBackgroundKnowledge`：

```python
from backend.models.database import Project, LearningContent, QARecord, FeynmanSession, LearningLog, DocumentChunk, ProjectBackgroundKnowledge  # noqa
```

**Step 3: 验证表创建**

Run: `python -c "from backend.core.database import init_database; init_database(); print('OK')"`
Expected: 输出 OK，无报错，sqlite 文件中出现新表

**Step 4: Commit**

```bash
git add backend/models/database.py backend/core/database.py
git commit -m "feat: add ProjectBackgroundKnowledge ORM model

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: LLM Adapter — 支持创建独立摘要适配器

**Files:**
- Modify: `backend/core/llm_adapter.py`

**Step 1: 修改 LLMAdapter.__init__ 支持参数覆盖**

修改 `LLMAdapter.__init__` 签名（约第 14 行），添加可选覆盖参数：

```python
def __init__(self, model_name_override: str = None, base_url_override: str = None,
             api_key_override: str = None, temperature_override: float = None,
             max_tokens_override: int = None, timeout_override: int = None):
    config = get_config()
    self.model_name = model_name_override or config.llm.model_name
    self.temperature = temperature_override if temperature_override is not None else config.llm.temperature
    self.max_tokens = max_tokens_override or config.llm.max_tokens
    self.timeout = timeout_override or config.llm.timeout

    api_key = api_key_override or config.llm.api_key
    base_url = base_url_override or config.llm.base_url or "https://api.openai.com/v1"

    self.client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=float(self.timeout),
        max_retries=2,
    )
    logger.info(f"LLM adapter initialized: model={self.model_name}")
```

**Step 2: 添加工厂函数 get_summary_llm()**

在 `llm_adapter.py` 文件末尾（`get_llm()` 函数之后），添加：

```python
_summary_llm: Optional[LLMAdapter] = None


def get_summary_llm() -> Optional[LLMAdapter]:
    """获取摘要专用 LLM 适配器（优先轻量模型，降级主 LLM）"""
    global _summary_llm
    if _summary_llm is not None:
        return _summary_llm

    config = get_config()
    summary_cfg = config.summary_llm

    if not summary_cfg.enabled:
        return None

    # 尝试创建轻量 LLM 适配器
    try:
        _summary_llm = LLMAdapter(
            model_name_override=summary_cfg.model_name,
            base_url_override=summary_cfg.base_url,
            api_key_override=summary_cfg.api_key or config.llm.api_key,
            temperature_override=0.3,  # 摘要用低温度
            max_tokens_override=1000,
            timeout_override=summary_cfg.timeout,
        )
        logger.info(f"Summary LLM configured: {summary_cfg.model_name} via {summary_cfg.provider}")
        return _summary_llm
    except Exception as e:
        logger.warning(f"Summary LLM unavailable ({e}), falling back to main LLM")
        _summary_llm = get_llm()  # 降级到主 LLM
        return _summary_llm
```

**Step 3: 验证**

Run: `python -c "from backend.core.llm_adapter import get_llm, get_summary_llm; print(get_llm().model_name); print(get_summary_llm().model_name if get_summary_llm() else 'None')"`
Expected: 输出主 LLM 模型名和摘要 LLM 模型名（或 None）

**Step 4: Commit**

```bash
git add backend/core/llm_adapter.py
git commit -m "feat: add get_summary_llm() with fallback to main LLM

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: ActiveBuffer — 滑动窗口 + token 计数

**Files:**
- Create: `backend/utils/context/__init__.py`（先创建空文件）
- Create: `backend/utils/context/active_buffer.py`
- Create: `tests/test_active_buffer.py`

**Step 1: 创建目录和空 __init__.py**

```bash
mkdir -p backend/utils/context
touch backend/utils/context/__init__.py
```

**Step 2: Write the failing test**

Create `tests/test_active_buffer.py`:

```python
"""Tests for ActiveBuffer"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.utils.context.active_buffer import ActiveBuffer


class TestActiveBuffer:

    def test_empty_buffer_token_count(self):
        buf = ActiveBuffer(token_limit=4000)
        assert buf.token_count() == 0
        assert buf.remaining() == 4000

    def test_add_turn_increases_count(self):
        buf = ActiveBuffer(token_limit=4000)
        buf.add_turn("什么是量子力学？", "量子力学是研究微观粒子运动规律的物理学分支。")
        assert buf.token_count() > 0
        assert buf.remaining() < 4000

    def test_as_messages_format(self):
        buf = ActiveBuffer(token_limit=4000)
        buf.add_turn("问题1", "答案1")
        messages = buf.as_messages()
        assert len(messages) == 2
        assert messages[0] == {"role": "user", "content": "问题1"}
        assert messages[1] == {"role": "assistant", "content": "答案1"}

    def test_eviction_when_over_limit(self):
        buf = ActiveBuffer(token_limit=50, model_name="gpt-4o-mini")
        evicted = buf.add_turn("问题A" * 20, "答案A" * 20)
        assert evicted is None or len(evicted) == 0  # 第一条不驱逐

        evicted = buf.add_turn("问题B" * 20, "答案B" * 20)
        # 窗口超限，应该驱逐了第一部分
        assert evicted is not None
        assert len(evicted) > 0

    def test_keep_last_turn_protected(self):
        buf = ActiveBuffer(token_limit=30, model_name="gpt-4o-mini")
        buf.add_turn("Q1" * 20, "A1" * 20)
        evicted = buf.add_turn("Q2", "A2")
        # 最后一条 Q2/A2 不应被驱逐（保护最小值）
        messages = buf.as_messages()
        assert len(messages) >= 2  # 至少保留最后一轮

    def test_clear_resets_buffer(self):
        buf = ActiveBuffer(token_limit=4000)
        buf.add_turn("Q", "A")
        buf.clear()
        assert buf.token_count() == 0
        assert buf.as_messages() == []

    def test_model_fallback_encoding(self):
        # 未知模型降级为 cl100k_base
        buf = ActiveBuffer(token_limit=4000, model_name="unknown-model-xyz")
        buf.add_turn("Hello", "World")
        assert buf.token_count() > 0  # 不应崩溃
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/test_active_buffer.py -v`
Expected: FAIL — module not found

**Step 4: Write ActiveBuffer implementation**

Create `backend/utils/context/active_buffer.py`:

```python
"""ActiveBuffer — 基于 token 计数的滑动窗口"""
import logging
import tiktoken
from typing import Optional

logger = logging.getLogger(__name__)

# tiktoken 已知模型列表的替代编码器
_FALLBACK_ENCODING = "cl100k_base"


class ActiveBuffer:
    """活跃缓冲区 — 保留最近对话的完整原文，按 token 数管理窗口"""

    def __init__(self, token_limit: int = 4000, model_name: str = "gpt-4o-mini"):
        self.token_limit = token_limit
        self.model_name = model_name
        self._messages: list[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]
        self._encoder = self._get_encoder(model_name)

    def _get_encoder(self, model_name: str):
        """获取 tiktoken 编码器，未知模型降级为 cl100k_base"""
        try:
            return tiktoken.encoding_for_model(model_name)
        except KeyError:
            logger.debug(f"Model '{model_name}' not in tiktoken registry, using {_FALLBACK_ENCODING}")
            return tiktoken.get_encoding(_FALLBACK_ENCODING)

    def count_tokens(self, text: str) -> int:
        """计算单段文本的 token 数"""
        return len(self._encoder.encode(text))

    def token_count(self) -> int:
        """当前窗口内所有消息的总 token 数"""
        return sum(self.count_tokens(m["content"]) for m in self._messages)

    def remaining(self) -> int:
        """剩余可用 token 数"""
        return max(0, self.token_limit - self.token_count())

    def add_turn(self, question: str, answer: str) -> list[dict] | None:
        """
        添加一轮对话。若窗口超限则从头部驱逐。
        返回被驱逐的消息列表（可能为 None 或空列表）。
        """
        self._messages.append({"role": "user", "content": question})
        self._messages.append({"role": "assistant", "content": answer})

        evicted = self._evict_if_needed()
        return evicted if evicted else None

    def _evict_if_needed(self) -> list[dict]:
        """从头部逐条弹出消息直到 token 数回到阈值以下"""
        evicted = []
        min_keep = 2  # 至少保留最后 1 轮（2 条消息）

        while self.token_count() > self.token_limit and len(self._messages) > min_keep:
            evicted.append(self._messages.pop(0))

        if evicted:
            logger.debug(f"Evicted {len(evicted)} messages, "
                         f"remaining tokens: {self.token_count()}/{self.token_limit}")

        return evicted

    def as_messages(self) -> list[dict]:
        """按时间顺序返回窗口内所有消息"""
        return list(self._messages)

    def clear(self):
        """清空窗口（切换项目时用）"""
        self._messages.clear()
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_active_buffer.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add backend/utils/context/ tests/test_active_buffer.py
git commit -m "feat: add ActiveBuffer with tiktoken-based sliding window

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: BackgroundKnowledgeStore — 摘要生成与持久化

**Files:**
- Create: `backend/utils/context/background_knowledge.py`
- Create: `tests/test_background_knowledge.py`

**Step 1: 理解依赖**

- 依赖 Task 2 的 DB model `ProjectBackgroundKnowledge`
- 依赖 Task 3 的 `get_summary_llm()`
- 依赖 `get_db_session()` 进行 DB 操作

**Step 2: Write the failing test**

Create `tests/test_background_knowledge.py`:

```python
"""Tests for BackgroundKnowledge"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.utils.context.background_knowledge import BackgroundKnowledge, BackgroundKnowledgeStore


class TestBackgroundKnowledge:

    def test_empty_knowledge_format(self):
        bk = BackgroundKnowledge()
        store = BackgroundKnowledgeStore(project_id="test-project")
        formatted = store.format_for_prompt(bk)
        # 空摘要不应输出任何内容
        assert formatted == ""

    def test_partial_knowledge_format(self):
        bk = BackgroundKnowledge(
            user_intents="理解量子力学",
            key_facts="薛定谔方程是基础",
        )
        store = BackgroundKnowledgeStore(project_id="test-project")
        formatted = store.format_for_prompt(bk)
        assert "理解量子力学" in formatted
        assert "薛定谔方程是基础" in formatted
        assert "## 对话历史背景" in formatted

    def test_full_knowledge_format(self):
        bk = BackgroundKnowledge(
            user_intents="用户想学微积分",
            assistant_actions="助手讲解了导数的定义和几何意义",
            key_facts="用户已掌握极限概念",
            message_count=5,
        )
        store = BackgroundKnowledgeStore(project_id="test-project")
        formatted = store.format_for_prompt(bk)
        assert "用户想学微积分" in formatted
        assert "助手讲解了导数的定义和几何意义" in formatted
        assert "用户已掌握极限概念" in formatted

    def test_format_differs_when_empty_vs_populated(self):
        store = BackgroundKnowledgeStore(project_id="test-project")
        empty = store.format_for_prompt(BackgroundKnowledge())
        full = store.format_for_prompt(BackgroundKnowledge(
            user_intents="test", assistant_actions="test", key_facts="test"
        ))
        assert empty != full
        assert len(full) > len(empty)
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/test_background_knowledge.py -v`
Expected: FAIL — module not found

**Step 4: Write BackgroundKnowledge implementation**

Create `backend/utils/context/background_knowledge.py`:

```python
"""BackgroundKnowledge — 对话历史摘要的生成、持久化与格式化"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from backend.core.database import get_db_session
from backend.models.database import ProjectBackgroundKnowledge

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """你是一个对话摘要助手。请根据以下增量对话，更新历史摘要。

## 当前摘要
用户意图：{user_intents}
助手行动：{assistant_actions}
关键事实：{key_facts}

## 新增对话
{new_messages}

## 输出要求
请以 JSON 格式输出更新后的摘要，包含以下三个字段：
- user_intents: 用户的主要问题和目标
- assistant_actions: 助手提供了哪些信息或执行了哪些操作
- key_facts: 对话中确认的重要事实、决定或偏好

请确保摘要简洁，保留所有关键信息，不要编造内容。
输出格式：{{"user_intents": "...", "assistant_actions": "...", "key_facts": "..."}}"""


@dataclass
class BackgroundKnowledge:
    """背景知识 — 窗口外历史的压缩摘要"""
    user_intents: str = ""
    assistant_actions: str = ""
    key_facts: str = ""
    message_count: int = 0
    last_updated: Optional[datetime] = None


class BackgroundKnowledgeStore:
    """背景知识存储 — 负责摘要的生成、DB 读写、格式化"""

    def __init__(self, project_id: str):
        self.project_id = project_id

    # ── DB 操作 ──

    def load(self) -> Optional[BackgroundKnowledge]:
        """从 DB 加载已有摘要"""
        db = get_db_session()
        try:
            row = db.query(ProjectBackgroundKnowledge).filter(
                ProjectBackgroundKnowledge.project_id == self.project_id
            ).first()
            if row is None:
                return None
            return BackgroundKnowledge(
                user_intents=row.user_intents or "",
                assistant_actions=row.assistant_actions or "",
                key_facts=row.key_facts or "",
                message_count=row.message_count or 0,
                last_updated=row.updated_at,
            )
        finally:
            db.close()

    def save(self, knowledge: BackgroundKnowledge):
        """写入 DB（upsert）"""
        db = get_db_session()
        try:
            row = db.query(ProjectBackgroundKnowledge).filter(
                ProjectBackgroundKnowledge.project_id == self.project_id
            ).first()
            if row:
                row.user_intents = knowledge.user_intents
                row.assistant_actions = knowledge.assistant_actions
                row.key_facts = knowledge.key_facts
                row.message_count = knowledge.message_count
                row.updated_at = datetime.utcnow()
            else:
                row = ProjectBackgroundKnowledge(
                    project_id=self.project_id,
                    user_intents=knowledge.user_intents,
                    assistant_actions=knowledge.assistant_actions,
                    key_facts=knowledge.key_facts,
                    message_count=knowledge.message_count,
                )
                db.add(row)
            db.commit()
        finally:
            db.close()

    # ── 摘要生成 ──

    async def update(self, evicted_messages: list[dict]) -> BackgroundKnowledge:
        """
        增量更新摘要：加载现有摘要 → 调用 LLM 合并驱逐消息 → 保存并返回
        """
        current = self.load() or BackgroundKnowledge()

        # 格式化驱逐消息
        new_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content']}"
            for m in evicted_messages
        )

        prompt = SUMMARY_PROMPT.format(
            user_intents=current.user_intents or "（无）",
            assistant_actions=current.assistant_actions or "（无）",
            key_facts=current.key_facts or "（无）",
            new_messages=new_text,
        )

        # 调用摘要 LLM
        try:
            from backend.core.llm_adapter import get_summary_llm
            llm = get_summary_llm()
            if llm is None:
                logger.warning("No summary LLM available, skipping summarization")
                return current

            response = await llm.ainvoke(prompt)
            data = self._parse_summary_response(response)

            updated = BackgroundKnowledge(
                user_intents=data.get("user_intents", current.user_intents),
                assistant_actions=data.get("assistant_actions", current.assistant_actions),
                key_facts=data.get("key_facts", current.key_facts),
                message_count=current.message_count + len(evicted_messages),
                last_updated=datetime.utcnow(),
            )

            self.save(updated)
            logger.info(f"Summary updated for project {self.project_id}, "
                        f"total messages summarized: {updated.message_count}")
            return updated

        except Exception as e:
            logger.warning(f"Summary LLM call failed: {e}, keeping existing summary")
            return current

    def _parse_summary_response(self, response: str) -> dict:
        """从 LLM 响应中解析 JSON 摘要"""
        # 尝试直接解析
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        # 尝试提取 ```json ... ``` 块
        import re
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # 尝试找最外层的 {}
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            try:
                return json.loads(response[start:end])
            except json.JSONDecodeError:
                pass
        logger.warning(f"Failed to parse summary response: {response[:200]}")
        return {}

    # ── 格式化 ──

    def format_for_prompt(self, knowledge: BackgroundKnowledge) -> str:
        """将摘要格式化为可注入 system prompt 的文本"""
        parts = []
        if knowledge.user_intents:
            parts.append(f"- 用户之前关心的问题: {knowledge.user_intents}")
        if knowledge.assistant_actions:
            parts.append(f"- 之前已讨论的内容: {knowledge.assistant_actions}")
        if knowledge.key_facts:
            parts.append(f"- 已确认的事实: {knowledge.key_facts}")

        if not parts:
            return ""

        return "## 对话历史背景\n" + "\n".join(parts)
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_background_knowledge.py -v`
Expected: ALL PASS（format 相关测试不依赖 DB/LLM）

**Step 6: Commit**

```bash
git add backend/utils/context/background_knowledge.py tests/test_background_knowledge.py
git commit -m "feat: add BackgroundKnowledgeStore for summary generation and persistence

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: ConversationContext 协调器

**Files:**
- Create: `backend/utils/context/conversation_context.py`
- Create: `tests/test_conversation_context.py`

**Step 1: Write the failing test**

Create `tests/test_conversation_context.py`:

```python
"""Tests for ConversationContext"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.utils.context.conversation_context import ConversationContext


class TestConversationContext:

    def test_init_creates_buffer(self):
        ctx = ConversationContext(project_id="test-ctx-1")
        assert ctx.buffer is not None
        assert ctx.store is not None
        assert ctx.project_id == "test-ctx-1"

    def test_add_turn_no_summary_needed(self):
        """添加少量对话不触发摘要"""
        ctx = ConversationContext(project_id="test-ctx-2", token_limit=4000)
        ctx.add_turn("Hello", "Hi there!")
        assert ctx.buffer.token_count() > 0

    def test_build_chat_history_empty(self):
        ctx = ConversationContext(project_id="test-ctx-3")
        history = ctx.build_chat_history()
        assert history == []

    def test_build_chat_history_with_turns(self):
        ctx = ConversationContext(project_id="test-ctx-4")
        ctx.add_turn("Q1", "A1")
        ctx.add_turn("Q2", "A2")
        history = ctx.build_chat_history()
        assert len(history) == 4
        assert history[0] == {"role": "user", "content": "Q1"}
        assert history[-1] == {"role": "assistant", "content": "A2"}

    def test_build_system_prompt_addition_empty(self):
        ctx = ConversationContext(project_id="test-ctx-5")
        addition = ctx.build_system_prompt_addition()
        assert addition == ""  # 没有背景知识时返回空字符串

    def test_custom_token_limit(self):
        ctx = ConversationContext(project_id="test-ctx-6", token_limit=30)
        ctx.add_turn("A" * 100, "B" * 100)
        # 窗口应该被限制
        history = ctx.build_chat_history()
        total_chars = sum(len(m["content"]) for m in history)
        assert total_chars < 500  # 至少比原始输入少很多
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_conversation_context.py -v`
Expected: FAIL — module not found

**Step 3: Write ConversationContext implementation**

Create `backend/utils/context/conversation_context.py`:

```python
"""ConversationContext — 对话上下文协调器"""
import logging
from .active_buffer import ActiveBuffer
from .background_knowledge import BackgroundKnowledgeStore

logger = logging.getLogger(__name__)


class ConversationContext:
    """对话上下文 — 组合 ActiveBuffer + BackgroundKnowledgeStore

    使用方式:
        ctx = ConversationContext(project_id)
        # 构建 system prompt（含背景知识）
        system_prompt = base_prompt + ctx.build_system_prompt_addition()
        # 构建用户 prompt（含最近对话）
        chat_history = ctx.build_chat_history()
        # ... LLM 调用 ...
        # 保存本轮对话
        ctx.add_turn(question, answer)
    """

    def __init__(self, project_id: str, token_limit: int = 4000,
                 model_name: str = "gpt-4o-mini"):
        self.project_id = project_id
        self.buffer = ActiveBuffer(token_limit=token_limit, model_name=model_name)
        self.store = BackgroundKnowledgeStore(project_id=project_id)
        self._summary_loaded = False
        self._background_text: str = ""

    def add_turn(self, question: str, answer: str):
        """
        添加一轮对话。同步方法 — 摘要生成是异步的但 add_turn 不等待。
        """
        evicted = self.buffer.add_turn(question, answer)

        if evicted:
            logger.debug(f"Evicted {len(evicted)} messages from buffer, "
                         f"scheduling summary update")
            # 触发摘要更新（fire-and-forget）
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._do_summarize(evicted))
            except RuntimeError:
                # 没有运行中的 event loop（同步上下文）
                asyncio.run(self._do_summarize(evicted))

    async def _do_summarize(self, evicted: list[dict]):
        """执行增量摘要（异步）"""
        self._background_text = ""  # 清除缓存
        await self.store.update(evicted)

    def build_system_prompt_addition(self) -> str:
        """返回要追加到 system prompt 的文本"""
        if self._background_text:
            return self._background_text

        knowledge = self.store.load()
        if knowledge is None:
            return ""

        self._background_text = self.store.format_for_prompt(knowledge)
        return self._background_text

    def build_chat_history(self) -> list[dict]:
        """返回活跃缓冲区中的消息列表"""
        return self.buffer.as_messages()

    async def flush(self):
        """强制保存摘要状态到 DB（项目删除/服务停止前）"""
        # 当前实现中摘要已在 _do_summarize 中即时保存
        # flush 作为未来扩展点保留
        pass
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_conversation_context.py -v`
Expected: ALL PASS（不依赖 DB 的测试）

**Step 5: Commit**

```bash
git add backend/utils/context/conversation_context.py tests/test_conversation_context.py
git commit -m "feat: add ConversationContext coordinator

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: 导出与清理

**Files:**
- Modify: `backend/utils/context/__init__.py`
- Delete: `backend/utils/context_manager.py`

**Step 1: 更新 __init__.py 导出**

Write to `backend/utils/context/__init__.py`:

```python
"""对话上下文管理 — ConversationContext"""
from .conversation_context import ConversationContext
from .active_buffer import ActiveBuffer
from .background_knowledge import BackgroundKnowledge, BackgroundKnowledgeStore

__all__ = ["ConversationContext", "ActiveBuffer", "BackgroundKnowledge", "BackgroundKnowledgeStore"]
```

**Step 2: 删除旧文件**

```bash
rm backend/utils/context_manager.py
```

**Step 3: 验证导入**

Run: `python -c "from backend.utils.context import ConversationContext, ActiveBuffer, BackgroundKnowledge; print('OK')"`
Expected: OK

**Step 4: Commit**

```bash
git add backend/utils/context/__init__.py
git rm backend/utils/context_manager.py
git commit -m "feat: export ConversationContext, remove old context_manager.py

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 集成到 QAAgent

**Files:**
- Modify: `backend/agents/qa_agent.py`

**Step 1: 修改 run() 方法**

将 `qa_agent.py` 中 `run()` 方法（第 29-103 行）的 history 处理改为使用 ConversationContext：

替换第 35 行：
```python
# 旧：
history = input_data.get("history", [])  # B1: 最近 QA 历史

# 新：
from backend.utils.context import ConversationContext
ctx = ConversationContext(project_id)
```

替换第 58-65 行：
```python
# 旧：
# B1: 注入对话历史，让 LLM 理解追问和指代
if history:
    history_lines = []
    for h in history[-3:]:
        history_lines.append(f"Q: {h.get('question', '')}")
        history_lines.append(f"A: {h.get('answer', '')[:300]}")
    if history_lines:
        prompt_parts.append("## 对话历史\n" + "\n".join(history_lines))

# 新：
# 注入活跃缓冲区中的最近对话
chat_history = ctx.build_chat_history()
if chat_history:
    history_lines = []
    for m in chat_history:
        prefix = "Q" if m["role"] == "user" else "A"
        history_lines.append(f"{prefix}: {m['content']}")
    prompt_parts.append("## 最近对话\n" + "\n".join(history_lines))
```

修改 system_prompt 的构建（第 94 行附近）：
```python
# 旧：
answer = await self.think(prompt, system_prompt=QA_SYSTEM_PROMPT)

# 新：
system_prompt = QA_SYSTEM_PROMPT + ctx.build_system_prompt_addition()
answer = await self.think(prompt, system_prompt=system_prompt)
```

在返回之前（约第 95 行后），添加：
```python
ctx.add_turn(question, answer)
```

**Step 2: 同步修改 stream_answer() 方法**

同样将 `stream_answer()`（第 106-182 行）改为使用 ConversationContext：

在方法开头（约第 112 行 "检索中..." yield 之后），添加：
```python
from backend.utils.context import ConversationContext
ctx = ConversationContext(project_id)
```

在 `yield {"type": "status", "text": "生成中..."}` 之前，插入最近对话到 prompt：
```python
chat_history = ctx.build_chat_history()
if chat_history:
    history_lines = []
    for m in chat_history:
        prefix = "Q" if m["role"] == "user" else "A"
        history_lines.append(f"{prefix}: {m['content']}")
    prompt_parts.append("## 最近对话\n" + "\n".join(history_lines))
```

修改 system_prompt（约第 171 行）并累积完整答案：
```python
# 旧：
async for chunk in llm.astream(prompt, system_prompt=QA_SYSTEM_PROMPT):

# 新：
system_prompt = QA_SYSTEM_PROMPT + ctx.build_system_prompt_addition()
full_answer = ""
try:
    async for chunk in llm.astream(prompt, system_prompt=system_prompt):
        full_answer += chunk
        yield {"type": "chunk", "text": chunk}
except Exception as e:
    ...

ctx.add_turn(question, full_answer)
```

**Step 3: 验证**

Run: `python -c "from backend.agents.qa_agent import QAAgent; a = QAAgent(); print('OK')"`
Expected: OK

**Step 4: Commit**

```bash
git add backend/agents/qa_agent.py
git commit -m "feat: integrate ConversationContext into QAAgent

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: 简化 QAService

**Files:**
- Modify: `backend/services/qa_service.py`

**Step 1: 移除手动取历史的代码**

在 `qa_service.py` `ask_question()` 函数中（第 27-46 行），删除以下块：

```python
# 删除这段（第 27-38 行）：
        # B1: 获取最近 QA 历史，供 Agent 理解多轮对话上下文
        recent_qa = (
            db.query(QARecord)
            .filter(QARecord.project_id == project_id)
            .order_by(QARecord.created_at.desc())
            .limit(5)
            .all()
        )
        history = [
            {"question": r.question, "answer": r.answer[:300]}
            for r in reversed(recent_qa)
        ]
```

同时修改 agent.run() 调用（第 40-46 行），不再传 history：
```python
# 旧：
        agent = QAAgent()
        result = await agent.run({
            "question": question,
            "project_id": project_id,
            "summary": summary,
            "raw_content": raw_content,
            "history": history,
        })

# 新：
        agent = QAAgent()
        result = await agent.run({
            "question": question,
            "project_id": project_id,
            "summary": summary,
            "raw_content": raw_content,
        })
```

**Step 2: 验证**

Run: `python -c "from backend.services.qa_service import ask_question, get_qa_history; print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add backend/services/qa_service.py
git commit -m "refactor: remove manual history loading from qa_service

Now handled by ConversationContext inside QAAgent.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 10: 端到端测试 — 完整流程验证

**Step 1: 验证环境准备**

Run: `python -c "
from backend.core.config import get_config
from backend.core.database import init_database
init_database()
from backend.utils.context import ConversationContext
ctx = ConversationContext('test-e2e')
ctx.add_turn('测试问题', '测试回答')
print('上下文消息数:', len(ctx.build_chat_history()))
print('System prompt 追加:', repr(ctx.build_system_prompt_addition()))
"`
Expected: 输出上下文消息数和空 system prompt 追加（因为没有摘要触发）

**Step 2: 验证集成不破坏现有功能**

Run: `python -m pytest tests/test_api.py -v --tb=short`
Expected: 现有 API 测试仍然 PASS

**Step 3: 运行所有新增测试**

Run: `python -m pytest tests/test_active_buffer.py tests/test_background_knowledge.py tests/test_conversation_context.py -v`
Expected: ALL PASS

**Step 4: 运行全部测试套件**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git commit -m "test: verify end-to-end context integration passes all tests

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 影响范围总结

| 文件 | 变更类型 |
|---|---|
| `backend/utils/context/__init__.py` | **Create** |
| `backend/utils/context/active_buffer.py` | **Create** |
| `backend/utils/context/background_knowledge.py` | **Create** |
| `backend/utils/context/conversation_context.py` | **Create** |
| `tests/test_active_buffer.py` | **Create** |
| `tests/test_background_knowledge.py` | **Create** |
| `tests/test_conversation_context.py` | **Create** |
| `backend/utils/context_manager.py` | **Delete** |
| `backend/models/database.py` | Modify — add `ProjectBackgroundKnowledge` |
| `backend/core/database.py` | Modify — register new model |
| `backend/core/config.py` | Modify — add `SummaryLLMConfig`, `context_buffer_tokens` |
| `backend/core/llm_adapter.py` | Modify — add `get_summary_llm()`, override params |
| `backend/agents/qa_agent.py` | Modify — integrate `ConversationContext` |
| `backend/services/qa_service.py` | Modify — remove manual history |
| `.env.example` | Modify — add 7 new entries |
