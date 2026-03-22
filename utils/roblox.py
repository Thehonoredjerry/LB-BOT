import aiohttp

PLACEHOLDER_AVATAR = "https://tr.rbxcdn.com/30DAY-Avatar-Placeholder-A-100x100.png"


async def get_roblox_user_id(username: str) -> int | None:
    """Returns the Roblox user ID for a username, or None if not found."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://users.roblox.com/v1/usernames/users",
                json={"usernames": [username], "excludeBannedUsers": False},
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data.get("data"):
                    return None
                return data["data"][0]["id"]
    except Exception:
        return None


async def get_roblox_avatar_url(username: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://users.roblox.com/v1/usernames/users",
                json={"usernames": [username], "excludeBannedUsers": False},
            ) as resp:
                if resp.status != 200:
                    return PLACEHOLDER_AVATAR
                data = await resp.json()
                if not data.get("data"):
                    return PLACEHOLDER_AVATAR
                user_id = data["data"][0]["id"]

            async with session.get(
                f"https://thumbnails.roblox.com/v1/users/avatar-headshot"
                f"?userIds={user_id}&size=150x150&format=Png&isCircular=false"
            ) as resp:
                if resp.status != 200:
                    return PLACEHOLDER_AVATAR
                thumb = await resp.json()
                if not thumb.get("data"):
                    return PLACEHOLDER_AVATAR
                return thumb["data"][0].get("imageUrl", PLACEHOLDER_AVATAR)
    except Exception:
        return PLACEHOLDER_AVATAR
