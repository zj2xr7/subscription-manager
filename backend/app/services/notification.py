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
