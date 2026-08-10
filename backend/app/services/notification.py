import json
from urllib.parse import quote

import httpx


async def send_server_chan(send_key: str, title: str, description: str) -> bool:
    if not send_key:
        return False
    url = f"https://sctapi.ftqq.com/{quote(send_key, safe='')}.send"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, data={"title": title, "desp": description})
        response.raise_for_status()
        payload = response.json()
    return payload.get("code") == 0 or payload.get("data", {}).get("errno") == 0


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
