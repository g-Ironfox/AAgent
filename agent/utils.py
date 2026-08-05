import os
def env(name: str, fallback: str) -> str:
    return os.getenv(name) or fallback