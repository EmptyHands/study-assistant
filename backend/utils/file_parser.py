"""文件解析工具 - 支持 PDF/DOCX/TXT/图片"""
import logging
import os
import hashlib
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".txt", ".md", ".rst",
    ".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c", ".h",
    ".png", ".jpg", ".jpeg", ".bmp", ".tiff",
}


def get_file_hash(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_file(file_path: str) -> dict:
    """解析单个文件，返回 {success, text, metadata}"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {"success": False, "error": f"不支持的文件格式: {ext}"}

    try:
        if ext == ".pdf":
            return _parse_pdf(file_path)
        elif ext in (".docx", ".doc"):
            return _parse_docx(file_path)
        elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff"):
            return _parse_image(file_path)
        else:
            return _parse_text(file_path)
    except Exception as e:
        logger.error(f"文件解析失败 {file_path}: {e}")
        return {"success": False, "error": str(e)}


def parse_directory(dir_path: str) -> dict:
    """解析整个目录，合并所有可解析文件的内容"""
    all_texts = []
    file_count = 0
    structure = []

    for root, dirs, files in os.walk(dir_path):
        if any(skip in root for skip in [".git", "__pycache__", "node_modules", ".venv", "venv", ".idea"]):
            continue
        rel_root = os.path.relpath(root, dir_path)
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            fpath = os.path.join(root, fname)
            rel_path = os.path.join(rel_root, fname) if rel_root != "." else fname
            result = parse_file(fpath)
            if result.get("success"):
                all_texts.append(f"=== {rel_path} ===\n{result['text']}")
                structure.append(rel_path)
                file_count += 1

    if not all_texts:
        return {"success": True, "text": "", "file_count": 0, "structure": [], "warning": "目录中没有可解析的文件"}

    return {
        "success": True,
        "text": "\n\n".join(all_texts),
        "file_count": file_count,
        "structure": structure,
    }


def _parse_pdf(file_path: str) -> dict:
    import pdfplumber
    text_parts = []
    meta = {}
    with pdfplumber.open(file_path) as pdf:
        meta = pdf.metadata or {}
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    text = "\n".join(text_parts)
    return {
        "success": True,
        "text": text,
        "page_count": len(pdf.pages) if hasattr(pdf, 'pages') else 0,
        "metadata": {"title": meta.get("/Title", ""), "author": meta.get("/Author", "")},
    }


def _parse_docx(file_path: str) -> dict:
    from docx import Document
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs)
    return {"success": True, "text": text, "paragraph_count": len(paragraphs)}


def _parse_image(file_path: str) -> dict:
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        return {"success": True, "text": text, "ocr": True}
    except ImportError:
        return {"success": True, "text": f"[图片文件: {os.path.basename(file_path)} - 未安装OCR引擎]"}
    except Exception as e:
        logger.warning(f"图片OCR失败 {file_path}: {e}")
        return {"success": True, "text": f"[图片文件: {os.path.basename(file_path)}] (OCR解析失败: {e})"}


def _parse_text(file_path: str) -> dict:
    encodings = ["utf-8", "gbk", "gb2312", "latin-1"]
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                text = f.read()
            return {"success": True, "text": text}
        except (UnicodeDecodeError, UnicodeError):
            continue
    return {"success": False, "error": "无法识别文件编码"}
