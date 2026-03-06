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

LEADERBOARD_FILE = "leaderboard.json"

active_parlays = {}

# ---------------- STORAGE ----------------

def load_data():
    try:
        with open(LEADERBOARD_FILE,"r") as f:
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

def odds_to_points(odds):

    odds=int(odds)

    if odds>0:
        return max(1,round(odds/100))
    else:
        return max(1,round(abs(odds)/200))


def build_bar(percent):

    filled=int(percent/10)
    return "▰"*filled+"▱"*(10-filled)

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

        pts=odds_to_points(odds)

        embed.description+=f"{EMOJIS[i]} **{team}** (+{odds}) • {pts} pts\n"

    embed.set_footer(text="⏳ Auto locks in 1 hour")

    message=await ctx.send(embed=embed)

    for i in range(len(teams)):
        await message.add_reaction(EMOJIS[i])

    active_parlays[message.id]={
        "teams":teams,
        "message":message,
        "end":datetime.utcnow()+timedelta(hours=1),
        "locked":False
    }

    asyncio.create_task(auto_lock(message.id))

# ---------------- ONE PICK ----------------

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

    for react in reaction.message.reactions:

        if react.emoji in EMOJIS and react.emoji!=reaction.emoji:

            users=[u async for u in react.users() if not u.bot]

            if user in users:
                await react.remove(user)

# ---------------- AUTO LOCK ----------------

async def auto_lock(message_id):

    await asyncio.sleep(3600)

    if message_id in active_parlays:
        await lock_parlay(message_id)

async def lock_parlay(message_id):

    parlay=active_parlays.get(message_id)

    if not parlay:
        return

    message=await parlay["message"].channel.fetch_message(message_id)

    embed=message.embeds[0]

    embed.color=discord.Color.red()
    embed.set_footer(text="🔒 Locked — Awaiting Result")

    parlay["locked"]=True

    await message.edit(embed=embed)

# ---------------- CLOSE ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def close(ctx):

    await ctx.message.delete()

    if not ctx.message.reference:
        return

    message_id=ctx.message.reference.message_id

    await lock_parlay(message_id)

# ---------------- SET WINNER ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def setwinner(ctx,emoji:str):

    await ctx.message.delete()

    if not ctx.message.reference:
        await ctx.send("Reply to a parlay message.")
        return

    message_id=ctx.message.reference.message_id

    message=await ctx.channel.fetch_message(message_id)

    if not message.embeds:
        return

    embed=message.embeds[0]

    lines=embed.description.split("\n")

    teams=[]

    for line in lines:

        for e in EMOJIS:

            if line.startswith(e):

                try:
                    team=line.split("**")[1]
                    odds=line.split("+")[1].split(")")[0]

                    teams.append((team,odds))
                except:
                    pass

    if emoji not in EMOJIS:
        return

    index=EMOJIS.index(emoji)

    if index>=len(teams):
        return

    team,odds=teams[index]

    points=odds_to_points(odds)

    guild=str(ctx.guild.id)

    leaderboard_data.setdefault(guild,{})

    winners=[]

    for reaction in message.reactions:

        if reaction.emoji==emoji:

            winners=[u async for u in reaction.users() if not u.bot]

    for user in winners:

        uid=str(user.id)

        leaderboard_data[guild].setdefault(uid,{
            "correct":0,
            "points":0
        })

        leaderboard_data[guild][uid]["correct"]+=1
        leaderboard_data[guild][uid]["points"]+=points

    save_data(leaderboard_data)

    embed.add_field(name="🏆 Winner",value=team,inline=False)
    embed.add_field(name="⭐ Points Awarded",value=f"{points} pts",inline=False)

    if winners:
        embed.add_field(name="👑 MVP",value=winners[0].mention,inline=False)

    embed.set_footer(text="Result Recorded")

    await message.edit(embed=embed)

# ---------------- LEADERBOARD ----------------

@bot.command(name="leaderboard")
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

# ---------------- NEW CYCLE ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def newcycle(ctx):

    await ctx.message.delete()

    guild=str(ctx.guild.id)

    leaderboard_data[guild]={}

    save_data(leaderboard_data)

    await ctx.send("🔄 New cycle started")

# ---------------- ERROR ----------------

@bot.event
async def on_command_error(ctx,error):

    if isinstance(error,commands.MissingPermissions):
        await ctx.send("Administrator permission required.")

# ---------------- RUN ----------------

bot.run(os.getenv("DISCORD_TOKEN"))
