import json
from urllib.parse import quote

import httpx


class NotificationSendError(Exception):
    """A provider failure that is safe to persist and show to the user."""


def provider_error_message(status_code: int) -> str:
    if status_code in (400, 401, 403):
        return "Server 酱拒绝了请求，请检查 SendKey 是否完整有效"
    if status_code == 429:
        return "Server 酱请求频率受限，请稍后在设置中发送测试通知"
    if status_code >= 500:
        return "Server 酱服务暂时异常，请稍后重试"
    return "Server 酱未接受本次通知，请在设置中发送测试通知"


def sanitize_notification_error(error: Exception | str | None, *, scheduler: bool = False) -> str | None:
    if error is None:
        return None
    if isinstance(error, NotificationSendError):
        return str(error)
    text = str(error)
    lowered = text.lower()
    if "400 bad request" in lowered or "status code 400" in lowered:
        return provider_error_message(400)
    if "401" in lowered or "403" in lowered:
        return provider_error_message(401)
    if "429" in lowered:
        return provider_error_message(429)
    if "timeout" in lowered or "timed out" in lowered or "connect" in lowered:
        return "暂时未连接到 Server 酱，请检查网络后发送测试通知"
    if "different event loop" in lowered or "asyncio" in lowered:
        return "通知检查暂时异常，请重新启动应用后查看最新状态"
    if scheduler:
        return "通知检查暂时异常，请重新启动应用后查看最新状态"
    return "通知发送暂时异常，请在设置中发送测试通知"


async def send_server_chan(send_key: str, title: str, description: str) -> bool:
    if not send_key:
        return False
    url = f"https://sctapi.ftqq.com/{quote(send_key, safe='')}.send"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, data={"title": title, "desp": description})
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise NotificationSendError(provider_error_message(exc.response.status_code)) from None
    except httpx.TimeoutException:
        raise NotificationSendError("连接 Server 酱超时，请检查网络后重试") from None
    except httpx.RequestError:
        raise NotificationSendError("暂时未连接到 Server 酱，请检查网络后重试") from None
    except (ValueError, TypeError, KeyError):
        raise NotificationSendError("Server 酱返回了无法识别的响应，请稍后重试") from None
    accepted = payload.get("code") == 0 or payload.get("data", {}).get("errno") == 0
    if not accepted:
        raise NotificationSendError("Server 酱拒绝了本次通知，请检查 SendKey 后重试")
    return True


def parse_notification_days(value: str | int | list[int] | None) -> list[int]:
    """Read both legacy scalar settings and the new JSON array representation."""
    if value is None or value == "":
        return [7]
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            parsed = int(value)
    if isinstance(parsed, int):
        parsed = [parsed]
    days = [int(day) for day in parsed if not isinstance(day, bool) and 0 <= int(day) <= 90]
    return sorted(set(days), reverse=True) or [7]
