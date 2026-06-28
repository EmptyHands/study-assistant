"""
Study Assistant 核心配置模块
"""
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB = str(_PROJECT_ROOT / "data" / "study_assistant.db")

load_dotenv()


class LLMProvider(str, Enum):
    OPENAI = "openai"
    DASHSCOPE = "dashscope"
    OLLAMA = "ollama"


class EmbeddingProvider(str, Enum):
    OPENAI = "openai"
    LOCAL = "local"
    OLLAMA = "ollama"


@dataclass
class LLMConfig:
    provider: LLMProvider = LLMProvider.OPENAI
    model_name: str = "gpt-4o-mini"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4000
    timeout: int = 60


@dataclass
class EmbeddingConfig:
    provider: EmbeddingProvider = EmbeddingProvider.OPENAI
    model_name: str = "text-embedding-3-small"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    local_device: str = "cpu"


@dataclass
class QdrantConfig:
    host: str = "localhost"
    port: int = 6333
    api_key: Optional[str] = None
    collection_name: str = "study_assistant"


@dataclass
class SearchConfig:
    api: str = "tavily"
    api_key: Optional[str] = None


@dataclass
class AppConfig:
    app_name: str = "Study Assistant"
    debug: bool = False
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 8000

    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    search: SearchConfig = field(default_factory=SearchConfig)

    database_url: str = f"sqlite:///{_DEFAULT_DB}"
    agent_max_steps: int = 5
    agent_timeout: int = 300
    retrieval_top_k: int = 5

    def __post_init__(self):
        self.llm.provider = LLMProvider(os.getenv("LLM_PROVIDER", "openai"))
        self.llm.model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.llm.api_key = os.getenv("LLM_API_KEY")
        self.llm.base_url = os.getenv("LLM_BASE_URL")
        self.llm.temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        self.llm.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4000"))

        self.embedding.provider = EmbeddingProvider(os.getenv("EMBEDDING_PROVIDER", "openai"))
        self.embedding.model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self.embedding.api_key = os.getenv("EMBEDDING_API_KEY") or self.llm.api_key
        self.embedding.base_url = os.getenv("EMBEDDING_BASE_URL") or self.llm.base_url
        self.embedding.local_device = os.getenv("EMBEDDING_DEVICE", "cpu")

        self.qdrant.host = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant.port = int(os.getenv("QDRANT_PORT", "6333"))
        self.qdrant.api_key = os.getenv("QDRANT_API_KEY")

        self.search.api = os.getenv("SEARCH_API", "tavily")
        self.search.api_key = os.getenv("SEARCH_API_KEY")

        self.database_url = os.getenv("DATABASE_URL", "") or f"sqlite:///{_DEFAULT_DB}"
        self.host = os.getenv("APP_HOST", "127.0.0.1")
        self.port = int(os.getenv("APP_PORT", "8000"))
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.agent_max_steps = int(os.getenv("AGENT_MAX_STEPS", "5"))
        self.agent_timeout = int(os.getenv("AGENT_TIMEOUT", "300"))


_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = AppConfig()
    return _config
