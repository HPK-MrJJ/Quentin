import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import re
import spacy
from collections import Counter, defaultdict

# Load spaCy model once
nlp = spacy.load("en_core_web_sm")


class ServerWrapped(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Utility ----------------------

    def clean_text(self, text: str) -> str:
        # Strip channel IDs, mentions, URLs, emojis, etc.
        text = re.sub(r"<a?:\w+:\d+>", "", text)  # emoji markup
        text = re.sub(r"<[#@]\d+>", "", text)  # channel/user mentions
        text = re.sub(r"https?://\S+", "", text)
        text = text.replace("\n", " ")
        return text.strip()

    def extract_topics(self, messages):
        """
        Use spaCy to extract "real" topics:
        - noun chunks + named entities
        - but filter out common junk ("man", "thing", "based", "idk", etc.)
        - filter out any tokens that are only digits (old channel IDs)
        - consolidate similar terms (case-insensitive)
        """
        topic_counter = Counter()
        junk = {"man", "thing", "things", "dont know", "idk", "based", "ok", "yes"}

        for m in messages:
            text = self.clean_text(m.content)
            if not text:
                continue

            doc = nlp(text)

            # Extract noun chunks
            for chunk in doc.noun_chunks:
                topic = chunk.text.lower()
                topic = re.sub(r"[^a-zA-Z0-9\s]", "", topic).strip()

                if not topic or topic in junk:
                    continue
                if topic.isdigit():
                    continue

                topic_counter[topic] += 1

            # Extract named entities
            for ent in doc.ents:
                topic = ent.text.lower().strip()
                topic = re.sub(r"[^a-zA-Z0-9\s]", "", topic)

                if not topic or topic in junk:
                    continue
                if topic.isdigit():
                    continue

                topic_counter[topic] += 1

        return topic_counter.most_common(10)

    def pick_interesting_message(self, messages):
        """
        Highlight scoring system:
        + Longer messages
        + Contains nouns / entities (spaCy)
        + Contains media embeds
        + Contains punctuation variety
        """
        best_msg = None
        best_score = -1

        for m in messages:
            text = m.content
            score = 0

            if len(text) > 40:
                score += len(text) / 50  # length

            doc = nlp(text)
            score += len([t for t in doc if t.pos_ in {"NOUN", "PROPN"}]) * 0.4

            if m.attachments:
                score += 3

            if any(p in text for p in ["?", "!", ":"]):
                score += 1

            if score > best_score:
                best_score = score
                best_msg = m

        return best_msg

    # Command ----------------------

    @commands.command(name="serverwrapped")
    async def serverwrapped(self, ctx):
        await ctx.typing()

        guild = ctx.guild

        # Define earliest timezone → Jan 1, 2025 @ 00:00 UTC–12
        earliest_tz = timezone(timedelta(hours=-12))
        year_start = datetime(2025, 1, 1, 0, 0, tzinfo=earliest_tz)

        # Collect all messages newer than year_start
        messages = []
        for channel in guild.text_channels:
            try:
                async for msg in channel.history(limit=None, after=year_start):
                    messages.append(msg)
            except:
                continue

        if not messages:
            await ctx.send("I couldn't find any messages from this year.")
            return

        # 1. HOW THE YEAR STARTED -------------------------
        early_msgs = [m for m in messages if (m.created_at - year_start).days < 7]
        if early_msgs:
            topics = self.extract_topics(early_msgs)
            if topics:
                first_topic = topics[0][0]
                year_intro = f"You kicked off the year chatting about **{first_topic}**, setting the tone early."
            else:
                year_intro = "The year began quietly, with some light banter in the first week."
        else:
            year_intro = "The year began with no recorded activity in the first week."

        # 2. COMMON TOPICS -------------------------------
        topics = self.extract_topics(messages)
        topic_str = "\n".join(f"- **{t}**" for t, _ in topics) if topics else "No clear topics emerged."

        # 3. SIDEKICKS (users you talk with the most) ----
        partner_counter = Counter()
        for m in messages:
            if m.author != ctx.author:
                partner_counter[m.author] += 1

        sidekicks = partner_counter.most_common(5)
        sidekick_str = "\n".join(f"- **{u.display_name}**" for u, _ in sidekicks) if sidekicks else "None."

        # 4. MOST USED EMOJIS ----------------------------
        emoji_pattern = re.compile(r"[\U0001F300-\U0001FAFF]")
        emoji_counter = Counter()

        for m in messages:
            for e in emoji_pattern.findall(m.content):
                emoji_counter[e] += 1

        emoji_str = (
            ", ".join(f"{e}" for e, _ in emoji_counter.most_common(10))
            if emoji_counter
            else "No emojis found."
        )

        # 5. SUMMARY (simple) ---------------------------
        total_msgs = len(messages)
        total_users = len({m.author.id for m in messages})
        summary = f"This year saw **{total_msgs}** messages from **{total_users}** participants."

        # 6. HIGHLIGHT -----------------------------------
        highlight = self.pick_interesting_message(messages)
        if highlight:
            jump = highlight.jump_url
            highlight_text = highlight.content[:400] or "[Attachment]"
            highlight_field = f"{highlight.author.display_name}: {highlight_text}\n[[Jump to message]]({jump})"
        else:
            highlight_field = "No highlight available."

        # BUILD EMBED -----------------------------------
        embed = discord.Embed(
            title=f"{guild.name} — Wrapped 2025",
            color=discord.Color.blurple(),
        )

        embed.add_field(name="How the Year Began", value=year_intro, inline=False)
        embed.add_field(name="Most Common Topics", value=topic_str, inline=False)
        embed.add_field(name="Sidekicks", value=sidekick_str, inline=False)
        embed.add_field(name="Most Used Emojis", value=emoji_str, inline=False)
        embed.add_field(name="Summary", value=summary, inline=False)
        embed.add_field(name="Highlight of the Year", value=highlight_field, inline=False)

        # SEND -------------------------------------------
        await ctx.send(embed=embed)
