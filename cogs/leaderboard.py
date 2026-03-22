import discord
from discord import app_commands
from discord.ext import commands
import db
from utils.permissions import check_permission, send_audit_log
from utils.leaderboard import (
    build_leaderboard_embeds, update_leaderboard_messages,
    get_category_for_rank, CATEGORY_RANGES, SECTION_CHOICES, lb_label,
)
from utils.roblox import get_roblox_user_id

LB_CHOICES = [
    app_commands.Choice(name="Top All",    value="all"),
    app_commands.Choice(name="Top Mobile", value="mobile"),
]

SECTION_APP_CHOICES = [
    app_commands.Choice(name=label, value=value)
    for label, value in SECTION_CHOICES
]


class SetPlayerModal(discord.ui.Modal):
    display_name    = discord.ui.TextInput(label="Name (shown in embed author)", placeholder="e.g. Banjo", required=True)
    roblox_username = discord.ui.TextInput(label="Roblox Username", required=True)
    discord_user_id = discord.ui.TextInput(
        label="Discord User ID",
        placeholder="e.g. 123456789012345678",
        required=True,
    )
    specific_info   = discord.ui.TextInput(
        label="Specific Info (score, wins, etc.)",
        style=discord.TextStyle.paragraph,
        required=True,
    )

    def __init__(self, rank: int, lb_type: str, existing=None):
        super().__init__(title=f"Set Player #{rank} [{lb_label(lb_type)}]", timeout=300)
        self.rank        = rank
        self.lb_type     = lb_type
        self.interaction = None
        if existing:
            self.display_name.default    = existing.get("display_name", "")
            self.roblox_username.default = existing["roblox_username"]
            self.discord_user_id.default = existing["discord_user_id"]
            self.specific_info.default   = existing["specific_info"]

    async def on_submit(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.stop()


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def pool(self):
        return self.bot.pool

    @app_commands.command(name="set-player", description="Set a player's leaderboard entry via a form popup")
    @app_commands.describe(rank="The rank to set (1-100)", leaderboard="Which leaderboard")
    @app_commands.choices(leaderboard=LB_CHOICES)
    async def set_player(self, interaction: discord.Interaction, rank: app_commands.Range[int, 1, 100], leaderboard: str = "all"):
        if not await check_permission(interaction, self.pool, "whitelist"):
            return

        existing = await db.get_player(self.pool, str(interaction.guild_id), rank, leaderboard)
        modal = SetPlayerModal(rank, leaderboard, existing)
        await interaction.response.send_modal(modal)
        await modal.wait()

        # Modal was dismissed or timed out without submitting
        if modal.interaction is None:
            return

        # Defer immediately — Roblox API can take >3s and would time out otherwise
        await modal.interaction.response.defer(ephemeral=True)

        display_name    = modal.display_name.value.strip()
        roblox_username = modal.roblox_username.value.strip()
        discord_user_id = modal.discord_user_id.value.strip()
        specific_info   = modal.specific_info.value.strip()

        # Validate Roblox username exists
        roblox_id = await get_roblox_user_id(roblox_username)
        if roblox_id is None:
            await modal.interaction.followup.send(
                f"❌ Roblox username **{roblox_username}** does not exist. Please check the spelling and try again.",
                ephemeral=True,
            )
            return

        await db.upsert_player(
            self.pool, str(interaction.guild_id), rank,
            roblox_username, discord_user_id, specific_info, leaderboard, display_name,
        )

        await modal.interaction.followup.send(
            f"✅ **#{rank}** (**{display_name}**) set in **{lb_label(leaderboard)}**.", ephemeral=True
        )

        category = get_category_for_rank(rank)
        await update_leaderboard_messages(self.bot, self.pool, str(interaction.guild_id), category, leaderboard)
        await send_audit_log(
            self.bot, self.pool, str(interaction.guild_id),
            f"Player Set — {lb_label(leaderboard)}",
            f"{lb_label(leaderboard)} #{rank} — {display_name}\nRoblox: {roblox_username} | {specific_info}",
            interaction.user,
        )

    @app_commands.command(name="clear-player", description="Remove a player from the leaderboard")
    @app_commands.describe(rank="The rank to clear (1-100)", leaderboard="Which leaderboard", shift="Leave vacant or shift players up within the same section")
    @app_commands.choices(
        leaderboard=LB_CHOICES,
        shift=[
            app_commands.Choice(name="Leave Vacant", value="vacant"),
            app_commands.Choice(name="Shift Up",     value="shift"),
        ],
    )
    async def clear_player(self, interaction: discord.Interaction, rank: app_commands.Range[int, 1, 100], leaderboard: str = "all", shift: str = "vacant"):
        if not await check_permission(interaction, self.pool, "whitelist"):
            return

        guild_id = str(interaction.guild_id)
        player = await db.get_player(self.pool, guild_id, rank, leaderboard)
        if not player:
            await interaction.response.send_message(f"❌ Rank **#{rank}** is already vacant in **{lb_label(leaderboard)}**.", ephemeral=True)
            return

        username = player["roblox_username"]
        display  = player.get("display_name") or username
        category = get_category_for_rank(rank)

        if shift == "shift":
            _, section_end = CATEGORY_RANGES[category]
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM players WHERE guild_id=$1 AND rank=$2 AND lb_type=$3",
                    guild_id, rank, leaderboard,
                )
                for r in range(rank + 1, section_end + 1):
                    await conn.execute(
                        "UPDATE players SET rank=$1, updated_at=NOW() WHERE guild_id=$2 AND rank=$3 AND lb_type=$4",
                        r - 1, guild_id, r, leaderboard,
                    )
            await interaction.response.send_message(
                f"✅ Cleared **#{rank}** (was **{display}**) and shifted **#{rank+1}–{section_end}** up in **{lb_label(leaderboard)}**.",
                ephemeral=True,
            )
            await send_audit_log(
                self.bot, self.pool, guild_id,
                f"Player Cleared — {lb_label(leaderboard)}",
                f"{lb_label(leaderboard)} #{rank} — {display}\nShifted #{rank+1}–{section_end} up.",
                interaction.user,
            )
        else:
            await db.delete_player(self.pool, guild_id, rank, leaderboard)
            await interaction.response.send_message(
                f"✅ Cleared **#{rank}** (was **{display}**) in **{lb_label(leaderboard)}**.", ephemeral=True
            )
            await send_audit_log(
                self.bot, self.pool, guild_id,
                f"Player Cleared — {lb_label(leaderboard)}",
                f"{lb_label(leaderboard)} #{rank} — {display}\nSlot set to vacant.",
                interaction.user,
            )

        await update_leaderboard_messages(self.bot, self.pool, guild_id, category, leaderboard)

    @app_commands.command(name="swap-players", description="Swap two players' positions on the leaderboard")
    @app_commands.describe(rank1="First rank (1-100)", rank2="Second rank (1-100)", leaderboard="Which leaderboard")
    @app_commands.choices(leaderboard=LB_CHOICES)
    async def swap_players(self, interaction: discord.Interaction, rank1: app_commands.Range[int, 1, 100], rank2: app_commands.Range[int, 1, 100], leaderboard: str = "all"):
        if not await check_permission(interaction, self.pool, "whitelist"):
            return

        if rank1 == rank2:
            await interaction.response.send_message("❌ The two ranks must be different.", ephemeral=True)
            return

        guild_id = str(interaction.guild_id)
        p1 = await db.get_player(self.pool, guild_id, rank1, leaderboard)
        p2 = await db.get_player(self.pool, guild_id, rank2, leaderboard)

        async with self.pool.acquire() as conn:
            if p1:
                await conn.execute(
                    "UPDATE players SET rank=$1, updated_at=NOW() WHERE id=$2",
                    rank2, p1["id"],
                )
            if p2:
                await conn.execute(
                    "UPDATE players SET rank=$1, updated_at=NOW() WHERE id=$2",
                    rank1, p2["id"],
                )

        n1 = (p1.get("display_name") or p1["roblox_username"]) if p1 else "VACANT"
        n2 = (p2.get("display_name") or p2["roblox_username"]) if p2 else "VACANT"
        await interaction.response.send_message(
            f"✅ Swapped **#{rank1}** ({n1}) ↔ **#{rank2}** ({n2}) in **{lb_label(leaderboard)}**.", ephemeral=True
        )

        cats = {get_category_for_rank(rank1), get_category_for_rank(rank2)}
        for cat in cats:
            await update_leaderboard_messages(self.bot, self.pool, guild_id, cat, leaderboard)
        await send_audit_log(
            self.bot, self.pool, guild_id,
            f"Players Swapped — {lb_label(leaderboard)}",
            f"#{rank1} {n1} ↔ #{rank2} {n2}",
            interaction.user,
        )

    @app_commands.command(name="post-leaderboard", description="Post a leaderboard section to a channel")
    @app_commands.describe(section="Which rank section to post", channel="The channel to post to", leaderboard="Which leaderboard")
    @app_commands.choices(section=SECTION_APP_CHOICES, leaderboard=LB_CHOICES)
    async def post_leaderboard(self, interaction: discord.Interaction, section: str, channel: discord.TextChannel, leaderboard: str = "all"):
        if not await check_permission(interaction, self.pool, "whitelist"):
            return

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)

        await db.delete_leaderboard_messages(self.pool, guild_id, section, leaderboard)
        embeds = await build_leaderboard_embeds(self.pool, guild_id, section, leaderboard)
        msg = await channel.send(embeds=embeds)
        await db.insert_leaderboard_message(self.pool, guild_id, str(channel.id), str(msg.id), section, leaderboard)

        start, end = CATEGORY_RANGES[section]
        await interaction.followup.send(
            f"✅ **{lb_label(leaderboard)}** ranks **{start}–{end}** posted to {channel.mention}.", ephemeral=True
        )
        await send_audit_log(
            self.bot, self.pool, guild_id,
            f"Leaderboard Posted — {lb_label(leaderboard)}",
            f"Ranks {start}–{end} posted to {channel.mention}",
            interaction.user,
        )

    @app_commands.command(name="edit-leaderboard", description="Point the bot to an existing leaderboard message to auto-update")
    @app_commands.describe(message_id="The message ID of the existing leaderboard", channel="The channel containing the message", section="Which rank section this message represents", leaderboard="Which leaderboard")
    @app_commands.choices(section=SECTION_APP_CHOICES, leaderboard=LB_CHOICES)
    async def edit_leaderboard(self, interaction: discord.Interaction, message_id: str, channel: discord.TextChannel, section: str, leaderboard: str = "all"):
        if not await check_permission(interaction, self.pool, "whitelist"):
            return

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)

        try:
            msg = await channel.fetch_message(int(message_id))
            embeds = await build_leaderboard_embeds(self.pool, guild_id, section, leaderboard)
            await msg.edit(embeds=embeds)

            await db.delete_leaderboard_messages(self.pool, guild_id, section, leaderboard)
            await db.insert_leaderboard_message(self.pool, guild_id, str(channel.id), str(msg.id), section, leaderboard)

            start, end = CATEGORY_RANGES[section]
            await interaction.followup.send(
                f"✅ **{lb_label(leaderboard)}** ranks **{start}–{end}** registered and updated.", ephemeral=True
            )
            await send_audit_log(
                self.bot, self.pool, guild_id,
                f"Leaderboard Registered — {lb_label(leaderboard)}",
                f"Ranks {start}–{end} | Message {message_id} in {channel.mention}",
                interaction.user,
            )
        except Exception:
            await interaction.followup.send("❌ Could not find that message. Check the message ID and channel.", ephemeral=True)

    @app_commands.command(name="leaderboard-status", description="See which sections are posted and how many slots are vacant")
    @app_commands.describe(leaderboard="Which leaderboard to check")
    @app_commands.choices(leaderboard=LB_CHOICES)
    async def leaderboard_status(self, interaction: discord.Interaction, leaderboard: str = "all"):
        if not await check_permission(interaction, self.pool, "whitelist"):
            return

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        players = await db.get_all_players(self.pool, guild_id, leaderboard)
        filled = {p["rank"] for p in players}

        embed = discord.Embed(title=f"📊 {lb_label(leaderboard)} — Leaderboard Status", color=0x2B2B31)
        for label, key in SECTION_CHOICES:
            start, end = CATEGORY_RANGES[key]
            slots = list(range(start, end + 1))
            vacant_count = sum(1 for r in slots if r not in filled)
            messages = await db.get_leaderboard_messages(self.pool, guild_id, key, leaderboard)
            posted = "✅ Posted" if messages else "❌ Not posted"
            embed.add_field(
                name=label,
                value=f"{posted}\n🕳️ Vacant: **{vacant_count}/10**",
                inline=True,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)


    @app_commands.command(name="cooldown-overview", description="Show all players currently on cooldown")
    @app_commands.describe(leaderboard="Which leaderboard to check")
    @app_commands.choices(leaderboard=LB_CHOICES)
    async def cooldown_overview(self, interaction: discord.Interaction, leaderboard: str = "all"):
        if not await check_permission(interaction, self.pool, "whitelist"):
            return

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)

        rows = await self.pool.fetch(
            """SELECT rank, display_name, roblox_username, cooldown_expires_at
               FROM players WHERE guild_id=$1 AND lb_type=$2
               AND cooldown_expires_at IS NOT NULL AND cooldown_expires_at > NOW()
               ORDER BY rank""",
            guild_id, leaderboard,
        )

        embed = discord.Embed(title=f"⏱️ {lb_label(leaderboard)} — Active Cooldowns", color=0x2B2B31)

        if not rows:
            embed.description = "No active cooldowns."
        else:
            lines = []
            for row in rows:
                name = row["display_name"] or row["roblox_username"]
                ts   = int(row["cooldown_expires_at"].timestamp())
                lines.append(f"**#{row['rank']}** {name} — expires <t:{ts}:R>")
            embed.description = "\n".join(lines)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="expand-leaderboard", description="Post an expansion section to a channel (owner only)")
    @app_commands.describe(section="Which rank section to expand", channel="The channel to post to", leaderboard="Which leaderboard")
    @app_commands.choices(section=SECTION_APP_CHOICES, leaderboard=LB_CHOICES)
    async def expand_leaderboard(self, interaction: discord.Interaction, section: str, channel: discord.TextChannel, leaderboard: str = "all"):
        if not await check_permission(interaction, self.pool, "owner"):
            return

        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)

        await db.delete_leaderboard_messages(self.pool, guild_id, section, leaderboard)
        embeds = await build_leaderboard_embeds(self.pool, guild_id, section, leaderboard)
        msg = await channel.send(embeds=embeds)
        await db.insert_leaderboard_message(self.pool, guild_id, str(channel.id), str(msg.id), section, leaderboard)

        start, end = CATEGORY_RANGES[section]
        await interaction.followup.send(
            f"✅ **{lb_label(leaderboard)}** ranks **{start}–{end}** posted to {channel.mention}.", ephemeral=True
        )
        await send_audit_log(
            self.bot, self.pool, guild_id,
            f"Expansion Posted — {lb_label(leaderboard)}",
            f"Ranks {start}–{end} posted to {channel.mention}",
            interaction.user,
        )

    @app_commands.command(name="remove-expansion", description="Remove an expansion section and clear all its player data (owner only)")
    @app_commands.describe(section="Which rank section to remove", leaderboard="Which leaderboard")
    @app_commands.choices(section=SECTION_APP_CHOICES, leaderboard=LB_CHOICES)
    async def remove_expansion(self, interaction: discord.Interaction, section: str, leaderboard: str = "all"):
        if not await check_permission(interaction, self.pool, "owner"):
            return

        guild_id = str(interaction.guild_id)
        start, end = CATEGORY_RANGES[section]

        await db.delete_leaderboard_messages(self.pool, guild_id, section, leaderboard)
        await db.delete_players_in_range(self.pool, guild_id, start, end, leaderboard)

        await interaction.response.send_message(
            f"✅ **{lb_label(leaderboard)}** ranks **{start}–{end}** removed and all players cleared.", ephemeral=True
        )
        await send_audit_log(
            self.bot, self.pool, guild_id,
            f"Expansion Removed — {lb_label(leaderboard)}",
            f"Ranks {start}–{end} removed and players cleared.",
            interaction.user,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))
