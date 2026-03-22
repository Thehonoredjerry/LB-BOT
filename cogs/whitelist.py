import discord
from discord import app_commands
from discord.ext import commands
import db
from utils.permissions import check_permission, send_audit_log, PERMANENT_OWNER_ID


class Whitelist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def pool(self):
        return self.bot.pool

    @app_commands.command(name="wl-add", description="Add a user to the owner list or whitelist (owner only)")
    @app_commands.describe(user="The user to add", role="Their permission level")
    @app_commands.choices(role=[
        app_commands.Choice(name="Owner",     value="owner"),
        app_commands.Choice(name="Whitelist", value="whitelist"),
    ])
    async def wl_add(self, interaction: discord.Interaction, user: discord.Member, role: str):
        if not await check_permission(interaction, self.pool, "owner"):
            return

        guild_id = str(interaction.guild_id)
        await db.upsert_whitelist(self.pool, guild_id, str(user.id), role)
        await interaction.response.send_message(f"✅ Set <@{user.id}>'s access to **{role}**.", ephemeral=True)
        await send_audit_log(
            self.bot, self.pool, guild_id,
            "Access Granted",
            f"<@{user.id}> granted **{role}** access.",
            interaction.user,
        )

    @app_commands.command(name="wl-list", description="Show all owners and whitelisted users (owner only)")
    async def wl_list(self, interaction: discord.Interaction):
        if not await check_permission(interaction, self.pool, "owner"):
            return

        guild_id = str(interaction.guild_id)
        entries  = await db.get_whitelist(self.pool, guild_id)

        owners      = [e for e in entries if e["role"] == "owner"]
        whitelisted = [e for e in entries if e["role"] == "whitelist"]

        embed = discord.Embed(title="🔑 Bot Access List", color=0x2B2B31)
        embed.add_field(
            name=f"👑 Owners ({len(owners)})",
            value="\n".join(f"<@{e['user_id']}>" for e in owners) or "None",
            inline=False,
        )
        embed.add_field(
            name=f"✅ Whitelisted ({len(whitelisted)})",
            value="\n".join(f"<@{e['user_id']}>" for e in whitelisted) or "None",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="wl-remove", description="Remove a user's bot access (owner only)")
    @app_commands.describe(user="The user to remove")
    async def wl_remove(self, interaction: discord.Interaction, user: discord.Member):
        if not await check_permission(interaction, self.pool, "owner"):
            return

        if str(user.id) == PERMANENT_OWNER_ID:
            await interaction.response.send_message("❌ This user cannot be removed.", ephemeral=True)
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message("❌ You cannot remove yourself.", ephemeral=True)
            return

        guild_id = str(interaction.guild_id)
        removed  = await db.delete_whitelist(self.pool, guild_id, str(user.id))
        if not removed:
            await interaction.response.send_message(f"❌ <@{user.id}> is not in the access list.", ephemeral=True)
            return

        await interaction.response.send_message(f"✅ Removed <@{user.id}>'s bot access.", ephemeral=True)
        await send_audit_log(
            self.bot, self.pool, guild_id,
            "Access Revoked",
            f"<@{user.id}>'s bot access removed.",
            interaction.user,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
