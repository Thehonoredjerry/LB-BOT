import discord
from datetime import datetime, timezone

EMBED_COLOR = 0x2B2B31
LINE_GIF = "https://c.tenor.com/FYTnZyWwqGwAAAAC/line-light.gif"
PLACEHOLDER_AVATAR = "https://tr.rbxcdn.com/30DAY-Avatar-Placeholder-A-100x100.png"


def build_player_embed(
    rank: int,
    roblox_username: str,
    discord_user_id: str,
    specific_info: str,
    avatar_url: str,
    display_name: str = "",
    cooldown_expires_at: datetime | None = None,
) -> discord.Embed:
    author_name = f"#{rank} ・{display_name}" if display_name else f"#{rank} ・{roblox_username}"
    embed = discord.Embed(
        title="⌞information⌝",
        description=f"<@{discord_user_id}>\n{specific_info}",
        color=EMBED_COLOR,
    )
    embed.set_author(name=author_name)
    embed.set_thumbnail(url=avatar_url)
    embed.set_image(url=LINE_GIF)

    if cooldown_expires_at:
        # Normalise to offset-aware UTC so naive vs aware never causes a comparison error
        if cooldown_expires_at.tzinfo is None:
            cooldown_expires_at = cooldown_expires_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if cooldown_expires_at > now:
            remaining = max(1, (cooldown_expires_at - now).days + 1)
            embed.set_footer(text=f"ติด cooldown {remaining} days")

    return embed


def build_vacant_embed(rank: int) -> discord.Embed:
    embed = discord.Embed(
        description="Waiting for a new challenger...",
        color=EMBED_COLOR,
    )
    embed.set_author(name=f"#{rank} ・VACANT")
    embed.set_thumbnail(url=PLACEHOLDER_AVATAR)
    embed.set_image(url=LINE_GIF)
    return embed
