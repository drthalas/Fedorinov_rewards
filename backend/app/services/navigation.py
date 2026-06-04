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
    safe_url = safe_return_to(url)
    if not safe_url or not status:
        return safe_url
    parts = urlsplit(safe_url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "status"]
    query.append(("status", status))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
