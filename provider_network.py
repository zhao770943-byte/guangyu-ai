"""System HTTPS proxy discovery, with optional per-host loopback overrides.

Loopback stays direct. Routes are read per request; TLS, redirect policy and
the caller's no-retry rule are unchanged.
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
        if destination.scheme != 'https' or host.rstrip('.') == 'localhost':
            return None
        try:
            if ipaddress.ip_address(host).is_loopback:
                return None
        except ValueError:
            pass
        try:
            path = self.config_path()
            config = {}
            if path.exists():
                if path.stat().st_size > 16384:
                    raise ValueError()
                config = json.loads(path.read_text(encoding='utf-8'))
            routes = config.get('https_proxy_by_host', {})
            use_system = config.get('use_system_proxy', True)
            if not isinstance(use_system, bool):
                raise ValueError()
            if not isinstance(routes, dict):
                raise ValueError()
            value = routes.get(host)
            if value is not None:
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
        return self.system_route(request) if use_system else None

    @staticmethod
    def system_route(request):
        # getproxies follows the standard environment/Windows registry priority.
        # Do not snapshot it at server startup: system proxy switches should apply
        # to subsequent requests without restarting the workbench.
        value = urllib.request.getproxies().get('https')
        if not value or urllib.request.proxy_bypass(request.host):
            return None
        try:
            value = value if '://' in value else 'http://' + value
            parsed = urllib.parse.urlsplit(value)
            if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                    or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                    or any(ord(ch) < 33 for ch in value)):
                raise ValueError()
            _ = parsed.port
        except (ValueError, TypeError, AttributeError):
            # Never echo a proxy URL: it may contain proxy credentials.
            raise urllib.error.URLError('系统 HTTPS 代理配置无效或协议不受支持，请使用 HTTP / HTTPS 代理端口。') from None
        return value

    def https_open(self, request):
        proxy = self.route(request)
        if proxy:
            return self.proxy_open(request, proxy, 'https')
        return None

    def http_open(self, request):
        return None
