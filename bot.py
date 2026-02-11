import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------
# DATA STORAGE
# -----------------------------
parlays = {}
user_stats = {}
EMOJIS = ["🇦", "🇧", "🇨", "🇩", "🇪"]
current_cycle = 1

# -----------------------------
# READY
# -----------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# -----------------------------
# CREATE PARLAY
# -----------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def parlay(ctx, *args):
    if len(args) < 4 or len(args) % 2 != 0:
        await ctx.send("❌ Usage: !parlay TeamA oddsA TeamB oddsB [TeamC oddsC ...]")
        return

    pairs = [(args[i], args[i+1]) for i in range(0, len(args), 2)]

    if len(pairs) > len(EMOJIS):
        await ctx.send("❌ Max 5 teams supported.")
        return

    text = f"🏀 **PARLAY (Cycle {current_cycle})**\n"
    for i, (team, odds) in enumerate(pairs):
        text += f"{EMOJIS[i]} {team} (+{odds})\n"

    text += "\nReact below ⬇️"

    message = await ctx.send(text)

    parlays[message.id] = {
        "picks": {},
        "closed": False
    }

    for i in range(len(pairs)):
        await message.add_reaction(EMOJIS[i])

# -----------------------------
# HANDLE REACTIONS
# -----------------------------
@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    emoji = str(reaction.emoji)
    message_id = reaction.message.id

    if emoji not in EMOJIS:
        return

    if message_id not in parlays:
        return

    parlay = parlays[message_id]

    if parlay["closed"]:
        await reaction.message.remove_reaction(emoji, user)
        return

    for e in EMOJIS:
        if e != emoji:
            await reaction.message.remove_reaction(e, user)

    parlay["picks"][user.id] = emoji


@bot.event
async def on_reaction_remove(reaction, user):
    message_id = reaction.message.id
    emoji = str(reaction.emoji)

    if message_id in parlays:
        if parlays[message_id]["picks"].get(user.id) == emoji:
            del parlays[message_id]["picks"][user.id]

# -----------------------------
# CLOSE PARLAY
# -----------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def close(ctx):
    if not ctx.message.reference:
        await ctx.send("❌ Reply to the parlay message to close it.")
        return

    message_id = ctx.message.reference.message_id

    if message_id not in parlays:
        await ctx.send("❌ No active parlay found.")
        return

    parlays[message_id]["closed"] = True

    try:
        message = await ctx.channel.fetch_message(message_id)
        await message.add_reaction("🔒")
    except:
        pass

    await ctx.send("🔒 Parlay closed. Existing reactions kept.")

# -----------------------------
# SET WINNER
# -----------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def setwinner(ctx, winning_emoji: str, odds: int):
    if not ctx.message.reference:
        await ctx.send("❌ Reply to the parlay message.")
        return

    if winning_emoji not in EMOJIS:
        await ctx.send("❌ Invalid emoji.")
        return

    message_id = ctx.message.reference.message_id

    if message_id not in parlays:
        await ctx.send("❌ No active parlay found.")
        return

    points = odds // 100
    winners = []

    for user_id, pick in parlays[message_id]["picks"].items():
        if user_id not in user_stats:
            user_stats[user_id] = {"correct": 0, "points": 0}

        if pick == winning_emoji:
            user_stats[user_id]["correct"] += 1
            user_stats[user_id]["points"] += points
            winners.append(f"<@{user_id}>")

    try:
        replied_message = await ctx.channel.fetch_message(message_id)
        await replied_message.add_reaction("🔒")
    except:
        pass

    del parlays[message_id]

    await ctx.send(
        f"🔒 **Parlay Closed**\n"
        f"✅ **Winner:** {winning_emoji} (+{odds})\n"
        f"🏆 Correct Picks: {', '.join(winners) if winners else 'None'}"
    )

# -----------------------------
# LEADERBOARD
# -----------------------------
@bot.command()
async def leaderboard(ctx):
    if not user_stats:
        await ctx.send("No results yet.")
        return

    sorted_users = sorted(
        user_stats.items(),
        key=lambda x: (x[1]["correct"], x[1]["points"]),
        reverse=True
    )

    msg = f"📊 **Parlay Leaderboard (Cycle {current_cycle})**\n"
    for user_id, stats in sorted_users:
        msg += f"<@{user_id}> — {stats['correct']} correct | ⭐ {stats['points']} pts\n"

    await ctx.send(msg)

# -----------------------------
# NEW CYCLE
# -----------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def newcycle(ctx):
    global user_stats, current_cycle
    user_stats = {}
    current_cycle += 1
    await ctx.send(f"🔄 **New Parlay Cycle Started! (Cycle {current_cycle})**")

# -----------------------------
# ACTIVE PARLAYS
# -----------------------------
@bot.command()
async def activeparlays(ctx):
    if not parlays:
        await ctx.send("📭 No active parlays right now.")
        return

    msg = "📌 **Active Parlays**\n"
    for message_id, data in parlays.items():
        status = "🔒 Closed" if data["closed"] else "🟢 Open"
        msg += f"• `{message_id}` — {len(data['picks'])} picks — {status}\n"

    await ctx.send(msg)

bot.run(os.getenv("DISCORD_TOKEN"))
