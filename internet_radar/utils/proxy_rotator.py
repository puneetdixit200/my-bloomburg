from __future__ import annotations


class ProxyRotator:
    def __init__(self, proxies: list[str] | None = None) -> None:
        self.proxies = [proxy.strip() for proxy in proxies or [] if proxy and proxy.strip()]
        self._index = 0

    def next_proxy(self) -> str | None:
        if not self.proxies:
            return None
        proxy = self.proxies[self._index % len(self.proxies)]
        self._index += 1
        return proxy

    def requests_kwargs(self) -> dict[str, dict[str, str]]:
        proxy = self.next_proxy()
        if not proxy:
            return {}
        return {"proxies": {"http": proxy, "https": proxy}}
