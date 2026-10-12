"""Test doubles shared by the suite. Kept out of production modules on purpose."""


class FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


class FakeAsyncClient:
    """Captures every outgoing request so tests can assert on what providers are sent."""

    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self._status_code = status_code
        self._text = text
        self.posts = []

    def __call__(self, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers or {}})
        return FakeResponse(self._payload, self._status_code, self._text)
