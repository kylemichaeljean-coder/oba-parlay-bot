import discord
from discord.ext import commands
import os
import json
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
active_parlays = {}

LEADERBOARD_FILE = "leaderboard.json"


# ---------------- STORAGE ----------------

def load_data():
    if not os.path.exists(LEADERBOARD_FILE):
        with open(LEADERBOARD_FILE, "w") as f:
            json.dump({}, f)

    with open(LEADERBOARD_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(LEADERBOARD_FILE, "w") as f:
        json.dump(data, f, indent=4)


leaderboard = load_data()


# ---------------- READY ----------------

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")


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
        embed.description += f"{EMOJIS[i]} **{team} (+{odds})**\n"

    embed.set_footer(text="⏳ Voting closes in 2 hours")

    message = await ctx.send(embed=embed)

    for i in range(len(teams)):
        await message.add_reaction(EMOJIS[i])

    active_parlays[message.id] = {
        "teams": teams,
        "locked": False,
        "end": datetime.utcnow() + timedelta(hours=2)
    }


# ---------------- ONE PICK ----------------

@bot.event
async def on_reaction_add(reaction, user):

    if user.bot:
        return

    if reaction.message.id not in active_parlays:
        return

    parlay = active_parlays[reaction.message.id]

    if parlay["locked"]:
        await reaction.remove(user)
        return

    for react in reaction.message.reactions:
        if react.emoji in EMOJIS and react.emoji != reaction.emoji:

            users = [u async for u in react.users()]

            if user in users:
                await react.remove(user)


# ---------------- CLOSE ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def close(ctx):

    await ctx.message.delete()

    if not ctx.message.reference:
        return

    message_id = ctx.message.reference.message_id

    if message_id not in active_parlays:
        return

    active_parlays[message_id]["locked"] = True

    message = await ctx.channel.fetch_message(message_id)
    embed = message.embeds[0]

    embed.color = discord.Color.red()
    embed.set_footer(text="🔒 Voting Closed")

    await message.edit(embed=embed)


# ---------------- SET WINNER ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def setwinner(ctx, emoji: str):

    await ctx.message.delete()

    if not ctx.message.reference:
        return

    message_id = ctx.message.reference.message_id
    message = await ctx.channel.fetch_message(message_id)

    if emoji not in EMOJIS:
        return

    embed = message.embeds[0]
    index = EMOJIS.index(emoji)

    lines = embed.description.split("\n")
    team_line = lines[index + 1]

    team = team_line.split("**")[1].split("(")[0].strip()
    odds = int(team_line.split("+")[1].split(")")[0])

    points = max(1, abs(odds)//100)

    users = []

    for reaction in message.reactions:
        if reaction.emoji == emoji:
            users = [u async for u in reaction.users() if not u.bot]

    guild = str(ctx.guild.id)
    leaderboard.setdefault(guild, {})

    for u in users:

        uid = str(u.id)

        leaderboard[guild].setdefault(uid, {
            "correct": 0,
            "points": 0
        })

        leaderboard[guild][uid]["correct"] += 1
        leaderboard[guild][uid]["points"] += points

    save_data(leaderboard)

    embed.clear_fields()

    embed.add_field(name="🏆 Winner", value=team, inline=False)
    embed.add_field(name="⭐ Points", value=str(points), inline=False)

    if users:
        embed.add_field(name="👑 MVP", value=users[0].mention, inline=False)

    embed.color = discord.Color.red()

    await message.edit(embed=embed)


# ---------------- LEADERBOARD ----------------

@bot.command()
async def leaderboard(ctx):

    await ctx.message.delete()

    guild = str(ctx.guild.id)

    if guild not in leaderboard or not leaderboard[guild]:
        await ctx.send("No stats yet.")
        return

    sorted_users = sorted(
        leaderboard[guild].items(),
        key=lambda x: x[1]["points"],
        reverse=True
    )

    desc = ""

    for uid, stats in sorted_users:
        desc += f"<@{uid}> — {stats['correct']} correct | {stats['points']} pts\n"

    embed = discord.Embed(
        title="🏆 Leaderboard",
        description=desc,
        color=discord.Color.gold()
    )

    await ctx.send(embed=embed)


# ---------------- RUN ----------------

bot.run(os.getenv("DISCORD_TOKEN"))
