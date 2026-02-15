"""
Website Parser.

Парсинг сайтов клиентов для извлечения информации.
"""

import ipaddress
import re
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx

# R9-18: Maximum response size (5 MB) to prevent OOM
_MAX_RESPONSE_SIZE = 5 * 1024 * 1024


def _is_safe_url(url: str) -> bool:
    """R9-03: Reject private/internal IPs and non-HTTP schemes to prevent SSRF.

    R24-01: Also resolves domain names via DNS and checks resolved IPs against
    private/loopback/link-local ranges to prevent DNS rebinding attacks.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    hostname = parsed.hostname or ''
    if hostname in ('localhost', '127.0.0.1', '0.0.0.0', '::1', ''):
        return False
    if hostname.startswith('169.254.'):
        return False
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
    except ValueError:
        # R24-01: hostname is a domain name — resolve via DNS and check IPs
        # to prevent DNS rebinding attacks (domain resolving to 127.0.0.1 etc.)
        try:
            for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP):
                resolved_ip = ipaddress.ip_address(sockaddr[0])
                if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local:
                    return False
        except (socket.gaierror, OSError):
            pass  # Unresolvable hostname — let HTTP client handle DNS errors
        except ValueError:
            pass  # Unusual sockaddr format — allow through
    return True


class WebsiteParser:
    """Парсер веб-сайтов."""

    def __init__(self, timeout: float = 30.0):
        """
        Инициализация парсера.

        Args:
            timeout: Таймаут запросов в секундах
        """
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; VoiceInterviewerBot/1.0)"
        }

    async def parse(self, url: str) -> Dict[str, Any]:
        """
        Парсить сайт и извлечь информацию.

        Args:
            url: URL сайта

        Returns:
            Словарь с извлечённой информацией
        """
        # Нормализуем URL
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"

        # R9-03: SSRF protection — reject internal/private URLs
        if not _is_safe_url(url):
            return {"error": "URL points to a private/internal address", "url": url}

        # R21-18: Validate each redirect hop for SSRF (don't blindly follow_redirects)
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            try:
                response = None
                for _hop in range(5):
                    response = await client.get(url, headers=self.headers)
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location", "")
                        # R22-02: Resolve relative URLs before SSRF check
                        url = urljoin(url, location)
                        if not _is_safe_url(url):
                            return {"error": "Redirect to unsafe URL blocked", "url": url}
                    else:
                        break
                response.raise_for_status()
                # R9-18: Limit response size to prevent OOM
                content_length = int(response.headers.get('content-length', 0))
                if content_length > _MAX_RESPONSE_SIZE:
                    return {"error": "Response too large", "url": url}
                html = response.text
                if len(html) > _MAX_RESPONSE_SIZE:
                    html = html[:_MAX_RESPONSE_SIZE]
            except Exception as e:
                return {"error": str(e), "url": url}

        # Извлекаем данные
        result = {
            "url": url,
            "title": self._extract_title(html),
            "description": self._extract_meta_description(html),
            "services": self._extract_services(html),
            "contacts": self._extract_contacts(html),
            "social_links": self._extract_social_links(html, url),
        }

        return result

    def _extract_title(self, html: str) -> Optional[str]:
        """Извлечь title страницы."""
        match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def _extract_meta_description(self, html: str) -> Optional[str]:
        """Извлечь meta description."""
        match = re.search(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']',
            html, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        # Альтернативный формат
        match = re.search(
            r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']description["\']',
            html, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        return None

    def _extract_services(self, html: str) -> List[str]:
        """Извлечь список услуг/продуктов."""
        services = []

        # Ищем в списках
        list_items = re.findall(r'<li[^>]*>([^<]{10,100})</li>', html)
        for item in list_items[:10]:
            clean = re.sub(r'<[^>]+>', '', item).strip()
            if clean and len(clean) > 5:
                services.append(clean)

        # Ищем в заголовках h2, h3
        headings = re.findall(r'<h[23][^>]*>([^<]{5,50})</h[23]>', html)
        for heading in headings[:5]:
            clean = re.sub(r'<[^>]+>', '', heading).strip()
            if clean:
                services.append(clean)

        return list(set(services))[:10]  # Уникальные, макс 10

    def _extract_contacts(self, html: str) -> Dict[str, Optional[str]]:
        """Извлечь контактную информацию."""
        contacts = {
            "phone": None,
            "email": None,
            "address": None,
        }

        # Телефон
        phone_patterns = [
            r'\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
            r'8[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
            r'\+\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{2,4}',
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, html)
            if match:
                contacts["phone"] = match.group(0)
                break

        # Email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', html)
        if email_match:
            contacts["email"] = email_match.group(0)

        return contacts

    def _extract_social_links(self, html: str, base_url: str) -> Dict[str, Optional[str]]:
        """Извлечь ссылки на соцсети."""
        social = {
            "telegram": None,
            "whatsapp": None,
            "vk": None,
            "instagram": None,
        }

        patterns = {
            "telegram": r'https?://t\.me/[\w_]+',
            "whatsapp": r'https?://wa\.me/\d+',
            "vk": r'https?://vk\.com/[\w_]+',
            "instagram": r'https?://(?:www\.)?instagram\.com/[\w_]+',
        }

        for name, pattern in patterns.items():
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                social[name] = match.group(0)

        return social

    async def parse_multiple_pages(self, base_url: str, max_pages: int = 3) -> Dict[str, Any]:
        """
        Парсить несколько страниц сайта.

        Args:
            base_url: Базовый URL
            max_pages: Максимум страниц

        Returns:
            Объединённые данные
        """
        # Простая реализация — парсим только главную
        # TODO: Добавить обход ссылок
        return await self.parse(base_url)
