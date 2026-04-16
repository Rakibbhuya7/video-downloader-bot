"""
Cloud-upload helpers.

Strategy (tried in order):
  1. file.io   – ephemeral, no account needed, ≤ 2 GB
  2. transfer.sh – no account needed, ≤ 10 GB
  3. 0x0.st   – no account needed, smaller files
"""
import asyncio
import os

import aiohttp


async def upload_to_fileio(path: str) -> str | None:
    """Upload to file.io (auto-expires after first download)."""
    size = os.path.getsize(path)
    if size > 2 * 1024 * 1024 * 1024:
        return None  # file.io cap
    try:
        async with aiohttp.ClientSession() as session:
            with open(path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field(
                    "file",
                    f,
                    filename=os.path.basename(path),
                )
                async with session.post(
                    "https://file.io",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=3600),
                ) as resp:
                    if resp.status == 200:
                        j = await resp.json()
                        if j.get("success"):
                            return j["link"]
    except Exception:
        pass
    return None


async def upload_to_transfersh(path: str) -> str | None:
    """Upload to transfer.sh (10 GB limit, 14-day expiry)."""
    filename = os.path.basename(path)
    try:
        async with aiohttp.ClientSession() as session:
            with open(path, "rb") as f:
                async with session.put(
                    f"https://transfer.sh/{filename}",
                    data=f,
                    timeout=aiohttp.ClientTimeout(total=7200),
                    headers={"Max-Days": "7"},
                ) as resp:
                    if resp.status == 200:
                        link = await resp.text()
                        return link.strip()
    except Exception:
        pass
    return None


async def upload_to_0x0(path: str) -> str | None:
    """Upload to 0x0.st (512 MB limit)."""
    size = os.path.getsize(path)
    if size > 512 * 1024 * 1024:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            with open(path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("file", f, filename=os.path.basename(path))
                async with session.post(
                    "https://0x0.st",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=1800),
                ) as resp:
                    if resp.status == 200:
                        return (await resp.text()).strip()
    except Exception:
        pass
    return None


async def smart_cloud_upload(path: str) -> str | None:
    """Try each provider in order; return first successful link."""
    size = os.path.getsize(path)

    providers = []

    if size <= 512 * 1024 * 1024:
        providers = [upload_to_0x0, upload_to_fileio, upload_to_transfersh]
    elif size <= 2 * 1024 * 1024 * 1024:
        providers = [upload_to_fileio, upload_to_transfersh]
    else:
        providers = [upload_to_transfersh]

    for provider in providers:
        link = await provider(path)
        if link:
            return link

    return None
