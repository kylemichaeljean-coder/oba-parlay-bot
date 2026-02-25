import discord
from discord.ext import commands, tasks
import os
import asyncio
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

active_parlays = {}
leaderboard = {}

# ---------------- READY ----------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# ---------------- PARLAY ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def parlay(ctx, name: str, *args):

    if len(args) < 2 or len(args) % 2 != 0:
        await ctx.send("Usage: !parlay <name> <team> <odds> <team> <odds> ...")
        return

    teams = [(args[i], args[i+1]) for i in range(0, len(args), 2)]

    embed = discord.Embed(
        title=f"🔥 {name}",
        description="React below to vote!\n\n",
        color=discord.Color.green()
    )

    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

    for i, (team, odds) in enumerate(teams):
        embed.description += f"{emojis[i]} **{team}** (+{odds})\n"

    embed.set_footer(text="⏳ Auto locks in 1 hour")

    message = await ctx.send(embed=embed)

    for i in range(len(teams)):
        await message.add_reaction(emojis[i])

    active_parlays[message.id] = {
        "name": name,
        "teams": teams,
        "message": message,
        "end_time": datetime.utcnow() + timedelta(hours=1),
        "locked": False
    }

    asyncio.create_task(auto_lock(message.id))

# ---------------- AUTO LOCK ----------------

async def auto_lock(message_id):
    await asyncio.sleep(3600)

    parlay = active_parlays.get(message_id)
    if not parlay or parlay["locked"]:
        return

    await finalize_parlay(message_id)

# ---------------- CLOSE EARLY ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def close(ctx):
    if not ctx.message.reference:
        await ctx.send("Reply to a parlay message to close it.")
        return

    message_id = ctx.message.reference.message_id

    if message_id not in active_parlays:
        await ctx.send("That message is not an active parlay.")
        return

    await finalize_parlay(message_id)

# ---------------- FINALIZE ----------------

async def finalize_parlay(message_id):

    parlay = active_parlays.get(message_id)
    if not parlay:
        return

    message = parlay["message"]
    parlay["locked"] = True

    message = await message.channel.fetch_message(message_id)

    results = []

    for reaction in message.reactions:
        if reaction.emoji in ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]:
            results.append((reaction.emoji, reaction.count - 1))

    winner = max(results, key=lambda x: x[1], default=None)

    embed = message.embeds[0]

    embed.color = discord.Color.red()
    embed.set_footer(text="🔒 Locked")

    if winner:
        index = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"].index(winner[0])
        team_name = parlay["teams"][index][0]
        embed.add_field(name="🏆 Winner", value=team_name, inline=False)

    await message.edit(embed=embed)

    active_parlays.pop(message_id, None)

# ---------------- LEADERBOARD ----------------

@bot.command()
async def leaderboard_cmd(ctx):

    if not leaderboard:
        await ctx.send("No leaderboard data yet.")
        return

    sorted_board = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)

    text = ""
    for user, points in sorted_board:
        text += f"{user}: {points}\n"

    embed = discord.Embed(title="🏆 Leaderboard", description=text, color=discord.Color.gold())
    await ctx.send(embed=embed)

# ---------------- RUN ----------------

bot.run(os.getenv("DISCORD_TOKEN"))
