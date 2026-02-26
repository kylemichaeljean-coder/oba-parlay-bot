import discord
from discord.ext import commands
import os
import asyncio
from datetime import datetime, timedelta
import json

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
active_parlays = {}

LEADERBOARD_FILE = "leaderboard.json"

# ---------------- FILE STORAGE ----------------

def load_data():
    try:
        with open(LEADERBOARD_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(LEADERBOARD_FILE, "w") as f:
        json.dump(data, f, indent=4)

leaderboard_data = load_data()

# ---------------- READY ----------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# ---------------- UTIL ----------------

def build_bar(percent):
    filled = int(percent / 10)
    return "▰" * filled + "▱" * (10 - filled)

def get_color(end_time):
    remaining = (end_time - datetime.utcnow()).total_seconds()

    if remaining <= 0:
        return discord.Color.red()

    ratio = remaining / 3600

    if ratio > 0.66:
        return discord.Color.green()
    elif ratio > 0.33:
        return discord.Color.gold()
    else:
        return discord.Color.red()

def odds_to_points(odds):
    odds = int(odds)
    return max(1, round(abs(odds) / 100))

    # Positive odds (+300 etc)
    if odds > 0:
        return round(odds / 100)

    # Negative odds (-150 etc)
    else:
        # Higher risk = more reward
        return round(abs(odds) / 200)

# ---------------- UPDATE EMBED ----------------

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

    desc = "React below to vote!\n\n"

    for i, (team, odds) in enumerate(parlay["teams"]):
        votes = counts[i] if i < len(counts) else 0
        percent = (votes / total_votes * 100) if total_votes > 0 else 0
        bar = build_bar(percent)
        desc += f"{EMOJIS[i]} **{team}** (+{odds})\n{bar} {int(percent)}%\n\n"

    embed.description = desc
    embed.color = get_color(parlay["end_time"])

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
        "teams": teams,
        "message": message,
        "end_time": datetime.utcnow() + timedelta(hours=1),
        "locked": False,
        "guild_id": str(ctx.guild.id)
    }

    asyncio.create_task(auto_lock(message.id))

# ---------------- ONE PICK ----------------

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    message_id = reaction.message.id

    if message_id not in active_parlays:
        return

    parlay = active_parlays[message_id]

    if parlay["locked"]:
        await reaction.remove(user)
        return

    for react in reaction.message.reactions:
        if react.emoji in EMOJIS and react.emoji != reaction.emoji:
            users = [u async for u in react.users()]
            if user in users:
                await react.remove(user)

    await update_embed(message_id)

@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot:
        return

    if reaction.message.id in active_parlays:
        await update_embed(reaction.message.id)

# ---------------- AUTO LOCK ----------------

async def auto_lock(message_id):
    await asyncio.sleep(3600)

    if message_id in active_parlays:
        await finalize_parlay(message_id)

# ---------------- FINALIZE ----------------

async def finalize_parlay(message_id):

    parlay = active_parlays.get(message_id)
    if not parlay:
        return

    message = await parlay["message"].channel.fetch_message(message_id)
    embed = message.embeds[0]

    parlay["locked"] = True

    guild_id = parlay["guild_id"]
    leaderboard_data.setdefault(guild_id, {})

    results = {}

    for reaction in message.reactions:
        if reaction.emoji in EMOJIS:
            users = [u async for u in reaction.users() if not u.bot]
            results[reaction.emoji] = users

    winner_emoji = max(results, key=lambda x: len(results[x]), default=None)

    if winner_emoji:
        index = EMOJIS.index(winner_emoji)
        team, odds = parlay["teams"][index]
        points = odds_to_points(odds)

        for user in results[winner_emoji]:
            user_id = str(user.id)
            leaderboard_data[guild_id].setdefault(user_id, {"correct": 0, "points": 0})
            leaderboard_data[guild_id][user_id]["correct"] += 1
            leaderboard_data[guild_id][user_id]["points"] += points

        save_data(leaderboard_data)

        embed.add_field(name="🏆 Winner", value=team, inline=False)
        embed.add_field(name="⭐ Points Awarded", value=f"{points} pts", inline=False)

        if results[winner_emoji]:
            embed.add_field(name="👑 MVP", value=results[winner_emoji][0].mention, inline=False)

    embed.color = discord.Color.red()
    embed.set_footer(text="🔒 Locked")

    await message.edit(embed=embed)

    active_parlays.pop(message_id, None)

