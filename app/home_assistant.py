from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import httpx

from app import config


class HomeAssistantConfigurationError(ValueError):
    pass


class HomeAssistantUnavailable(RuntimeError):
    def __init__(self, message="Home Assistant is unavailable", response_class="unavailable"):
        super().__init__(message)
        self.response_class = response_class


@dataclass(frozen=True)
class HomeAssistantConnection:
    base_url: str
    access_value: str = field(repr=False)
    timeout_seconds: int


def load_home_assistant_connection():
    try:
        values = config.home_assistant_configuration()
    except ValueError as exc:
        raise HomeAssistantConfigurationError("Home Assistant configuration is invalid") from exc
    raw_url = values["base_url"]
    access_value = values["access_value"]
    timeout_seconds = values["timeout_seconds"]
    if not raw_url and not access_value:
        return None
    if not raw_url or not access_value:
        raise HomeAssistantConfigurationError("Home Assistant configuration is incomplete")
    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HomeAssistantConfigurationError("Home Assistant URL must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise HomeAssistantConfigurationError("Home Assistant URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise HomeAssistantConfigurationError("Home Assistant URL must not contain query or fragment")
    base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")).rstrip("/")
    return HomeAssistantConnection(base_url, access_value, timeout_seconds)


class HomeAssistantClient:
    def __init__(self, connection: HomeAssistantConnection, client_factory: Callable = httpx.Client):
        self.connection = connection
        self.client_factory = client_factory

    def request_json(self, method, path, *, params=None, json_body=None):
        headers = {
            "Authorization": f"Bearer {self.connection.access_value}",
            "Content-Type": "application/json",
        }
        try:
            with self.client_factory(headers=headers, timeout=self.connection.timeout_seconds) as client:
                response = client.request(
                    method,
                    f"{self.connection.base_url}{path}",
                    params=params,
                    json=json_body,
                )
                if not response.is_success:
                    if response.status_code in {401, 403}:
                        response_class = "authentication"
                    elif response.status_code == 404:
                        response_class = "not_found"
                    elif response.status_code == 429:
                        response_class = "rate_limited"
                    elif 500 <= response.status_code <= 599:
                        response_class = "server"
                    else:
                        response_class = "response"
                    raise HomeAssistantUnavailable(response_class=response_class)
                try:
                    return response.json()
                except (ValueError, TypeError) as exc:
                    raise HomeAssistantUnavailable("Home Assistant is unavailable") from exc
        except httpx.HTTPError as exc:
            raise HomeAssistantUnavailable(response_class="transport") from exc

    def get_json(self, path, *, params=None):
        return self.request_json("GET", path, params=params)

    def post_json(self, path, *, params=None, json_body=None):
        return self.request_json("POST", path, params=params, json_body=json_body)
