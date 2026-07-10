from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .navigation import safe_return_to


MAX_OPEN_GUIDE_NODES = 100


def guide_node_key(level: object, item_id: object) -> str:
    try:
        safe_level = int(level)
        safe_item_id = int(item_id)
    except (TypeError, ValueError):
        return ""
    if safe_level not in {0, 1, 2, 3, 4} or safe_item_id <= 0:
        return ""
    return f"{safe_level}-{safe_item_id}"


def parse_guide_node_keys(value: object) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for part in str(value or "").split(","):
        raw_level, separator, raw_item_id = part.strip().partition("-")
        key = guide_node_key(raw_level, raw_item_id) if separator else ""
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
        if len(result) >= MAX_OPEN_GUIDE_NODES:
            break
    return tuple(result)


def parse_guide_focus(value: object) -> str:
    keys = parse_guide_node_keys(value)
    return keys[0] if keys else ""


def apply_guide_tree_state(
    tree: list[dict[str, object]],
    open_value: object = "",
    focus_value: object = "",
) -> tuple[tuple[str, ...], str]:
    requested_open = set(parse_guide_node_keys(open_value))
    requested_focus = parse_guide_focus(focus_value)
    available: set[str] = set()
    focus_ancestors: set[str] = set()

    def collect(nodes: list[dict[str, object]]) -> None:
        for node in nodes:
            key = guide_node_key(node.get("level"), node.get("id"))
            node["guide_key"] = key
            available.add(key)
            if key == requested_focus:
                focus_ancestors.update(parse_guide_node_keys(",".join(node.get("ancestor_keys") or ())))
            collect(node.get("children") or [])

    collect(tree)
    effective_open = {key for key in requested_open | focus_ancestors if key in available}

    def mark(nodes: list[dict[str, object]]) -> None:
        for node in nodes:
            key = str(node.get("guide_key") or "")
            node["is_open"] = key in effective_open
            node["is_focus"] = key == requested_focus
            mark(node.get("children") or [])

    mark(tree)
    requested_order = list(parse_guide_node_keys(open_value))
    for key in sorted(focus_ancestors):
        if key not in requested_order:
            requested_order.append(key)
    safe_open = tuple(key for key in requested_order if key in available)
    safe_focus = requested_focus if requested_focus in available else ""
    return safe_open, safe_focus


def guide_tree_return_url(
    value: object,
    *,
    focus_key: object = "",
    add_open_keys: tuple[str, ...] = (),
) -> str:
    safe_url = safe_return_to(value, "/guides")
    parts = urlsplit(safe_url)
    if parts.path != "/guides":
        return safe_url
    query = parse_qsl(parts.query, keep_blank_values=True)
    open_value = next((item for key, item in query if key == "open"), "")
    open_keys = list(parse_guide_node_keys(open_value))
    for key in add_open_keys:
        safe_key = parse_guide_focus(key)
        if safe_key and safe_key not in open_keys:
            open_keys.append(safe_key)
    clean_query = [(key, item) for key, item in query if key not in {"open", "focus", "status"}]
    if open_keys:
        clean_query.append(("open", ",".join(open_keys)))
    safe_focus = parse_guide_focus(focus_key)
    if safe_focus:
        clean_query.append(("focus", safe_focus))
    return urlunsplit(("", "", "/guides", urlencode(clean_query), parts.fragment))
