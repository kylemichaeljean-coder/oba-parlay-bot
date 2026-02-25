import os
import discord
from discord.ext import commands
from database import init_db, get_connection
from parlay_manager import ParlayManager, EMOJIS
import time

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

init_db()
manager = ParlayManager(bot)

# -----------------------------
# ON READY (Resume Timers)
# -----------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT message_id FROM parlays
        WHERE closed=0 AND finalized=0
    """)
    rows = cursor.fetchall()
    conn.close()

    for (message_id,) in rows:
        await manager.start_timer(message_id)

# -----------------------------
# CREATE PARLAY
# -----------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def parlay(ctx, name: str, *args):
    if len(args) < 2 or len(args) % 2 != 0:
    await ctx.send("Usage: !parlay <name> <team> <odds> <team> <odds> ...")
    return

    pairs = [(args[i], args[i+1]) for i in range(0, len(args), 2)]

    await manager.create_parlay(ctx, name, pairs)

# -----------------------------
# CLOSE EARLY
# -----------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def close(ctx):
    if not ctx.message.reference:
        await ctx.message.delete()
        return

    message_id = ctx.message.reference.message_id

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE parlays SET closed=1 WHERE message_id=?
    """, (message_id,))

    conn.commit()
    conn.close()

    await manager.update_embed(message_id)
    await ctx.message.delete()

# -----------------------------
# SET WINNER
# -----------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def setwinner(ctx, winning_emoji: str, odds: int):
    if not ctx.message.reference:
        await ctx.message.delete()
        return

    message_id = ctx.message.reference.message_id

    points = odds // 100

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT guild_id FROM parlays WHERE message_id=?
    """, (message_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        await ctx.message.delete()
        return

    guild_id = row[0]

    cursor.execute("""
        SELECT user_id FROM picks
        WHERE message_id=? AND emoji=?
    """, (message_id, winning_emoji))
    winners = cursor.fetchall()

    for (user_id,) in winners:
        cursor.execute("""
            INSERT INTO users (guild_id, user_id, correct, points)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET
            correct = correct + 1,
            points = points + ?
        """, (guild_id, user_id, points, points))

    cursor.execute("""
        UPDATE parlays SET finalized=1 WHERE message_id=?
    """, (message_id,))

    conn.commit()
    conn.close()

    await manager.update_embed(message_id)
    await ctx.message.delete()

# -----------------------------
# LEADERBOARD
# -----------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def leaderboard(ctx):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, correct, points
        FROM users
        WHERE guild_id=?
        ORDER BY points DESC
    """, (ctx.guild.id,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await ctx.message.delete()
        return

    embed = discord.Embed(
        title="📊 Leaderboard",
        color=discord.Color.blue()
    )

    for i, (user_id, correct, points) in enumerate(rows[:10], start=1):
        embed.add_field(
            name=f"{i}. <@{user_id}>",
            value=f"{correct} correct | {points} pts",
            inline=False
        )

    await ctx.send(embed=embed)
    await ctx.message.delete()

# -----------------------------
# REACTION EVENT
# -----------------------------
@bot.event
async def on_reaction_add(reaction, user):
    await manager.handle_reaction(reaction, user)

# -----------------------------
# PERMISSION ERROR CLEANUP
# -----------------------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.message.delete()

bot.run(os.getenv("DISCORD_TOKEN"))
