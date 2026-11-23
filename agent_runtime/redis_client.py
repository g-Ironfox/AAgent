"""Separate Redis connections for runtime state and public communication."""

import os

import redis


REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
REDIS_PUBLIC_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_KERNEL_DB = int(os.getenv("REDIS_KERNEL_DB", "1"))
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "30"))

if REDIS_PUBLIC_DB < 0 or REDIS_KERNEL_DB < 0 or REDIS_PUBLIC_DB == REDIS_KERNEL_DB:
    raise ValueError("Redis public and kernel databases must be different non-negative numbers")


def _connection(database, *, blocking=False):
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        db=database,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=None if blocking else REDIS_SOCKET_TIMEOUT,
    )


def get_connection():
    """Kernel-only process, scheduler, routing, and Context state."""
    return _connection(REDIS_KERNEL_DB)


def get_public_connection():
    """External events, public terminal sessions, and shared tool registrations."""
    return _connection(REDIS_PUBLIC_DB)


def get_event_connection():
    """Public queue connection whose blocking wait has no socket timeout."""
    return _connection(REDIS_PUBLIC_DB, blocking=True)