# ---------------- LEADERBOARD ----------------

@bot.command(name="leaderboard")
async def leaderboard(ctx):

    await ctx.message.delete()

    guild_id = str(ctx.guild.id)

    if guild_id not in leaderboard_data or not leaderboard_data[guild_id]:
        await ctx.send("No stats yet.")
        return

    sorted_users = sorted(
        leaderboard_data[guild_id].items(),
        key=lambda x: x[1]["points"],
        reverse=True
    )

    desc = ""
    for user_id, stats in sorted_users:
        desc += f"<@{user_id}> — {stats['correct']} correct | {stats['points']} pts\n"

    embed = discord.Embed(
        title="🏆 Leaderboard",
        description=desc,
        color=discord.Color.gold()
    )

    await ctx.send(embed=embed)

# ---------------- NEW CYCLE ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def newcycle(ctx):

    await ctx.message.delete()

    guild_id = str(ctx.guild.id)
    leaderboard_data[guild_id] = {}
    save_data(leaderboard_data)

    await ctx.send("🔄 New cycle started! Leaderboard reset.")
# ---------------- CLOSE EARLY ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def close(ctx):

    await ctx.message.delete()

    if not ctx.message.reference:
        await ctx.send("Reply to the parlay message to close it.")
        return

    message_id = ctx.message.reference.message_id

    if message_id not in active_parlays:
        await ctx.send("That message is not an active parlay.")
        return

    await finalize_parlay(message_id)
    # ---------------- SET WINNER (MANUAL) ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def setwinner(ctx, emoji: str):

    await ctx.message.delete()

    if not ctx.message.reference:
        await ctx.send("Reply to the parlay message to set winner.")
        return

    message_id = ctx.message.reference.message_id

    if message_id not in active_parlays:
        await ctx.send("That message is not an active parlay.")
        return

    if emoji not in EMOJIS:
        await ctx.send("Invalid emoji. Use one of the reaction emojis.")
        return

    parlay = active_parlays.get(message_id)
    message = await parlay["message"].channel.fetch_message(message_id)
    embed = message.embeds[0]

    guild_id = parlay["guild_id"]
    leaderboard_data.setdefault(guild_id, {})

    index = EMOJIS.index(emoji)
    team, odds = parlay["teams"][index]
    points = odds_to_points(odds)

    # Get users who reacted to that emoji
    winner_users = []
    for reaction in message.reactions:
        if reaction.emoji == emoji:
            winner_users = [u async for u in reaction.users() if not u.bot]

    for user in winner_users:
        user_id = str(user.id)
        leaderboard_data[guild_id].setdefault(user_id, {"correct": 0, "points": 0})
        leaderboard_data[guild_id][user_id]["correct"] += 1
        leaderboard_data[guild_id][user_id]["points"] += points

    save_data(leaderboard_data)

    embed.add_field(name="🏆 Winner (Manual)", value=team, inline=False)
    embed.add_field(name="⭐ Points Awarded", value=f"{points} pts", inline=False)

    if winner_users:
        embed.add_field(name="👑 MVP", value=winner_users[0].mention, inline=False)

    embed.color = discord.Color.red()
    embed.set_footer(text="🔒 Locked (Manual Override)")

    await message.edit(embed=embed)

    active_parlays.pop(message_id, None)
# ---------------- ERROR HANDLER ----------------

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need Administrator permission for this command.")

# ---------------- RUN ----------------

bot.run(os.getenv("DISCORD_TOKEN"))
