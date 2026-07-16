from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def safe_return_to(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return default
    if not text.startswith("/") or text.startswith("//") or "\\" in text:
        return default
    parts = urlsplit(text)
    if parts.scheme or parts.netloc:
        return default
    return text


def with_status(url: str, status: str) -> str:
    return with_query_value(url, "status", status)


def with_query_value(url: str, key: str, value: str) -> str:
    safe_url = safe_return_to(url)
    if not safe_url or not key or not value:
        return safe_url
    parts = urlsplit(safe_url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query = [(query_key, query_value) for query_key, query_value in query if query_key != key]
    query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
