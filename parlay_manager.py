import discord
import time
import asyncio
from database import get_connection
from utils import build_bar, calculate_percentages, format_time_remaining

EMOJIS = ["🇦", "🇧", "🇨", "🇩", "🇪"]

class ParlayManager:

    def __init__(self, bot):
        self.bot = bot
        self.active_timers = {}

    # -----------------------------
    # CREATE PARLAY
    # -----------------------------
    async def create_parlay(self, ctx, name, pairs):
        now = int(time.time())
        lock_time = now + 3600  # 1 hour auto lock

        conn = get_connection()
        cursor = conn.cursor()

        embed = await self.build_embed(
            guild_id=ctx.guild.id,
            name=name,
            pairs=pairs,
            message_id=None,
            lock_time=lock_time,
            closed=False,
            finalized=False
        )

        message = await ctx.send(embed=embed)

        cursor.execute("""
            INSERT INTO parlays
            (message_id, guild_id, name, created_at, lock_time, closed, finalized)
            VALUES (?, ?, ?, ?, ?, 0, 0)
        """, (message.id, ctx.guild.id, name, now, lock_time))

        conn.commit()
        conn.close()

        for i in range(len(pairs)):
            await message.add_reaction(EMOJIS[i])

        await ctx.message.delete()

        await self.start_timer(message.id)

    # -----------------------------
    # TIMER SYSTEM
    # -----------------------------
    async def start_timer(self, message_id):
        if message_id in self.active_timers:
            return

        task = self.bot.loop.create_task(self.timer_loop(message_id))
        self.active_timers[message_id] = task

    async def timer_loop(self, message_id):
        while True:
            await asyncio.sleep(5)

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT guild_id, name, lock_time, closed, finalized
                FROM parlays
                WHERE message_id=?
            """, (message_id,))
            row = cursor.fetchone()

            if not row:
                conn.close()
                return

            guild_id, name, lock_time, closed, finalized = row

            if closed or finalized:
                conn.close()
                return

            now = int(time.time())
            remaining = lock_time - now

            if remaining <= 0:
                cursor.execute("""
                    UPDATE parlays SET closed=1 WHERE message_id=?
                """, (message_id,))
                conn.commit()
                conn.close()

                await self.update_embed(message_id)
                return

            conn.close()
            await self.update_embed(message_id)

    # -----------------------------
    # UPDATE EMBED
    # -----------------------------
    async def update_embed(self, message_id):
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT guild_id, name, lock_time, closed, finalized
            FROM parlays
            WHERE message_id=?
        """, (message_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return

        guild_id, name, lock_time, closed, finalized = row

        cursor.execute("""
            SELECT emoji, COUNT(*) FROM picks
            WHERE message_id=?
            GROUP BY emoji
        """, (message_id,))
        votes = dict(cursor.fetchall())

        conn.close()

        percentages, total_votes = calculate_percentages(votes)

        guild = self.bot.get_guild(guild_id)
        channel = None

        for ch in guild.text_channels:
            try:
                msg = await ch.fetch_message(message_id)
                channel = ch
                break
            except:
                continue

        if not channel:
            return

        message = await channel.fetch_message(message_id)

        now = int(time.time())
        remaining = lock_time - now

        if finalized:
            color = discord.Color.purple()
            status_text = "🏆 FINAL RESULT"
        elif closed:
            color = discord.Color.gold()
            status_text = "🔒 LOCKED"
        else:
            color = discord.Color.green()
            status_text = f"🟢 OPEN — Locks in {format_time_remaining(max(remaining,0))}"

        embed = discord.Embed(
            title=f"🏀 {name}",
            description=status_text,
            color=color
        )

        for emoji in EMOJIS:
            count = votes.get(emoji, 0)
            percent = percentages.get(emoji, 0)
            bar = build_bar(percent)
            if count > 0:
                embed.add_field(
                    name=f"{emoji}",
                    value=f"{bar} {percent}% ({count})",
                    inline=False
                )

        embed.set_footer(text=f"Total Votes: {total_votes}")

        await message.edit(embed=embed)

    # -----------------------------
    # REACTION HANDLING
    # -----------------------------
    async def handle_reaction(self, reaction, user):
        if user.bot:
            return

        message_id = reaction.message.id
        emoji = str(reaction.emoji)

        if emoji not in EMOJIS:
            return

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT closed FROM parlays WHERE message_id=?
        """, (message_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return

        closed = row[0]

        if closed:
            await reaction.message.remove_reaction(emoji, user)
            conn.close()
            return

        cursor.execute("""
            INSERT OR REPLACE INTO picks (message_id, user_id, emoji)
            VALUES (?, ?, ?)
        """, (message_id, user.id, emoji))

        conn.commit()
        conn.close()

        await self.update_embed(message_id)
