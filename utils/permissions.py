import discord
from discord import app_commands
import asyncpg
import db


PERMANENT_OWNER_ID = "1150660855025909800"


async def check_permission(
    interaction: discord.Interaction,
    pool: asyncpg.Pool,
    required: str,
) -> bool:
    if required == "any":
        return True

    guild_id = str(interaction.guild_id)
    user_id  = str(interaction.user.id)

    # Permanent owner always has full access
    if user_id == PERMANENT_OWNER_ID:
        return True

    entry = await db.get_whitelist_entry(pool, guild_id, user_id)

    if entry is None:
        await interaction.response.send_message(
            "❌ You don't have permission to use this command.", ephemeral=True
        )
        return False

    user_role = entry["role"]

    if required == "owner" and user_role != "owner":
        await interaction.response.send_message(
            "❌ This command is restricted to owners only.", ephemeral=True
        )
        return False

    return True


async def send_audit_log(
    bot: discord.Client,
    pool: asyncpg.Pool,
    guild_id: str,
    title: str,
    body: str,
    user: discord.User | discord.Member,
) -> None:
    guild = bot.get_guild(int(guild_id))
    guild_name = guild.name if guild else guild_id
    print(f"[{guild_name}] {title} | {body} | By {user.display_name} ({user.id})")

    try:
        row = await db.get_audit_log_channel(pool, guild_id)
        if not row:
            print(f"[{guild_name}] Audit log: no channel set — use /set-audit-log first")
            return

        channel_id = int(row["channel_id"])
        channel = bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception as e:
                print(f"[{guild_name}] Audit log: cannot find channel {channel_id} — {e}")
                return

        embed = discord.Embed(color=0x2B2B31)
        embed.set_author(name=title, icon_url=bot.user.display_avatar.url)
        embed.description = f"{body}\nBy {user.display_name} ({user.id})"
        await channel.send(embed=embed)
    except discord.Forbidden:
        print(f"[{guild_name}] Audit log: bot lacks permission to send in that channel")
    except Exception as e:
        print(f"[{guild_name}] Audit log error: {e}")
