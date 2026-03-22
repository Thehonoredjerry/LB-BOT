-- Run this once to set up the database schema locally
-- psql -U your_user -d your_db -f schema.sql

DO $$ BEGIN
    CREATE TYPE whitelist_role AS ENUM ('owner', 'whitelist');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

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
);

CREATE TABLE IF NOT EXISTS leaderboard_messages (
    id SERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '1_10',
    lb_type TEXT NOT NULL DEFAULT 'all'
);

CREATE TABLE IF NOT EXISTS whitelist (
    id SERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role whitelist_role NOT NULL DEFAULT 'whitelist'
);

CREATE TABLE IF NOT EXISTS audit_log_channels (
    id SERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL
);
