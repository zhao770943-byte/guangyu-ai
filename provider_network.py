"""Explicit, per-host HTTPS routes through a user-owned loopback HTTP proxy.

Unconfigured endpoints remain direct. No environment proxy, TLS downgrade,
redirect, or automatic retry/fallback is introduced.
"""
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request


class LocalProxyRoutes(urllib.request.ProxyHandler):
    def __init__(self, config_path):
        self.config_path = config_path
        super().__init__({})

    def route(self, request):
        destination = urllib.parse.urlsplit(request.full_url)
        host = (destination.hostname or '').lower()
        if destination.scheme != 'https' or host == 'localhost':
            return None
        try:
            if ipaddress.ip_address(host).is_loopback:
                return None
        except ValueError:
            pass
        try:
            path = self.config_path()
            if not path.exists():
                return None
            if path.stat().st_size > 16384:
                raise ValueError()
            routes = json.loads(path.read_text(encoding='utf-8')).get('https_proxy_by_host', {})
            if not isinstance(routes, dict):
                raise ValueError()
            value = routes.get(host)
            if value is None:
                return None
            if not isinstance(value, str):
                raise ValueError()
            proxy = urllib.parse.urlsplit(value)
            if (proxy.scheme != 'http' or proxy.username is not None or proxy.password is not None
                    or proxy.path not in ('', '/') or proxy.query or proxy.fragment
                    or not proxy.port or not ipaddress.ip_address(proxy.hostname).is_loopback):
                raise ValueError()
            return value
        except (OSError, ValueError, TypeError, AttributeError):
            raise urllib.error.URLError('本机 HTTPS 代理路由配置无效，请检查 provider-network.json。') from None

    def https_open(self, request):
        proxy = self.route(request)
        if proxy:
            return self.proxy_open(request, proxy, 'https')
        return None

    def http_open(self, request):
        return None
