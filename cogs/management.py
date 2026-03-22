import discord
from discord import app_commands
from discord.ext import commands
import json
import io
import time
from datetime import datetime, timedelta, timezone
import db
from utils.permissions import check_permission, send_audit_log
from utils.leaderboard import update_leaderboard_messages, lb_label

LB_CHOICES = [
    app_commands.Choice(name="Top All",    value="all"),
    app_commands.Choice(name="Top Mobile", value="mobile"),
]

ALL_SECTIONS = ["1_10", "11_20", "21_30", "31_40", "41_50", "51_60", "61_70", "71_80", "81_90", "91_100"]


def get_category_for_rank(rank: int) -> str:
    start = ((rank - 1) // 10) * 10 + 1
    end = start + 9
    return f"{start}_{end}"


class Management(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def pool(self):
        return self.bot.pool

    @app_commands.command(name="backup", description="Download a backup of all leaderboard data as a file (owner only)")
    async def backup(self, interaction: discord.Interaction):
        if not await check_permission(interaction, self.pool, "owner"):
            return

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)

        players    = await self.pool.fetch("SELECT * FROM players WHERE guild_id = $1", guild_id)
        messages   = await self.pool.fetch("SELECT * FROM leaderboard_messages WHERE guild_id = $1", guild_id)
        whitelist  = await db.get_whitelist(self.pool, guild_id)
        audit_logs = await self.pool.fetch("SELECT * FROM audit_log_channels WHERE guild_id = $1", guild_id)

        def to_dict(record):
            d = dict(record)
            for k, v in d.items():
                if isinstance(v, datetime):
                    d[k] = v.isoformat()
            return d

        data = {
            "guildId":    guild_id,
            "exportedAt": datetime.utcnow().isoformat(),
            "players":    [to_dict(p) for p in players],
            "messages":   [to_dict(m) for m in messages],
            "whitelist":  [to_dict(w) for w in whitelist],
            "auditLogs":  [to_dict(a) for a in audit_logs],
        }

        buf = io.BytesIO(json.dumps(data, indent=2).encode())
        buf.seek(0)
        file = discord.File(buf, filename=f"leaderboard-backup-{int(time.time())}.json")
        await interaction.followup.send("✅ Here is your backup:", file=file, ephemeral=True)

    @app_commands.command(name="import-backup", description="Restore leaderboard data from a backup JSON file (owner only)")
    @app_commands.describe(file="The backup JSON file")
    async def import_backup(self, interaction: discord.Interaction, file: discord.Attachment):
        if not await check_permission(interaction, self.pool, "owner"):
            return

        if not file.filename.endswith(".json"):
            await interaction.response.send_message("❌ Please attach a valid JSON backup file.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)

        try:
            content = await file.read()
            data    = json.loads(content)
        except Exception as e:
            await interaction.followup.send(f"❌ Could not read backup file: {e}", ephemeral=True)
            return

        # Validate the file looks like a real backup before touching anything
        if "players" not in data and "messages" not in data:
            await interaction.followup.send("❌ This file doesn't look like a valid backup.", ephemeral=True)
            return

        # Parse all rows first — catch any bad data before deleting anything
        try:
            parsed_players = []
            for p in data.get("players", []):
                cooldown_str = p.get("cooldown_expires_at")
                cooldown = None
                if cooldown_str:
                    # Strip timezone suffix if present (e.g. +00:00 or Z) for compatibility
                    cooldown_str = cooldown_str.split("+")[0].rstrip("Z")
                    cooldown = datetime.fromisoformat(cooldown_str)
                parsed_players.append({
                    "rank": p["rank"], "roblox_username": p["roblox_username"],
                    "discord_user_id": p["discord_user_id"], "specific_info": p["specific_info"],
                    "cooldown_expires_at": cooldown, "lb_type": p.get("lb_type", "all"),
                    "display_name": p.get("display_name", ""),
                })
        except Exception as e:
            await interaction.followup.send(f"❌ Backup file has invalid data: {e}", ephemeral=True)
            return

        # All data validated — safe to replace
        try:
            await self.pool.execute("DELETE FROM players WHERE guild_id = $1", guild_id)
            await self.pool.execute("DELETE FROM leaderboard_messages WHERE guild_id = $1", guild_id)
            await self.pool.execute("DELETE FROM whitelist WHERE guild_id = $1", guild_id)
            await self.pool.execute("DELETE FROM audit_log_channels WHERE guild_id = $1", guild_id)

            for p in parsed_players:
                await self.pool.execute(
                    """INSERT INTO players (guild_id, rank, roblox_username, discord_user_id, specific_info, cooldown_expires_at, lb_type, display_name)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                    guild_id, p["rank"], p["roblox_username"], p["discord_user_id"],
                    p["specific_info"], p["cooldown_expires_at"], p["lb_type"], p["display_name"],
                )
            for m in data.get("messages", []):
                await self.pool.execute(
                    "INSERT INTO leaderboard_messages (guild_id, channel_id, message_id, category, lb_type) VALUES ($1,$2,$3,$4,$5)",
                    guild_id, m["channel_id"], m["message_id"], m["category"], m.get("lb_type", "all"),
                )
            for w in data.get("whitelist", []):
                await self.pool.execute(
                    "INSERT INTO whitelist (guild_id, user_id, role) VALUES ($1,$2,$3)",
                    guild_id, w["user_id"], w["role"],
                )
            for a in data.get("auditLogs", []):
                await self.pool.execute(
                    "INSERT INTO audit_log_channels (guild_id, channel_id) VALUES ($1,$2)",
                    guild_id, a["channel_id"],
                )

            await interaction.followup.send("✅ Backup imported successfully!", ephemeral=True)

            for lb_type in ["all", "mobile"]:
                for cat in ALL_SECTIONS:
                    await update_leaderboard_messages(self.bot, self.pool, guild_id, cat, lb_type)
        except Exception as e:
            await interaction.followup.send(f"❌ Import failed mid-way: {e}\nSome data may be missing — re-import your backup.", ephemeral=True)

    @app_commands.command(name="set-audit-log", description="Set a channel to receive audit logs — can be in another server (owner only)")
    @app_commands.describe(
        channel_id="ID of the channel to send logs to (can be in any server the bot is in)",
        for_guild="Guild ID whose actions to log (leave blank to use this server)",
    )
    async def set_audit_log(self, interaction: discord.Interaction, channel_id: str, for_guild: str = None):
        if not await check_permission(interaction, self.pool, "owner"):
            return

        target_guild_id = for_guild.strip() if for_guild else str(interaction.guild_id)

        # Validate the channel exists and the bot can access it
        try:
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                channel = await self.bot.fetch_channel(int(channel_id))
        except Exception:
            await interaction.response.send_message(
                "❌ Could not find that channel. Check the ID is correct and the bot is in that server.",
                ephemeral=True,
            )
            return

        await db.set_audit_log_channel(self.pool, target_guild_id, channel_id.strip())

        guild_label = f"server `{target_guild_id}`" if for_guild else "this server"
        server_name = channel.guild.name if hasattr(channel, "guild") and channel.guild else "Unknown"
        await interaction.response.send_message(
            f"✅ Audit logs for **{guild_label}** will now be sent to **#{channel.name}** in **{server_name}**.",
            ephemeral=True,
        )

    @app_commands.command(name="set-cooldown", description="Set a challenge cooldown on a player (whitelist only)")
    @app_commands.describe(rank="The player's rank", days="Cooldown duration in days", leaderboard="Which leaderboard")
    @app_commands.choices(leaderboard=LB_CHOICES)
    async def set_cooldown(self, interaction: discord.Interaction, rank: app_commands.Range[int, 1, 100], days: app_commands.Range[int, 1, 365], leaderboard: str = "all"):
        if not await check_permission(interaction, self.pool, "whitelist"):
            return

        guild_id = str(interaction.guild_id)
        player = await db.get_player(self.pool, guild_id, rank, leaderboard)
        if not player:
            await interaction.response.send_message(f"❌ No player at rank **#{rank}** in **{lb_label(leaderboard)}**.", ephemeral=True)
            return

        expires_at = datetime.now(timezone.utc) + timedelta(days=days)
        await db.set_cooldown(self.pool, guild_id, rank, expires_at, leaderboard)

        ts      = int(expires_at.timestamp())
        display = player.get("display_name") or player["roblox_username"]
        await interaction.response.send_message(
            f"✅ Cooldown set on **{display}** (#{rank}) for **{days} day(s)**. Expires <t:{ts}:R>.",
            ephemeral=True,
        )
        await send_audit_log(
            self.bot, self.pool, guild_id,
            "Cooldown Set",
            f"{lb_label(leaderboard)} #{rank} — {display}\nCooldown: {days} days (expires <t:{ts}:R>)",
            interaction.user,
        )

    @app_commands.command(name="clear-cooldown", description="Remove a player's challenge cooldown early (whitelist only)")
    @app_commands.describe(rank="The player's rank", leaderboard="Which leaderboard")
    @app_commands.choices(leaderboard=LB_CHOICES)
    async def clear_cooldown(self, interaction: discord.Interaction, rank: app_commands.Range[int, 1, 100], leaderboard: str = "all"):
        if not await check_permission(interaction, self.pool, "whitelist"):
            return

        guild_id = str(interaction.guild_id)
        player = await db.get_player(self.pool, guild_id, rank, leaderboard)
        if not player:
            await interaction.response.send_message(f"❌ No player at rank **#{rank}** in **{lb_label(leaderboard)}**.", ephemeral=True)
            return

        if not player["cooldown_expires_at"]:
            await interaction.response.send_message(
                f"ℹ️ **{player.get('display_name') or player['roblox_username']}** (#{rank}) has no active cooldown.", ephemeral=True
            )
            return

        display = player.get("display_name") or player["roblox_username"]
        await db.set_cooldown(self.pool, guild_id, rank, None, leaderboard)
        await interaction.response.send_message(f"✅ Cooldown cleared for **{display}** (#{rank}).", ephemeral=True)
        await send_audit_log(
            self.bot, self.pool, guild_id,
            "Cooldown Cleared",
            f"{lb_label(leaderboard)} #{rank} — {display}\nCooldown removed early.",
            interaction.user,
        )

    @app_commands.command(name="season-reset", description="Wipe all players from a leaderboard to start fresh (owner only)")
    @app_commands.describe(leaderboard="Which leaderboard to reset")
    @app_commands.choices(leaderboard=LB_CHOICES)
    async def season_reset(self, interaction: discord.Interaction, leaderboard: str = "all"):
        if not await check_permission(interaction, self.pool, "owner"):
            return

        guild_id = str(interaction.guild_id)
        await db.delete_all_players(self.pool, guild_id, leaderboard)
        await interaction.response.send_message(
            f"✅ All players wiped from **{lb_label(leaderboard)}**. Season reset complete.", ephemeral=True
        )

        for cat in ALL_SECTIONS:
            await update_leaderboard_messages(self.bot, self.pool, guild_id, cat, leaderboard)
        await send_audit_log(
            self.bot, self.pool, guild_id,
            f"Season Reset — {lb_label(leaderboard)}",
            f"All players wiped from {lb_label(leaderboard)}.",
            interaction.user,
        )

    @app_commands.command(name="copy-player", description="Copy a player to another rank or leaderboard (owner only)")
    @app_commands.describe(from_rank="Source rank", to_rank="Destination rank", from_leaderboard="Copy from", to_leaderboard="Copy to (can be different)")
    @app_commands.choices(from_leaderboard=LB_CHOICES, to_leaderboard=LB_CHOICES)
    async def copy_player(self, interaction: discord.Interaction, from_rank: app_commands.Range[int, 1, 100], to_rank: app_commands.Range[int, 1, 100], from_leaderboard: str = "all", to_leaderboard: str = "all"):
        if not await check_permission(interaction, self.pool, "owner"):
            return

        guild_id = str(interaction.guild_id)
        source = await db.get_player(self.pool, guild_id, from_rank, from_leaderboard)
        if not source:
            await interaction.response.send_message(
                f"❌ No player at rank **#{from_rank}** in **{lb_label(from_leaderboard)}**.", ephemeral=True
            )
            return

        await db.upsert_player(
            self.pool, guild_id, to_rank,
            source["roblox_username"], source["discord_user_id"], source["specific_info"],
            to_leaderboard, source.get("display_name", ""),
        )
        display = source.get("display_name") or source["roblox_username"]
        cross = f"{lb_label(from_leaderboard)} → {lb_label(to_leaderboard)}" if from_leaderboard != to_leaderboard else lb_label(from_leaderboard)
        await interaction.response.send_message(
            f"✅ Copied **{display}** from #{from_rank} → #{to_rank} ({cross}).", ephemeral=True
        )

        await update_leaderboard_messages(self.bot, self.pool, guild_id, get_category_for_rank(from_rank), from_leaderboard)
        if to_leaderboard != from_leaderboard or to_rank != from_rank:
            await update_leaderboard_messages(self.bot, self.pool, guild_id, get_category_for_rank(to_rank), to_leaderboard)
        await send_audit_log(
            self.bot, self.pool, guild_id,
            f"Player Copied — {cross}",
            f"#{from_rank} → #{to_rank} | {display}",
            interaction.user,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Management(bot))
