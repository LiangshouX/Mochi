"""
* Time      : 2026/7/2
* Author    : LiangshouX
* File      : web_search.py
* Function  : 内置网页搜索工具
"""
from mochi_assistant.logging_config import get_logger

logger = get_logger(__name__)


def web_search(query: str, max_results: int = 5) -> str:
    """搜索网页

    Args:
        query: 搜索查询
        max_results: 最大结果数

    Returns:
        搜索结果文本
    """
    logger.info(f"网页搜索: {query}")

    try:
        # 使用 DuckDuckGo 搜索（通过 requests）
        import requests
        from urllib.parse import quote_plus

        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # 简单解析 HTML 结果
        from html.parser import HTMLParser

        class DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self._current = {}
                self._in_title = False
                self._in_snippet = False

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == 'a' and 'result__a' in attrs_dict.get('class', ''):
                    self._in_title = True
                    self._current['url'] = attrs_dict.get('href', '')
                if tag == 'a' and 'result__snippet' in attrs_dict.get('class', ''):
                    self._in_snippet = True

            def handle_data(self, data):
                if self._in_title:
                    self._current['title'] = data.strip()
                    self._in_title = False
                if self._in_snippet:
                    self._current['snippet'] = data.strip()
                    self._in_snippet = False
                    if self._current.get('title'):
                        self.results.append(self._current)
                    self._current = {}

        parser = DDGParser()
        parser.feed(response.text)

        if not parser.results:
            return f"未找到与 '{query}' 相关的结果"

        lines = [f"搜索结果: {query}\n"]
        for i, result in enumerate(parser.results[:max_results], 1):
            title = result.get('title', '无标题')
            snippet = result.get('snippet', '无摘要')
            url = result.get('url', '')
            lines.append(f"{i}. {title}")
            lines.append(f"   {snippet}")
            if url:
                lines.append(f"   链接: {url}")
            lines.append("")

        return "\n".join(lines)

    except ImportError:
        return "搜索功能需要 requests 库。请运行: pip install requests"
    except Exception as e:
        logger.error(f"网页搜索失败: {e}")
        return f"搜索失败: {e}"


def register_web_tools(registry) -> None:
    """注册网页搜索工具到工具注册表

    Args:
        registry: ToolRegistry 实例
    """
    registry.register(
        name="web_search",
        description="搜索互联网获取信息",
        handler=web_search,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询关键词"},
                "max_results": {"type": "integer", "description": "最大结果数", "default": 5},
            },
            "required": ["query"],
        },
    )
