import discord
from discord.ext import commands
import os
import json
from datetime import datetime, timedelta
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

EMOJIS = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]

active_parlays = {}

LEADERBOARD_FILE = "leaderboard.json"

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
    print(f"Bot Online: {bot.user}")

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


def get_color(end):

    remaining=(end-datetime.utcnow()).total_seconds()

    if remaining<=0:
        return discord.Color.red()

    ratio=remaining/7200

    if ratio>0.66:
        return discord.Color.green()
    elif ratio>0.33:
        return discord.Color.gold()
    else:
        return discord.Color.red()

# ---------------- EMBED UPDATE ----------------

async def update_embed(message_id):

    if message_id not in active_parlays:
        return

    parlay=active_parlays[message_id]

    message=await parlay["message"].channel.fetch_message(message_id)

    embed=message.embeds[0]

    votes=[]
    total=0

    for reaction in message.reactions:

        if reaction.emoji in EMOJIS:

            count=reaction.count-1
            votes.append(count)
            total+=count

    desc="React below to vote!\n\n"

    for i,(team,odds) in enumerate(parlay["teams"]):

        vote_count=votes[i] if i<len(votes) else 0
        percent=(vote_count/total*100) if total>0 else 0

        bar=build_bar(percent)

        desc+=f"{EMOJIS[i]} **{team}** (+{odds})\n{bar} {int(percent)}%\n\n"

    embed.description=desc
    embed.color=get_color(parlay["end"])

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
        description="Loading votes...",
        color=discord.Color.green()
    )

    embed.set_footer(text="⏳ Voting open (2 hours)")

    message=await ctx.send(embed=embed)

    for i in range(len(teams)):
        await message.add_reaction(EMOJIS[i])

    active_parlays[message.id]={
        "teams":teams,
        "message":message,
        "locked":False,
        "guild":str(ctx.guild.id),
        "end":datetime.utcnow()+timedelta(hours=2)
    }

    await update_embed(message.id)

    asyncio.create_task(auto_lock(message.id))

# ---------------- AUTO LOCK ----------------

async def auto_lock(message_id):

    await asyncio.sleep(7200)

    if message_id not in active_parlays:
        return

    parlay=active_parlays[message_id]

    parlay["locked"]=True

    message=await parlay["message"].channel.fetch_message(message_id)

    embed=message.embeds[0]

    embed.set_footer(text="🔒 Voting Closed")

    await message.edit(embed=embed)

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

    for react in reaction.message.reactions:

        if react.emoji in EMOJIS and react.emoji!=reaction.emoji:

            users=[u async for u in react.users() if not u.bot]

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

    embed.set_footer(text="🔒 Voting Closed")

    await message.edit(embed=embed)

# ---------------- SET WINNER ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def setwinner(ctx,emoji:str):

    await ctx.message.delete()

    if not ctx.message.reference:
        return

    message=await ctx.channel.fetch_message(ctx.message.reference.message_id)

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

    index=EMOJIS.index(emoji)

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

    embed.color=discord.Color.red()
    embed.set_footer(text="Result Recorded")

    await message.edit(embed=embed)

# ---------------- RETRO SET ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def retroset(ctx,emoji:str):

    await ctx.message.delete()

    if not ctx.message.reference:
        return

    message=await ctx.channel.fetch_message(ctx.message.reference.message_id)

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
        leaderboard_data[guild][uid]["points"]+=1

    save_data(leaderboard_data)

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
