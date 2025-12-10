import re
import asyncio
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import discord
from redbot.core import commands, Config

import nltk
from nltk import word_tokenize, pos_tag
from nltk.corpus import stopwords
from nltk.util import ngrams

# Ensure NLTK data is downloaded
nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')
nltk.download('stopwords')

STOPWORDS = set(stopwords.words('english'))

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MENTION_RE = re.compile(r"^(\s*<@!?\d+>\s*)+$")
ONLY_ANY_EMOJI_RE = re.compile(
    r"^(?:\s*(?:[\U0001F300-\U0001FAFF\u2600-\u27BF]|<a?:\w+:\d+>|:[a-zA-Z0-9_~]+:)\s*)+$"
)
CUSTOM_EMOJI_RE = re.compile(r"<a?:\w+:\d+>")
UNICODE_EMOJI_RE = re.compile(
    "[" 
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "]+", flags=re.UNICODE
)
COLON_EMOJI_RE = re.compile(r"^:[a-zA-Z0-9_~]+:$")

MIN_HIGHLIGHT_LEN = 10
MAX_HIGHLIGHT_LEN = 350

SCORE_WEIGHTS = {
    "length": 2,
    "attachment": 3,
    "emoji": 1,
    "rare_word": 1,
    "question": 1,
    "reactions": 1,
    "mentions": -1,
    "url": -1
}
REACTION_SCORE_CAP = 3

DEFAULTS = {"channels": []}

