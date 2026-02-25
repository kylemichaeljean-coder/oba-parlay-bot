import discord
from discord.ext import commands
import os
import asyncio
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

active_parlays = {}

EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

# ---------------- READY ----------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# ---------------- UTIL ----------------

def build_bar(percent):
    filled = int(percent / 10)
    return "▰" * filled + "▱" * (10 - filled)

async def update_embed(message_id):
    parlay = active_parlays.get(message_id)
    if not parlay:
        return

    message = await parlay["message"].channel.fetch_message(message_id)
    embed = message.embeds[0]

    total_votes = 0
    counts = []

    for reaction in message.reactions:
        if reaction.emoji in EMOJIS:
            count = reaction.count - 1
            counts.append(count)
            total_votes += count

    new_description = "React below to vote!\n\n"

    for i, (team, odds) in enumerate(parlay["teams"]):
        votes = counts[i] if i < len(counts) else 0
        percent = (votes / total_votes * 100) if total_votes > 0 else 0
        bar = build_bar(percent)
        new_description += f"{EMOJIS[i]} **{team}** (+{odds})\n{bar} {int(percent)}%\n\n"

    embed.description = new_description
    await message.edit(embed=embed)

# ---------------- PARLAY ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def parlay(ctx, name: str, *args):

    await ctx.message.delete()

    if len(args) < 2 or len(args) % 2 != 0:
        return

    teams = [(args[i], args[i+1]) for i in range(0, len(args), 2)]

    embed = discord.Embed(
        title=f"🔥 {name}",
        description="React below to vote!\n\n",
        color=discord.Color.green()
    )

    for i, (team, odds) in enumerate(teams):
        embed.description += f"{EMOJIS[i]} **{team}** (+{odds})\n"

    embed.set_footer(text="⏳ Auto locks in 1 hour")

    message = await ctx.send(embed=embed)

    for i in range(len(teams)):
        await message.add_reaction(EMOJIS[i])

    active_parlays[message.id] = {
        "name": name,
        "teams": teams,
        "message": message,
        "end_time": datetime.utcnow() + timedelta(hours=1),
        "locked": False
    }

    asyncio.create_task(auto_lock(message.id))

# ---------------- REACTION UPDATE ----------------

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    message_id = reaction.message.id

    if message_id in active_parlays:
        if active_parlays[message_id]["locked"]:
            await reaction.remove(user)
            return

        await update_embed(message_id)

@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot:
        return

    message_id = reaction.message.id

    if message_id in active_parlays:
        await update_embed(message_id)

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

    await ctx.message.delete()

    if not ctx.message.reference:
        return

    message_id = ctx.message.reference.message_id

    if message_id not in active_parlays:
        return

    await finalize_parlay(message_id)

# ---------------- FINALIZE ----------------

async def finalize_parlay(message_id):

    parlay = active_parlays.get(message_id)
    if not parlay:
        return

    message = await parlay["message"].channel.fetch_message(message_id)
    embed = message.embeds[0]

    embed.color = discord.Color.red()
    embed.set_footer(text="🔒 Locked")

    await message.edit(embed=embed)

    active_parlays.pop(message_id, None)

# ---------------- LEADERBOARD ----------------

@bot.command(name="leaderboard")
async def leaderboard_cmd(ctx):

    await ctx.message.delete()

    await ctx.send("Leaderboard system coming next 👀")

# ---------------- RUN ----------------

bot.run(os.getenv("DISCORD_TOKEN"))
