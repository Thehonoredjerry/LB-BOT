import asyncpg
import os
from datetime import datetime
from typing import Optional


async def create_pool() -> asyncpg.Pool:
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], command_timeout=30)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    id SERIAL PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    roblox_username TEXT NOT NULL,
                    discord_user_id TEXT NOT NULL,
                    specific_info TEXT NOT NULL,
                    cooldown_expires_at TIMESTAMP,
                    display_name TEXT NOT NULL DEFAULT '',
                    lb_type TEXT NOT NULL DEFAULT 'all',
                    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS leaderboard_messages (
                    id SERIAL PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '1_10',
                    lb_type TEXT NOT NULL DEFAULT 'all'
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS whitelist (
                    id SERIAL PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'whitelist'
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log_channels (
                    id SERIAL PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS leaderboard_roles (
                    guild_id TEXT NOT NULL,
                    leaderboard TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    PRIMARY KEY (guild_id, leaderboard)
                )
            """)
    print("[DB] All tables verified/created")
    return pool


async def get_player(pool: asyncpg.Pool, guild_id: str, rank: int, lb_type: str = "all") -> Optional[asyncpg.Record]:
    return await pool.fetchrow(
        "SELECT * FROM players WHERE guild_id = $1 AND rank = $2 AND lb_type = $3",
        guild_id, rank, lb_type,
    )


async def get_all_players(pool: asyncpg.Pool, guild_id: str, lb_type: str = "all") -> list[asyncpg.Record]:
    return await pool.fetch(
        "SELECT * FROM players WHERE guild_id = $1 AND lb_type = $2 ORDER BY rank",
        guild_id, lb_type,
    )


async def get_players_in_range(pool: asyncpg.Pool, guild_id: str, start: int, end: int, lb_type: str = "all") -> list[asyncpg.Record]:
    return await pool.fetch(
        "SELECT * FROM players WHERE guild_id = $1 AND rank >= $2 AND rank <= $3 AND lb_type = $4 ORDER BY rank",
        guild_id, start, end, lb_type,
    )


async def upsert_player(
    pool: asyncpg.Pool,
    guild_id: str,
    rank: int,
    roblox_username: str,
    discord_user_id: str,
    specific_info: str,
    lb_type: str = "all",
    display_name: str = "",
) -> None:
    existing = await get_player(pool, guild_id, rank, lb_type)
    if existing:
        await pool.execute(
            """UPDATE players SET roblox_username=$1, discord_user_id=$2, specific_info=$3,
               display_name=$4, updated_at=NOW() WHERE guild_id=$5 AND rank=$6 AND lb_type=$7""",
            roblox_username, discord_user_id, specific_info, display_name, guild_id, rank, lb_type,
        )
    else:
        await pool.execute(
            """INSERT INTO players (guild_id, rank, roblox_username, discord_user_id, specific_info, lb_type, display_name)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            guild_id, rank, roblox_username, discord_user_id, specific_info, lb_type, display_name,
        )


async def delete_player(pool: asyncpg.Pool, guild_id: str, rank: int, lb_type: str = "all") -> bool:
    result = await pool.execute(
        "DELETE FROM players WHERE guild_id = $1 AND rank = $2 AND lb_type = $3",
        guild_id, rank, lb_type,
    )
    return result != "DELETE 0"


async def delete_players_in_range(pool: asyncpg.Pool, guild_id: str, start: int, end: int, lb_type: str = "all") -> None:
    await pool.execute(
        "DELETE FROM players WHERE guild_id = $1 AND rank >= $2 AND rank <= $3 AND lb_type = $4",
        guild_id, start, end, lb_type,
    )


async def delete_all_players(pool: asyncpg.Pool, guild_id: str, lb_type: Optional[str] = None) -> None:
    if lb_type:
        await pool.execute("DELETE FROM players WHERE guild_id = $1 AND lb_type = $2", guild_id, lb_type)
    else:
        await pool.execute("DELETE FROM players WHERE guild_id = $1", guild_id)


async def set_cooldown(pool: asyncpg.Pool, guild_id: str, rank: int, expires_at: Optional[datetime], lb_type: str = "all") -> None:
    await pool.execute(
        "UPDATE players SET cooldown_expires_at=$1, updated_at=NOW() WHERE guild_id=$2 AND rank=$3 AND lb_type=$4",
        expires_at, guild_id, rank, lb_type,
    )


async def get_leaderboard_messages(
    pool: asyncpg.Pool, guild_id: str, category: str, lb_type: str = "all"
) -> list[asyncpg.Record]:
    return await pool.fetch(
        "SELECT * FROM leaderboard_messages WHERE guild_id = $1 AND category = $2 AND lb_type = $3",
        guild_id, category, lb_type,
    )


async def delete_leaderboard_messages(pool: asyncpg.Pool, guild_id: str, category: str, lb_type: str = "all") -> None:
    await pool.execute(
        "DELETE FROM leaderboard_messages WHERE guild_id = $1 AND category = $2 AND lb_type = $3",
        guild_id, category, lb_type,
    )


async def insert_leaderboard_message(
    pool: asyncpg.Pool, guild_id: str, channel_id: str, message_id: str, category: str, lb_type: str = "all"
) -> None:
    await pool.execute(
        "INSERT INTO leaderboard_messages (guild_id, channel_id, message_id, category, lb_type) VALUES ($1,$2,$3,$4,$5)",
        guild_id, channel_id, message_id, category, lb_type,
    )


async def get_whitelist(pool: asyncpg.Pool, guild_id: str) -> list[asyncpg.Record]:
    return await pool.fetch("SELECT * FROM whitelist WHERE guild_id = $1", guild_id)


async def get_whitelist_entry(pool: asyncpg.Pool, guild_id: str, user_id: str) -> Optional[asyncpg.Record]:
    return await pool.fetchrow(
        "SELECT * FROM whitelist WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
    )


async def upsert_whitelist(pool: asyncpg.Pool, guild_id: str, user_id: str, role: str) -> None:
    existing = await get_whitelist_entry(pool, guild_id, user_id)
    if existing:
        await pool.execute(
            "UPDATE whitelist SET role=$1 WHERE guild_id=$2 AND user_id=$3", role, guild_id, user_id
        )
    else:
        await pool.execute(
            "INSERT INTO whitelist (guild_id, user_id, role) VALUES ($1,$2,$3)", guild_id, user_id, role
        )


async def delete_whitelist(pool: asyncpg.Pool, guild_id: str, user_id: str) -> bool:
    result = await pool.execute(
        "DELETE FROM whitelist WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
    )
    return result != "DELETE 0"


async def get_audit_log_channel(pool: asyncpg.Pool, guild_id: str) -> Optional[asyncpg.Record]:
    return await pool.fetchrow(
        "SELECT * FROM audit_log_channels WHERE guild_id = $1", guild_id
    )


async def set_audit_log_channel(pool: asyncpg.Pool, guild_id: str, channel_id: str) -> None:
    await pool.execute("DELETE FROM audit_log_channels WHERE guild_id = $1", guild_id)
    await pool.execute(
        "INSERT INTO audit_log_channels (guild_id, channel_id) VALUES ($1,$2)", guild_id, channel_id
    )


async def get_lb_role(pool: asyncpg.Pool, guild_id: str, leaderboard: str) -> Optional[asyncpg.Record]:
    return await pool.fetchrow(
        "SELECT role_id FROM leaderboard_roles WHERE guild_id = $1 AND leaderboard = $2",
        guild_id, leaderboard,
    )


async def set_lb_role(pool: asyncpg.Pool, guild_id: str, leaderboard: str, role_id: str) -> None:
    await pool.execute(
        """INSERT INTO leaderboard_roles (guild_id, leaderboard, role_id) VALUES ($1,$2,$3)
           ON CONFLICT (guild_id, leaderboard) DO UPDATE SET role_id = EXCLUDED.role_id""",
        guild_id, leaderboard, role_id,
    )


async def clear_lb_role(pool: asyncpg.Pool, guild_id: str, leaderboard: str) -> None:
    await pool.execute(
        "DELETE FROM leaderboard_roles WHERE guild_id = $1 AND leaderboard = $2",
        guild_id, leaderboard,
    )