class ServerWrapped(commands.Cog):
    """Server Wrapped summary"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(**DEFAULTS)

    # -------------------
    # Setup command
    # -------------------
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="serverwrapped-setup", usage="<#channel|id> [#channel2 ...]")
    async def setup(self, ctx: commands.Context, *channels: discord.TextChannel):
        if not channels:
            await ctx.send("Provide at least one channel to include in scans.")
            return
        channel_ids = [c.id for c in channels]
        await self.config.guild(ctx.guild).channels.set(channel_ids)
        await ctx.send(f"Wrapped will scan {len(channel_ids)} channels.")

    # -------------------
    # Main command
    # -------------------
    @commands.guild_only()
    @commands.command(name="serverwrapped", aliases=["wrapped"])
    async def wrapped(self, ctx: commands.Context, member: Optional[discord.Member] = None, year: Optional[int] = None):
        target = member or ctx.author
        year = year or datetime.now(timezone.utc).year

        allowed_channel_ids = await self.config.guild(ctx.guild).channels()
        if not allowed_channel_ids:
            await ctx.send("No channels configured. Admin must run `[p]serverwrapped-setup` first.")
            return

        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if target.joined_at and target.joined_at.replace(tzinfo=timezone.utc) > start:
            start = target.joined_at.replace(tzinfo=timezone.utc)

        await ctx.typing()
        messages = []
        for cid in allowed_channel_ids:
            ch = ctx.guild.get_channel(cid)
            if not ch or not isinstance(ch, discord.TextChannel):
                continue
            try:
                async for m in ch.history(limit=None, after=start, before=end, oldest_first=True):
                    if m.author and m.author.id == target.id and not m.author.bot:
                        messages.append(m)
            except discord.Forbidden:
                continue
            except discord.HTTPException:
                await asyncio.sleep(1)
                continue
            await asyncio.sleep(0)

        if not messages:
            await ctx.send(f"{target} had no messages in configured channels for {year}.")
            return

        stats = self._analyze_messages(messages)

        embed = discord.Embed(title=f"{ctx.guild.name} Wrapped — {year}", color=discord.Color.brand_red())
        embed.set_author(name=str(target), icon_url=target.avatar.url if target.avatar else None)

        # How year started
        first_msg = min(messages, key=lambda m: m.created_at)
        first_topic = stats["topics"][0] if stats["topics"] else "chatting"
        embed.add_field(
            name="How the year started",
            value=f"You started off the year strong with a discussion about **{first_topic}**:\n{self._shorten(first_msg.content)}",
            inline=False
        )

        # Most common topics
        topics_pretty = " · ".join(stats["topics"][:6]) if stats["topics"] else "—"
        embed.add_field(name="Most common topics", value=topics_pretty, inline=False)

        # Sidekicks
        sidekicks_pretty = "\n".join(f"{i+1}. {name} — {count} msgs" for i, (name, count) in enumerate(stats["sidekicks"][:8])) if stats["sidekicks"] else "—"
        embed.add_field(name="Most common sidekicks", value=sidekicks_pretty, inline=False)

        # Emojis
        emojis_pretty = " ".join(e for e, _ in stats["emojis"][:12]) if stats["emojis"] else "—"
        embed.add_field(name="Most used emojis", value=emojis_pretty, inline=False)

        # Summary
        st_lines = [
            f"Total messages: **{len(messages)}**",
            f"Attachments posted: **{stats['attachments']}**",
            f"Messages with reactions: **{stats['reacted_messages']}**",
        ]
        embed.add_field(name="Summary", value="\n".join(st_lines), inline=False)

        # Highlight
        if stats["highlight"]:
            highlight_msg, _ = stats["highlight"]
            hl_text = f"{self._shorten(highlight_msg.content)}\n— in <#{highlight_msg.channel.id}> on {highlight_msg.created_at.date()}"
            embed.add_field(name="Highlight", value=hl_text, inline=False)
        else:
            embed.add_field(name="Highlight", value="Couldn't find a suitable highlight.", inline=False)

        await ctx.send(embed=embed)

    # -------------------
    # Analysis
    # -------------------
    def _analyze_messages(self, messages: List[discord.Message]) -> dict:
        channels_counter = Counter()
        sidekick_counter = Counter()
        emoji_counter = Counter()
        all_words = []
        candidate_highlights = []
        total_attachments = 0
        reacted_messages = 0

        for m in messages:
            channels_counter[m.channel.name] += 1
            if m.attachments:
                total_attachments += len(m.attachments)
            if m.reactions:
                reacted_messages += 1

            # sidekicks
            if m.reference and m.reference.resolved and isinstance(m.reference.resolved, discord.Message):
                ref = m.reference.resolved
                sidekick_counter[ref.author.display_name] += 1
            for u in m.mentions:
                if u.id != m.author.id:
                    sidekick_counter[u.display_name] += 1

            # emojis
            for match in CUSTOM_EMOJI_RE.findall(m.content):
                emoji_counter[match] += 1
            for match in UNICODE_EMOJI_RE.findall(m.content):
                emoji_counter[match] += 1
            for token in m.content.split():
                if COLON_EMOJI_RE.match(token):
                    emoji_counter[token] += 1

            # words for topics
            text_no_url = URL_RE.sub("", m.content or "")
            tokens = [w.lower() for w in word_tokenize(text_no_url) if w.isalpha()]
            tokens = [t for t in tokens if t not in STOPWORDS]
            all_words.append(tokens)

            candidate_highlights.append(m)

        # topics: noun/adjective bigrams and trigrams
        topics = self._extract_topics(all_words)

        # highlight
        highlight_msg, highlight_attach = self._choose_highlight(candidate_highlights, all_words)

        return {
            "topics": topics,
            "sidekicks": sidekick_counter.most_common(),
            "emojis": emoji_counter.most_common(),
            "attachments": total_attachments,
            "reacted_messages": reacted_messages,
            "highlight": (highlight_msg, highlight_attach)
        }

    def _extract_topics(self, list_of_wordlists: List[List[str]]) -> List[str]:
        counts = Counter()
        for words in list_of_wordlists:
            # POS tagging for nouns/adjectives
            pos = pos_tag(words)
            nouns_adj = [w for w, p in pos if p.startswith("NN") or p.startswith("JJ")]
            # bigrams and trigrams
            for n in [2, 3]:
                for gram in ngrams(nouns_adj, n):
                    counts[" ".join(gram)] += 1
        # filter low counts
        return [t for t, c in counts.most_common(20) if c >= 2]

    def _choose_highlight(self, candidates: List[discord.Message], all_words: List[List[str]]) -> Tuple[Optional[discord.Message], Optional[str]]:
        best_score = -9999
        best_msg = None
        best_attach_url = None

        word_counts = Counter([w for sublist in all_words for w in sublist])
        common_words_set = {w for w, _ in word_counts.most_common(200)}

        for m in candidates:
            if not self._is_message_valid_for_highlight(m):
                continue

            score = 0
            content = (m.content or "").strip()

            # length
            if MIN_HIGHLIGHT_LEN <= len(content) <= MAX_HIGHLIGHT_LEN:
                score += SCORE_WEIGHTS["length"]

            # attachments
            image_url = None
            for a in m.attachments:
                if a.content_type and a.content_type.startswith("image"):
                    image_url = a.url
                    break
                if a.filename.lower().endswith((".gif", ".png", ".jpg", ".jpeg", ".webp")):
                    image_url = a.url
                    break
            if image_url:
                score += SCORE_WEIGHTS["attachment"]

            # emojis
            emoji_count = len(UNICODE_EMOJI_RE.findall(content)) + len(CUSTOM_EMOJI_RE.findall(content))
            if 1 <= emoji_count <= 3:
                score += SCORE_WEIGHTS["emoji"]

            # question
            if "?" in content:
                score += SCORE_WEIGHTS["question"]

            # reactions
            reaction_count = sum(r.count for r in m.reactions)
            score += min(reaction_count * SCORE_WEIGHTS["reactions"], REACTION_SCORE_CAP)

            # url / mentions penalty
            if URL_RE.search(content):
                score += SCORE_WEIGHTS["url"]
            if m.mentions:
                score += SCORE_WEIGHTS["mentions"]

            # rare word
            words = [w.lower() for w in word_tokenize(URL_RE.sub("", content)) if w.isalpha()]
            if any(w not in common_words_set and w not in STOPWORDS and len(w) > 2 for w in words):
                score += SCORE_WEIGHTS["rare_word"]

            # freshness tie-breaker
            freshness = (m.created_at - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds() / 1e9
            score += freshness * 1e-6

            if score > best_score:
                best_score = score
                best_msg = m
                best_attach_url = image_url

        return best_msg, best_attach_url

    def _is_message_valid_for_highlight(self, m: discord.Message) -> bool:
        if not m.content and not m.attachments:
            return False
        if m.author.bot:
            return False
        content = (m.content or "").strip()
        if content and (len(content) < MIN_HIGHLIGHT_LEN or len(content) > MAX_HIGHLIGHT_LEN):
            if not m.attachments:
                return False
        if content and URL_RE.sub("", content).strip() == "":
            return False
        if MENTION_RE.match(content):
            return False
        if ONLY_ANY_EMOJI_RE.match(content):
            return False
        if content.startswith(("!", ".", "-", "~", "/")):
            return False
        return True

    def _shorten(self, text: str, limit: int = 240) -> str:
        if not text:
            return "—"
        t = text.strip()
        if len(t) <= limit:
            return t
        return t[:limit-1].rsplit(" ", 1)[0] + "…"

# Cog setup
def setup(bot):
    bot.add_cog(ServerWrapped(bot))
