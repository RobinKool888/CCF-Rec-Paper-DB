import hashlib
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from core.cache_manager import CacheDB

_rate_limit_lock = threading.Lock()
_rate_limit_until: float = 0.0


class SandboxFixtureMissError(Exception):
    """Raised when a fixture-mode LLMClient encounters an uncached prompt."""
    pass


class LLMClient:
    """Thin wrapper around multiple LLM providers with SQLite caching."""

    def __init__(self, config: dict, fixture_path: Optional[str] = None):
        self.config = config
        self.fixture_path = fixture_path
        self.provider = config.get("provider", "openai")
        self.model = config.get("model", "gpt-4o-mini")
        self.api_key_env = config.get("api_key_env", "OPENAI_API_KEY")
        self.openai_base_url = config.get("openai_base_url")
        self.ollama_base_url = config.get(
            "ollama_base_url", "http://localhost:11434"
        )
        self.rpm_limit = config.get("rpm_limit", 500)
        self.max_retries = config.get("max_retries", 3)
        self.retry_statuses = set(config.get("retry_statuses", [429, 500, 502, 503]))
        self.max_concurrent = config.get("max_concurrent", 5)

        # SQLite cache
        cache_dir = config.get("cache_dir", "cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_db = os.path.join(cache_dir, "llm_cache.sqlite")
        self._cache = CacheDB(cache_db)

        # Fixture responses (test mode)
        self._fixtures: Optional[dict] = None
        if fixture_path is not None:
            if os.path.exists(fixture_path):
                with open(fixture_path, "r", encoding="utf-8") as fh:
                    self._fixtures = json.load(fh)
            else:
                self._fixtures = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete(self, prompt: str, temperature: float = 0.1) -> str:
        key = self._cache_key(prompt)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = self._dispatch(prompt, temperature)
        self._cache.set(key, result)
        return result

    def complete_batch(self, prompts: list, **kwargs) -> list:
        temperature = kwargs.get("temperature", 0.1)
        results = [None] * len(prompts)
        delay = 60.0 / max(self.rpm_limit, 1)

        # Resolve cache hits first — never send a cached prompt to the API
        uncached_indices = []
        for i, p in enumerate(prompts):
            key = self._cache_key(p)
            cached = self._cache.get(key)
            if cached is not None:
                results[i] = cached
            else:
                uncached_indices.append(i)

        if not uncached_indices:
            return results  # everything was already cached

        with ThreadPoolExecutor(max_workers=self.max_concurrent) as pool:
            futures = {
                pool.submit(self.complete, prompts[i], temperature): i
                for i in uncached_indices
            }
            for future in as_completed(futures):
                idx = futures[future]
                results[idx] = future.result()
                time.sleep(delay)
        return results

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, prompt: str, temperature: float) -> str:
        if self._fixtures is not None:
            key = self._cache_key(prompt)
            if key not in self._fixtures:
                raise SandboxFixtureMissError(
                    f"Prompt hash '{key}' not found in fixture file. "
                    f"Run analysis/tests/tools/record_fixtures.py to "
                    f"record real responses."
                )
            return self._fixtures[key]

        provider = self.provider
        if provider == "openai":
            return self._call_openai(prompt, temperature)
        if provider == "anthropic":
            return self._call_anthropic(prompt, temperature)
        if provider == "deepseek":
            return self._call_deepseek(prompt, temperature)
        if provider == "ollama":
            return self._call_ollama(prompt, temperature)
        raise ValueError(f"Unknown LLM provider: {provider}")

    def _call_openai(self, prompt: str, temperature: float) -> str:
        import openai
        import httpx

        api_key = os.environ.get(self.api_key_env, "")
        kwargs = {
            "api_key": api_key,
            "timeout": httpx.Timeout(connect=15.0, read=180.0, write=15.0, pool=5.0),
        }
        if self.openai_base_url:
            kwargs["base_url"] = self.openai_base_url
        client = openai.OpenAI(**kwargs)
        global _rate_limit_until
        for attempt in range(self.max_retries):
            with _rate_limit_lock:
                wait = max(0.0, _rate_limit_until - time.time())
            if wait > 0:
                time.sleep(wait)
            try:
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                )
                return resp.choices[0].message.content
            except openai.BadRequestError as e:
                # Third-party proxy content filter triggered (e.g. security paper titles).
                # Log and return empty string — caller will skip this batch.
                logging.warning(
                    f"[LLMClient] BadRequestError (content filtered), skipping: {e}"
                )
                return ""
            except openai.RateLimitError:
                if attempt < self.max_retries - 1:
                    backoff = 2 ** attempt
                    with _rate_limit_lock:
                        _rate_limit_until = time.time() + backoff
                    time.sleep(backoff)
                else:
                    raise
            except (openai.APITimeoutError, openai.APIConnectionError) as e:
                if attempt < self.max_retries - 1:
                    backoff = 30 * (2 ** attempt)  # 30s, 60s, 120s, …
                    logging.warning(
                        f"[LLMClient] Timeout/connection error (attempt {attempt + 1}/{self.max_retries}), "
                        f"retrying in {backoff}s: {e}"
                    )
                    time.sleep(backoff)
                else:
                    logging.error(
                        f"[LLMClient] Giving up after {self.max_retries} attempts due to timeout: {e}"
                    )
                    return ""
        return ""

    def _call_anthropic(self, prompt: str, temperature: float) -> str:
        import anthropic

        api_key = os.environ.get(self.api_key_env, "")
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    def _call_deepseek(self, prompt: str, temperature: float) -> str:
        import openai

        api_key = os.environ.get(self.api_key_env, "")
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
        )
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return resp.choices[0].message.content

    def _call_ollama(self, prompt: str, temperature: float) -> str:
        import requests

        url = f"{self.ollama_base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": temperature},
            "stream": False,
        }
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cache_key(self, prompt: str) -> str:
        raw = f"{self.model}:{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()
