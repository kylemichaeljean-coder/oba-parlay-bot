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

EMOJIS = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]
active_parlays = {}

LEADERBOARD_FILE = "leaderboard.json"

# ---------------- STORAGE ----------------

def load_data():
    if not os.path.exists(LEADERBOARD_FILE):
        with open(LEADERBOARD_FILE,"w") as f:
            json.dump({},f)

    with open(LEADERBOARD_FILE,"r") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_data(data):
    with open(LEADERBOARD_FILE,"w") as f:
        json.dump(data,f,indent=4)

leaderboard_data = load_data()

# ---------------- READY ----------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# ---------------- UTIL ----------------

def build_bar(percent):
    filled = int(percent/10)
    return "▰"*filled + "▱"*(10-filled)

def odds_to_points(odds):
    odds=int(odds)
    return max(1,round(abs(odds)/100))

# ---------------- UPDATE EMBED ----------------

async def update_embed(message_id):

    if message_id not in active_parlays:
        return

    parlay=active_parlays[message_id]

    message = await parlay["message"].channel.fetch_message(message_id)
    embed = message.embeds[0]

    total_votes=0
    counts=[]

    for reaction in message.reactions:
        if reaction.emoji in EMOJIS:
            count=reaction.count-1
            counts.append(count)
            total_votes+=count

    desc="React below to vote!\n\n"

    for i,(team,odds) in enumerate(parlay["teams"]):

        votes = counts[i] if i<len(counts) else 0
        percent = (votes/total_votes*100) if total_votes>0 else 0
        bar=build_bar(percent)

        desc += f"{EMOJIS[i]} **{team} (+{odds})**\n{bar} {int(percent)}%\n\n"

    embed.description=desc

    await message.edit(embed=embed)

# ---------------- PARLAY ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def parlay(ctx,name:str,*args):

    await ctx.message.delete()

    if len(args)<2 or len(args)%2!=0:
        return

    teams=[(args[i],args[i+1]) for i in range(0,len(args),2)]

    embed=discord.Embed(
        title=f"🔥 {name}",
        description="React below to vote!\n\n",
        color=discord.Color.green()
    )

    for i,(team,odds) in enumerate(teams):
        embed.description+=f"{EMOJIS[i]} **{team} (+{odds})**\n"

    embed.set_footer(text="⏳ Locks in 1 hour")

    message=await ctx.send(embed=embed)

    for i in range(len(teams)):
        await message.add_reaction(EMOJIS[i])

    active_parlays[message.id]={
        "teams":teams,
        "message":message,
        "end_time":datetime.utcnow()+timedelta(hours=1),
        "locked":False,
        "guild":str(ctx.guild.id)
    }

# ---------------- REACTIONS ----------------

@bot.event
async def on_reaction_add(reaction,user):

    if user.bot:
        return

    message_id=reaction.message.id

    if message_id not in active_parlays:
        return

    parlay=active_parlays[message_id]

    if parlay["locked"]:
        await reaction.remove(user)
        return

    # enforce one pick
    for react in reaction.message.reactions:
        if react.emoji in EMOJIS and react.emoji!=reaction.emoji:

            users=[u async for u in react.users()]

            if user in users:
                await react.remove(user)

    await update_embed(message_id)

@bot.event
async def on_reaction_remove(reaction,user):

    if user.bot:
        return

    if reaction.message.id in active_parlays:
        await update_embed(reaction.message.id)

# ---------------- CLOSE ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def close(ctx):

    await ctx.message.delete()

    if not ctx.message.reference:
        return

    message_id=ctx.message.reference.message_id

    if message_id not in active_parlays:
        return

    parlay=active_parlays[message_id]

    parlay["locked"]=True

    message=await parlay["message"].channel.fetch_message(message_id)
    embed=message.embeds[0]

    embed.color=discord.Color.red()
    embed.set_footer(text="🔒 Voting Closed")

    await message.edit(embed=embed)

# ---------------- SET WINNER ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def setwinner(ctx,emoji:str):

    await ctx.message.delete()

    if not ctx.message.reference:
        return

    message_id=ctx.message.reference.message_id

    message = await ctx.channel.fetch_message(message_id)

    embed=message.embeds[0]

    if emoji not in EMOJIS:
        return

    index=EMOJIS.index(emoji)

    lines=embed.description.split("\n")

    team_line=lines[index*3]
    team=team_line.split("**")[1].split("(")[0].strip()
    odds=int(team_line.split("+")[1].split(")")[0])

    points=odds_to_points(odds)

    winner_users=[]

    for reaction in message.reactions:
        if reaction.emoji==emoji:
            winner_users=[u async for u in reaction.users() if not u.bot]

    guild=str(ctx.guild.id)
    leaderboard_data.setdefault(guild,{})

    for user in winner_users:

        uid=str(user.id)

        leaderboard_data[guild].setdefault(uid,{
            "correct":0,
            "points":0
        })

        leaderboard_data[guild][uid]["correct"]+=1
        leaderboard_data[guild][uid]["points"]+=points

    save_data(leaderboard_data)

    # override old results
    embed.clear_fields()

    embed.add_field(name="🏆 Winner",value=team,inline=False)
    embed.add_field(name="⭐ Points",value=f"{points}",inline=False)

    if winner_users:
        embed.add_field(name="👑 MVP",value=winner_users[0].mention,inline=False)

    embed.color=discord.Color.red()

    await message.edit(embed=embed)

# ---------------- LEADERBOARD ----------------

@bot.command()
async def leaderboard(ctx):

    await ctx.message.delete()

    guild=str(ctx.guild.id)

    if guild not in leaderboard_data or not leaderboard_data[guild]:

        await ctx.send("No stats yet.")
        return

    sorted_users=sorted(
        leaderboard_data[guild].items(),
        key=lambda x:x[1]["points"],
        reverse=True
    )

    desc=""

    for uid,stats in sorted_users:

        desc+=f"<@{uid}> — {stats['correct']} correct | {stats['points']} pts\n"

    embed=discord.Embed(
        title="🏆 Leaderboard",
        description=desc,
        color=discord.Color.gold()
    )

    await ctx.send(embed=embed)

# ---------------- RUN ----------------

bot.run(os.getenv("DISCORD_TOKEN"))
