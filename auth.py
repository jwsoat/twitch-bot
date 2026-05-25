def is_allowed(username: str, allowed: set[str]) -> bool:
    return username.lower() in {u.lower() for u in allowed}
