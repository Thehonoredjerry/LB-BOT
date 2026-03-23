import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncpg
import os
import db
from utils.leaderboard import update_leaderboard_messages, get_category_for_rank


class LeaderboardBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.pool: asyncpg.Pool = None

    async def setup_hook(self):
        try:
            self.pool = await db.create_pool()
            print("[DB] Connected to PostgreSQL")
        except Exception as e:
            print(f"[DB] FATAL: Could not connect or create tables — {e}")
            raise

        await self.load_extension("cogs.leaderboard")
        await self.load_extension("cogs.management")
        await self.load_extension("cogs.whitelist")
        print("[Bot] Cogs loaded")

        await self.tree.sync()
        print("[Bot] Slash commands synced globally")

    async def on_app_command_completion(
        self, interaction: discord.Interaction, command: app_commands.Command | app_commands.ContextMenu
    ):
        guild_name = interaction.guild.name if interaction.guild else "DM"
        user = interaction.user
        print(f"[{guild_name}] /{command.name} — {user.display_name} ({user.id})")

    async def on_ready(self):
        print(f"[Bot] Logged in as {self.user} (ID: {self.user.id})")
        guild_list = ", ".join(f"{g.name} ({g.id})" for g in self.guilds)
        print(f"[Bot] Active in {len(self.guilds)} server(s): {guild_list}")
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Jerry",
        ))

        # Clear any guild-specific commands to eliminate duplicates and stale commands
        for guild in self.guilds:
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
        print(f"[Bot] Cleared guild-specific commands from {len(self.guilds)} server(s)")

        self.cooldown_cleanup.start()

    @tasks.loop(hours=1)
    async def cooldown_cleanup(self):
        try:
            expired = await self.pool.fetch(
                "SELECT guild_id, rank, lb_type FROM players WHERE cooldown_expires_at IS NOT NULL AND cooldown_expires_at <= NOW()"
            )
            if not expired:
                return

            await self.pool.execute(
                "UPDATE players SET cooldown_expires_at = NULL WHERE cooldown_expires_at IS NOT NULL AND cooldown_expires_at <= NOW()"
            )

            done = set()
            for row in expired:
                key = (row["guild_id"], get_category_for_rank(row["rank"]), row["lb_type"])
                if key not in done:
                    done.add(key)
                    guild = self.get_guild(int(row["guild_id"]))
                    guild_name = guild.name if guild else row["guild_id"]
                    print(f"[{guild_name}] Cooldown expired for rank #{row['rank']} ({row['lb_type']})")
                    await update_leaderboard_messages(self, self.pool, row["guild_id"], get_category_for_rank(row["rank"]), row["lb_type"])

            print(f"[Cooldown] Cleared {len(expired)} expired cooldown(s) across all servers")
        except Exception as e:
            print(f"[Cooldown] Cleanup error: {e}")

    async def close(self):
        self.cooldown_cleanup.cancel()
        if self.pool:
            await self.pool.close()
        await super().close()
