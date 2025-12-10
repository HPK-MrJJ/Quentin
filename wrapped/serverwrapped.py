# serverwrapped.py
from __future__ import annotations
import re
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import discord
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import pagify, box

# ------------------------------------------------------------
# Configuration defaults
# ------------------------------------------------------------
DEFAULTS = {
    "channels": []  # list of channel IDs to scan
}

# Lightweight stopword list (extend as needed)
STOPWORDS = {
    "the", "and", "to", "a", "in", "of", "is", "it", "for", "on", "that", "i", "you",
    "with", "this", "was", "are", "be", "have", "my", "we", "but", "not", "they",
    "at", "so", "if", "or", "as", "an", "by", "from", "me", "what", "just", "like",
    "do", "get", "got", "can", "will", "your", "all", "about", "no", "when", "there",
    "who", "one", "would", "which", "them", "myself", "been", "out", "up", "then",
    "how", "he", "she"
}

URL_RE = re.compile(
    r"https?://\S+|www\.\S+",
    re.IGNORECASE
)
MENTION_RE = re.compile(r"^(\s*<@!?\d+>\s*)+$")
ONLY_EMOJI_RE = re.compile(r"^(?:\s*[\U0001F300-\U0001FAFF\u2600-\u27BF]+)+\s*$")
CUSTOM_EMOJI_RE = re.compile(r"<a?:\w+:\d+>")
UNICODE_EMOJI_RE = re.compile(
    "[" 
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "]+", flags=re.UNICODE
)
# colon emoji like :grin: or :gigachad:
COLON_EMOJI_RE = re.compile(r"^:[a-zA-Z0-9_~]+:$")

# detect a message consisting ONLY of emojis (unicode, custom, or colon-style)
ONLY_ANY_EMOJI_RE = re.compile(
    r"^(?:\s*(?:"
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF]"      # unicode
    r"|<a?:\w+:\d+>"                               # custom discord emoji
    r"|:[a-zA-Z0-9_~]+:"                           # colon emoji
    r")\s*)+$"
)
WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)

# Message length thresholds
MIN_HIGHLIGHT_LEN = 10
MAX_HIGHLIGHT_LEN = 350

# Scoring weights (tweak to taste)
SCORE_WEIGHTS = {
    "length": 2,           # if length in good range
    "attachment": 3,
    "emoji": 1,
    "rare_word": 1,
    "question": 1,
    "reactions": 1,        # per reaction (capped)
    "mentions": -1,
    "url": -1
}

# Reaction score cap
REACTION_SCORE_CAP = 3


