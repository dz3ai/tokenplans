import re

_SEGMENT = re.compile(r"^([^\[\]]+)(?:\[(\d+)\])?$")


def extract_value(data, path: str):
    parts = []
    for seg in path.split("."):
        m = _SEGMENT.match(seg)
        if not m:
            raise ValueError(f"invalid path segment: {seg!r}")
        parts.append((m.group(1), m.group(2)))

    cur = data
    for name, idx in parts:
        cur = cur[name]
        if idx is not None:
            cur = cur[int(idx)]
    return cur
