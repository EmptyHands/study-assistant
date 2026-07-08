"""父子块切分策略 — 纯文本处理，不感知存储"""
from dataclasses import dataclass, field


@dataclass
class ParentChunk:
    """父块：检索命中时返回给 LLM 的完整上下文"""
    index: int
    text: str


@dataclass
class ChildChunk:
    """子块：用于向量检索的精准匹配片段"""
    text: str
    parent_index: int
    parent_text: str


@dataclass
class ChunkResult:
    """父子块切分结果"""
    parents: list[ParentChunk] = field(default_factory=list)
    children: list[ChildChunk] = field(default_factory=list)


class ParentChildChunker:
    """父子块切分器 — ParentDocumentRetriever 策略"""

    def __init__(self, parent_size: int = 1500, child_size: int = 300):
        self.parent_size = parent_size
        self.child_size = child_size

    def chunk(self, text: str) -> ChunkResult:
        """将文本切分为父子块结构"""
        if not text or not text.strip():
            return ChunkResult()

        # 第一步：按自然段落切分（双换行 \n\n）
        paragraphs = text.split("\n\n")

        # 第二步：生成父块（合并相邻段落，不超过 parent_size 字符）
        parents = self._merge_to_parents(paragraphs, max_size=self.parent_size)

        # 第三步：从父块中切子块（child_size 字符，带句子边界感知）
        children = []
        for pid, parent_text in enumerate(parents):
            subs = self._split_to_children(parent_text, size=self.child_size)
            for sub in subs:
                children.append(ChildChunk(
                    text=sub,
                    parent_index=pid,
                    parent_text=parent_text,
                ))

        return ChunkResult(
            parents=[ParentChunk(index=i, text=t) for i, t in enumerate(parents)],
            children=children,
        )

    def _merge_to_parents(self, paragraphs: list[str], max_size: int) -> list[str]:
        """合并相邻段落为父块"""
        parents = []
        current = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if current and len(current) + len(para) + 2 > max_size:
                parents.append(current.strip())
                current = para
            else:
                current = (current + "\n\n" + para) if current else para
        if current.strip():
            parents.append(current.strip())
        return parents

    def _split_to_children(self, text: str, size: int) -> list[str]:
        """将父块切分为子块，尽量在句子边界断开"""
        if len(text) <= size:
            return [text]

        children = []
        sentences = self._split_sentences(text)
        current = ""
        for sent in sentences:
            if current and len(current) + len(sent) > size:
                if current.strip():
                    children.append(current.strip())
                current = sent
            else:
                current = (current + sent) if current else sent
        if current.strip():
            children.append(current.strip())
        return children

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """按中英文句子边界切分，保留分隔符"""
        parts = []
        buf = ""
        for ch in text:
            buf += ch
            if ch in ("。", "！", "？", ".", "!", "?", "\n"):
                parts.append(buf)
                buf = ""
        if buf.strip():
            parts.append(buf)
        # 合并过短的片段
        merged = []
        acc = ""
        for p in parts:
            if acc and len(acc) < 20:
                acc += p
            elif acc:
                merged.append(acc)
                acc = p
            else:
                acc = p
        if acc:
            merged.append(acc)
        return merged
