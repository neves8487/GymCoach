"""
Testes unitários para o módulo de retry com backoff exponencial.
"""

import pytest
import asyncio
from webhook.retry_helper import is_rate_limit_error, retry_sync_with_backoff, retry_async_with_backoff


def test_is_rate_limit_error():
    assert is_rate_limit_error(Exception("429 Too Many Requests")) is True
    assert is_rate_limit_error(Exception("ResourceExhausted quota exceeded")) is True
    assert is_rate_limit_error(Exception("Division by zero")) is False


def test_retry_sync_success_first_try():
    calls = 0
    def sample():
        nonlocal calls
        calls += 1
        return "success"

    res = retry_sync_with_backoff(sample, max_retries=3, initial_delay=0.01)
    assert res == "success"
    assert calls == 1


def test_retry_sync_recovers_after_429():
    calls = 0
    def sample():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise Exception("429 Rate Limit Exceeded")
        return "recovered"

    res = retry_sync_with_backoff(sample, max_retries=4, initial_delay=0.01)
    assert res == "recovered"
    assert calls == 3


def test_retry_sync_fails_non_rate_limit_error_immediately():
    calls = 0
    def sample():
        nonlocal calls
        calls += 1
        raise ValueError("Invalid argument")

    with pytest.raises(ValueError):
        retry_sync_with_backoff(sample, max_retries=3, initial_delay=0.01)
    assert calls == 1


@pytest.mark.asyncio
async def test_retry_async_recovers_after_429():
    calls = 0
    async def sample():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise Exception("ResourceExhausted: 429 quota")
        return "async_ok"

    res = await retry_async_with_backoff(sample, max_retries=3, initial_delay=0.01)
    assert res == "async_ok"
    assert calls == 2
