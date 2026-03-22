import discord


async def apply_lb_role(
    bot: discord.Client,
    guild_id: str,
    discord_user_id: str,
    role_id: str,
    action: str,
) -> None:
    """Add or remove the leaderboard role from a member. Logs all outcomes, never raises."""
    try:
        guild = bot.get_guild(int(guild_id))
        if not guild:
            print(f"[Guild {guild_id}] Role sync: guild not in cache, skipping")
            return

        role = guild.get_role(int(role_id))
        if not role:
            print(f"[{guild.name}] Role sync: role {role_id} not found")
            return

        try:
            member = await guild.fetch_member(int(discord_user_id))
        except discord.NotFound:
            print(f"[{guild.name}] Role sync: member {discord_user_id} not in this server")
            return
        except Exception as e:
            print(f"[{guild.name}] Role sync: could not fetch member {discord_user_id} — {e}")
            return

        if action == "add":
            await member.add_roles(role, reason="Added to leaderboard")
            print(f"[{guild.name}] Role sync: gave '{role.name}' to {member.display_name}")
        elif action == "remove":
            await member.remove_roles(role, reason="Removed from leaderboard")
            print(f"[{guild.name}] Role sync: removed '{role.name}' from {member.display_name}")

    except discord.Forbidden:
        print(
            f"[Guild {guild_id}] Role sync: missing Manage Roles permission "
            "or the role is above the bot's highest role"
        )
    except Exception as e:
        print(f"[Guild {guild_id}] Role sync error: {e}")
