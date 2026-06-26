"""网络搜索集成"""
import logging
from typing import Optional
from backend.core.config import get_config

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """执行网络搜索，返回 [{title, url, snippet}]"""
    config = get_config()

    if not config.search.api_key:
        logger.warning("未配置搜索 API Key，跳过网络搜索")
        return []

    if config.search.api == "tavily":
        return await _tavily_search(query, max_results, config.search.api_key)
    else:
        logger.warning(f"不支持的搜索 API: {config.search.api}")
        return []


async def _tavily_search(query: str, max_results: int, api_key: str) -> list[dict]:
    try:
        from tavily import AsyncTavilyClient
        client = AsyncTavilyClient(api_key=api_key)
        response = await client.search(query=query, max_results=max_results, search_depth="basic")
        results = response.get("results", [])
        return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")} for r in results]
    except ImportError:
        logger.error("tavily-python 未安装")
        return []
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return []
