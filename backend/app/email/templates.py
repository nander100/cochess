"""The text of each account email (SPEC_V4 §12.4). Placeholders: $name, $app_url, $note,
$credits.

The HTML part is made from the same text (`to_html`): each paragraph escaped and wrapped, and the
app's address made a link, so the two parts can't drift apart.
"""

import html
import re

TEXTS: dict[str, str] = {
    "waitlist_joined": """Hi $name,

Thanks for signing up for CoChess. You're on the waitlist.

We're letting players in a few at a time. We'll email you as soon as your account is ready, and
CoChess will open for you the next time you sign in with Google at $app_url

The CoChess team
""",
    "accepted": """Hi $name,

You've been accepted to CoChess.

Sign in with Google at $app_url to set up your profile and analyze your first game. Your free
trial includes coaching credits to get you started.

The CoChess team
""",
    "access_paused": """Hi $name,

Your access to CoChess has been paused.$note

Your games and history are kept. You can still sign in to download your data or delete your
account. If you think this is a mistake, reply to this email.

The CoChess team
""",
    "access_restored": """Hi $name,

Your access to CoChess is back. Sign in with Google at $app_url to pick up where you left off.

The CoChess team
""",
    "account_deleted": """Hi $name,

Your CoChess account has been deleted, as you asked. Your games, chats, reports and settings are
gone, and this is the last email we'll send to this address.

If you had a subscription, it was cancelled and won't renew. Stripe keeps its own records of past
payments. You're welcome back any time at $app_url

The CoChess team
""",
    "credits_low": """Hi $name,

You're running low on coaching credits. When they run out, analysis keeps working but the coach
pauses until you top up or your next monthly allowance arrives.

See your credits and options at $app_url/profile

The CoChess team
""",
    "credits_out": """Hi $name,

You're out of coaching credits, so the coach is paused. Your games still upload and analyze, and
everything you've done is kept.

Top up or subscribe at $app_url/profile to keep getting coached.

The CoChess team
""",
    "credits_added": """Hi $name,

$credits coaching credits were added to your CoChess account.$note

They don't expire. See them at $app_url/profile

The CoChess team
""",
    "terms_updated": """Hi $name,

We've updated the CoChess Terms of Service and Privacy Policy. You'll be asked to review and accept
them the next time you sign in at $app_url

The CoChess team
""",
}


def to_html(text: str, app_url: str) -> str:
    """`text` with its placeholders already filled in and escaped; `app_url` escaped too."""
    paragraphs = [" ".join(block.split()) for block in text.strip().split("\n\n")]
    # Every address on the app's site is a link (the app, /profile, an unsubscribe link).
    url = re.compile(re.escape(app_url) + r"[^\s<]*")
    body = "\n".join(
        f"<p>{url.sub(lambda m: f'<a href="{m[0]}">{m[0]}</a>', p)}</p>" for p in paragraphs if p
    )
    return f"<!doctype html>\n<html><body>\n{body}\n</body></html>\n"


def escape(value: str) -> str:
    return html.escape(value, quote=True)
