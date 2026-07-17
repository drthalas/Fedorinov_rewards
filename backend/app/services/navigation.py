from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRANSIENT_QUERY_KEYS = ("status", "message", "error", "created", "media_cleanup")


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


def without_query_keys(url: str, *keys: str) -> str:
    safe_url = safe_return_to(url)
    excluded = {str(key) for key in keys if key}
    if not safe_url or not excluded:
        return safe_url
    parts = urlsplit(safe_url)
    query = [item for item in parse_qsl(parts.query, keep_blank_values=True) if item[0] not in excluded]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def delete_return_to(url: str, selection_key: str = "") -> str:
    keys = (*TRANSIENT_QUERY_KEYS, selection_key) if selection_key else TRANSIENT_QUERY_KEYS
    return without_query_keys(url, *keys)
