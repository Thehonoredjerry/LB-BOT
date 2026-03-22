import discord
import asyncpg
import db
from utils.embeds import build_player_embed, build_vacant_embed
from utils.roblox import get_roblox_avatar_url

CATEGORY_RANGES = {
    "1_10":   (1,  10),
    "11_20":  (11, 20),
    "21_30":  (21, 30),
    "31_40":  (31, 40),
    "41_50":  (41, 50),
    "51_60":  (51, 60),
    "61_70":  (61, 70),
    "71_80":  (71, 80),
    "81_90":  (81, 90),
    "91_100": (91, 100),
}

SECTION_CHOICES = [
    ("Ranks 1-10",   "1_10"),
    ("Ranks 11-20",  "11_20"),
    ("Ranks 21-30",  "21_30"),
    ("Ranks 31-40",  "31_40"),
    ("Ranks 41-50",  "41_50"),
    ("Ranks 51-60",  "51_60"),
    ("Ranks 61-70",  "61_70"),
    ("Ranks 71-80",  "71_80"),
    ("Ranks 81-90",  "81_90"),
    ("Ranks 91-100", "91_100"),
]

LB_TYPES = {
    "all":    "Top All",
    "mobile": "Top Mobile",
}


def get_category_for_rank(rank: int) -> str:
    start = ((rank - 1) // 10) * 10 + 1
    end = start + 9
    return f"{start}_{end}"


def lb_label(lb_type: str) -> str:
    return LB_TYPES.get(lb_type, lb_type.title())


async def build_leaderboard_embeds(
    pool: asyncpg.Pool, guild_id: str, category: str, lb_type: str = "all"
) -> list[discord.Embed]:
    start, end = CATEGORY_RANGES[category]
    players = await db.get_players_in_range(pool, guild_id, start, end, lb_type)
    player_map = {p["rank"]: p for p in players}

    embeds = []
    for rank in range(start, end + 1):
        player = player_map.get(rank)
        if player:
            avatar_url = await get_roblox_avatar_url(player["roblox_username"])
            embeds.append(build_player_embed(
                rank,
                player["roblox_username"],
                player["discord_user_id"],
                player["specific_info"],
                avatar_url,
                player.get("display_name", ""),
                player.get("cooldown_expires_at"),
            ))
        else:
            embeds.append(build_vacant_embed(rank))

    return embeds


async def update_leaderboard_messages(
    bot: discord.Client, pool: asyncpg.Pool, guild_id: str, category: str, lb_type: str = "all"
) -> None:
    messages = await db.get_leaderboard_messages(pool, guild_id, category, lb_type)
    if not messages:
        return

    embeds = await build_leaderboard_embeds(pool, guild_id, category, lb_type)

    for msg_row in messages:
        try:
            channel = bot.get_channel(int(msg_row["channel_id"]))
            if channel is None:
                channel = await bot.fetch_channel(int(msg_row["channel_id"]))
            msg = await channel.fetch_message(int(msg_row["message_id"]))
            await msg.edit(embeds=embeds)
        except Exception:
            pass