class ServerWrapped(commands.Cog):
    """Create a '[Server] Wrapped' summary for a user for a given year."""

    def __init__(self):
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(**DEFAULTS)

    # -------------------
    # Setup command
    # -------------------
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="serverwrapped-setup", usage="<#channel|id> [#channel2 ...]")
    async def setup(self, ctx: commands.Context, *channels: discord.TextChannel):
        """
        Configure which channels are included in Wrapped scans.
        Provide any number of channel mentions or IDs. This replaces the list.
        Example:
        `[p]serverwrapped-setup #general #art #bot-logs`
        """
        if not channels:
            await ctx.send("Provide at least one channel to include in scans.")
            return
        channel_ids = [c.id for c in channels]
        await self.config.guild(ctx.guild).channels.set(channel_ids)
        await ctx.send(f"Wrapped will scan the {len(channel_ids)} configured channels.")

    # -------------------
    # Main command
    # -------------------
    @commands.guild_only()
    @commands.command(name="serverwrapped", aliases=["wrapped"])
    async def wrapped(self, ctx: commands.Context, member: Optional[discord.Member] = None, year: Optional[int] = None):
        """
        Generate a Server Wrapped for a user.
        Usage:
        `[p]serverwrapped` -> yourself, current year
        `[p]serverwrapped @User 2024` -> specific user/year
        """
        target = member or ctx.author
        now = datetime.now(timezone.utc)
        year = year or now.year

        # Get allowed channels
        allowed_channel_ids = await self.config.guild(ctx.guild).channels()
        if not allowed_channel_ids:
            await ctx.send("No channels configured. An admin must run `[p]serverwrapped-setup` with allowed channels first.")
            return

        # Determine date range (start of year to end of year)
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)

        # Adjust start if user joined after year start
        if target.joined_at and target.joined_at.replace(tzinfo=timezone.utc) > start:
            start = target.joined_at.replace(tzinfo=timezone.utc)

        # Gather messages
        await ctx.trigger_typing()
        messages = []
        channel_objs = []
        for cid in allowed_channel_ids:
            ch = ctx.guild.get_channel(cid)
            if ch and isinstance(ch, discord.TextChannel):
                channel_objs.append(ch)

        if not channel_objs:
            await ctx.send("No valid channels (or I can't see them) in the configured channel list.")
            return

        # Async gather messages per channel to avoid blocking too long
        # We'll yield control between channels
        for ch in channel_objs:
            try:
                async for msg in ch.history(limit=None, after=start, before=end, oldest_first=True):
                    if msg.author and msg.author.id == target.id and not msg.author.bot:
                        messages.append(msg)
            except discord.Forbidden:
                # can't read channel; skip
                continue
            except discord.HTTPException:
                # could be rate-limited; small sleep
                await asyncio.sleep(1)
                continue
            # little pause to be polite
            await asyncio.sleep(0)

        # If no messages: produce a light result
        if not messages:
            embed = discord.Embed(title=f"{ctx.guild.name} Wrapped — {year}", color=discord.Color.blurple())
            embed.set_author(name=str(target), icon_url=target.avatar.url if target.avatar else None)
            embed.add_field(name="No activity", value="You didn't send a message in the configured channels this year.", inline=False)
            await ctx.send(embed=embed)
            return

        # Compute stats
        stats = await self._analyze_messages(messages)

        # Build embed summary
        embed = discord.Embed(title=f"{ctx.guild.name} Wrapped — {year}", color=discord.Color.brand_red())
        embed.set_author(name=str(target), icon_url=target.avatar.url if target.avatar else None)

        # How the year started
        first_msg = min(messages, key=lambda m: m.created_at)
        how_started_text = f"First message ({first_msg.created_at.date()} in #{first_msg.channel.name}):\n{self._shorten(first_msg.content)}"
        embed.add_field(name="How the year started", value=how_started_text, inline=False)

        # Most common topics
        if stats["topics"]:
            topics_pretty = " · ".join(stats["topics"][:6])
        else:
            topics_pretty = "—"
        embed.add_field(name="Most common topics", value=topics_pretty, inline=False)

        # Sidekicks
        if stats["sidekicks"]:
            sidekicks_pretty = "\n".join(f"{i+1}. {name} — {count} msgs" for i, (name, count) in enumerate(stats["sidekicks"][:8]))
        else:
            sidekicks_pretty = "—"
        embed.add_field(name="Most common sidekicks", value=sidekicks_pretty, inline=True)

        # Channels
        channels_pretty = "\n".join(f"{i+1}. #{name} — {count}" for i, (name, count) in enumerate(stats["channels"][:8]))
        embed.add_field(name="Most used channels", value=channels_pretty or "—", inline=True)

        # Emojis
        if stats["emojis"]:
            emojis_pretty = " ".join(f"{e}" for e, _ in stats["emojis"][:12])
        else:
            emojis_pretty = "—"
        embed.add_field(name="Most used emojis", value=emojis_pretty, inline=False)

        # Most common words
        if stats["common_words"]:
            words_pretty = ", ".join(w for w, _ in stats["common_words"][:16])
        else:
            words_pretty = "—"
        embed.add_field(name="Top words (excluding stopwords)", value=words_pretty, inline=False)

        # Summary stats
        st_lines = [
            f"Total messages: **{len(messages)}**",
            f"Attachments posted: **{stats['attachments']}**",
            f"Messages with reactions: **{stats['reacted_messages']}**",
        ]
        embed.add_field(name="Summary", value="\n".join(st_lines), inline=False)

        # Highlight
        if stats["highlight"]:
            highlight_msg, highlight_attachment = stats["highlight"]
            hl_text = f"{self._shorten(highlight_msg.content)}\n— in #{highlight_msg.channel.name} on {highlight_msg.created_at.date()}"
            embed.add_field(name="Highlight", value=hl_text, inline=False)
            # If attachment exists, set as image (first one)
            if highlight_attachment:
                embed.set_image(url=highlight_attachment)
        else:
            embed.add_field(name="Highlight", value="Couldn't find a suitable highlight.", inline=False)

        # Send embed (if it's long, Red will handle)
        await ctx.send(embed=embed)

    # -------------------
    # Analysis helpers
    # -------------------
    async def _analyze_messages(self, messages: List[discord.Message]) -> dict:
        """Return analysis dict with topics, sidekicks, channels, emojis, words, attachments, highlight"""
        total_attachments = 0
        reacted_messages = 0
        channels_counter = Counter()
        sidekick_counter = Counter()
        emoji_counter = Counter()
        word_counter = Counter()
        all_texts = []
        msg_word_lists = []  # for rare word detection per message
        candidate_highlights = []

        # Build frequent-word baseline to detect 'rare' words
        for m in messages:
            channels_counter[m.channel.name] += 1
            if m.attachments:
                total_attachments += len(m.attachments)
            if m.reactions:
                reacted_messages += 1
            # sidekicks: users mentioned in replies/context - use message references & mentions
            if m.reference and m.reference.resolved:
                ref = m.reference.resolved
                if isinstance(ref, discord.Message) and ref.author:
                    sidekick_counter[ref.author.display_name] += 1
            for u in m.mentions:
                # don't count the author themselves
                if u.id != m.author.id:
                    sidekick_counter[u.display_name] += 1

            # emojis: both custom and unicode
            for match in CUSTOM_EMOJI_RE.findall(m.content):
                emoji_counter[match] += 1
            for match in UNICODE_EMOJI_RE.findall(m.content):
                emoji_counter[match] += 1
            # colon emojis like :grin:
            for token in m.content.split():
                if COLON_EMOJI_RE.match(token):
                    emoji_counter[token] += 1

            # text processing
            text = m.content or ""
            text_no_url = URL_RE.sub("", text)
            words = [w.lower() for w in WORD_RE.findall(text_no_url)]
            msg_word_lists.append(words)
            for w in words:
                if w not in STOPWORDS and len(w) > 1:
                    word_counter[w] += 1
            all_texts.append(text)
            # candidate highlight preliminary: will score later
            candidate_highlights.append(m)

        # Compute common words list
        common_words = word_counter.most_common()

        # Topics: get bigrams and trigrams from cleaned words
        topics = self._extract_topics(msg_word_lists)

        # Highlight: score each candidate
        highlight_msg, highlight_attachment = self._choose_highlight(candidate_highlights, common_words)

        # Build results
        return {
            "topics": topics,
            "sidekicks": sidekick_counter.most_common(),
            "channels": channels_counter.most_common(),
            "emojis": emoji_counter.most_common(),
            "common_words": common_words,
            "attachments": total_attachments,
            "reacted_messages": reacted_messages,
            "highlight": (highlight_msg, highlight_attachment)
        }

    def _extract_topics(self, list_of_wordlists: List[List[str]]) -> List[str]:
        """
        Lightweight topic extraction via frequent bigrams & trigrams.
        Returns a list of topic strings ordered by frequency.
        """
        bigrams = Counter()
        trigrams = Counter()

        for words in list_of_wordlists:
            cleaned = [w for w in words if w not in STOPWORDS]
            # bigrams
            for i in range(len(cleaned) - 1):
                bigr = f"{cleaned[i]} {cleaned[i+1]}"
                bigrams[bigr] += 1
            # trigrams
            for i in range(len(cleaned) - 2):
                trigr = f"{cleaned[i]} {cleaned[i+1]} {cleaned[i+2]}"
                trigrams[trigr] += 1

        topics = []
        # Prefer trigrams with 3+ occurrences
        for t, c in trigrams.most_common(12):
            if c >= 3:
                topics.append(t)
        # Then bigrams with 3+ occurrences
        for b, c in bigrams.most_common(24):
            if c >= 3:
                topics.append(b)
        # Finally most frequent single words as fallback
        # (caller likely has computed word frequencies; we avoid heavy cross-dependency)
        return topics

    def _choose_highlight(self, candidates: List[discord.Message], common_words: List[Tuple[str, int]]) -> Tuple[Optional[discord.Message], Optional[str]]:
        """
        Score candidate messages and return top message plus an image url if one exists.
        """
        common_words_set = {w for w, _ in common_words[:200]}  # top common words
        best_score = -9999
        best_msg = None
        best_attach_url = None

        for m in candidates:
            # Exclusion filters
            if not self._is_message_valid_for_highlight(m):
                continue

            score = 0
            content = (m.content or "").strip()

            # length scoring
            if MIN_HIGHLIGHT_LEN <= len(content) <= MAX_HIGHLIGHT_LEN:
                score += SCORE_WEIGHTS["length"]

            # attachments
            image_url = None
            for a in m.attachments:
                if a.content_type and a.content_type.startswith("image"):
                    image_url = a.url
                    break
                # treat gifs as images too
                if a.filename.lower().endswith((".gif", ".png", ".jpg", ".jpeg", ".webp")):
                    image_url = a.url
                    break
            if image_url:
                score += SCORE_WEIGHTS["attachment"]

            # emojis count
            emoji_count = len(UNICODE_EMOJI_RE.findall(content)) + len(CUSTOM_EMOJI_RE.findall(content))
            if 1 <= emoji_count <= 3:
                score += SCORE_WEIGHTS["emoji"]

            # question
            if "?" in content:
                score += SCORE_WEIGHTS["question"]

            # reactions
            reaction_count = sum(r.count for r in m.reactions)
            score += min(reaction_count * SCORE_WEIGHTS["reactions"], REACTION_SCORE_CAP)

            # contains url or mentions -> small penalty
            if URL_RE.search(content):
                score += SCORE_WEIGHTS["url"]
            if m.mentions:
                score += SCORE_WEIGHTS["mentions"]

            # rare word boost: word not in common_words_set
            words = [w.lower() for w in WORD_RE.findall(URL_RE.sub("", content))]
            rare_word_bonus = 0
            for w in words:
                if w and w not in common_words_set and w not in STOPWORDS and len(w) > 2:
                    rare_word_bonus = 1
                    break
            score += rare_word_bonus * SCORE_WEIGHTS["rare_word"]

            # small tie-breaker: later messages win slightly (freshness)
            freshness = (m.created_at - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds() / 1e9
            score += freshness * 1e-6

            if score > best_score:
                best_score = score
                best_msg = m
                best_attach_url = image_url

        return best_msg, best_attach_url

    def _is_message_valid_for_highlight(self, m: discord.Message) -> bool:
        """Return False for messages that are too short, only URL, only emoji, commands, or bot messages."""
        if not m.content and not m.attachments:
            return False
        if m.author.bot:
            return False
        content = (m.content or "").strip()
        # Too short or too long
        if content and (len(content) < MIN_HIGHLIGHT_LEN or len(content) > MAX_HIGHLIGHT_LEN):
            # allow attachments even if short, so we don't discard images
            if not m.attachments:
                return False
        # Only URLs
        if content and URL_RE.sub("", content).strip() == "":
            return False
        # Only mentions
        if MENTION_RE.match(content):
            return False
        # Only emojis (unicode, custom, or :colon: type)
        if ONLY_ANY_EMOJI_RE.match(content):
            return False
        # commands (starts with typical prefix or slash) - skip
        if content.startswith(("!", ".", "-", "~", "/")):
            # allow slash commands content is unlikely in message content
            return False
        return True

    def _shorten(self, text: str, limit: int = 240) -> str:
        if not text:
            return "—"
        t = text.strip()
        if len(t) <= limit:
            return t
        return t[:limit - 1].rsplit(" ", 1)[0] + "…"

# Cog setup
def setup(bot):
    bot.add_cog(ServerWrapped())
