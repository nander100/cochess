"""The text of each account email (SPEC_V4 §12.4). Placeholders: $name, $app_url, $note.

The HTML part is made from the same text (`to_html`): each paragraph escaped and wrapped, and the
app's address made a link, so the two parts can't drift apart.
"""

import html

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
    "terms_updated": """Hi $name,

We've updated the CoChess Terms of Service and Privacy Policy. You'll be asked to review and accept
them the next time you sign in at $app_url

The CoChess team
""",
}


def to_html(text: str, app_url: str) -> str:
    """`text` with its placeholders already filled in and escaped; `app_url` escaped too."""
    paragraphs = [" ".join(block.split()) for block in text.strip().split("\n\n")]
    link = f'<a href="{app_url}">{app_url}</a>'
    body = "\n".join(f"<p>{p.replace(app_url, link)}</p>" for p in paragraphs if p)
    return f"<!doctype html>\n<html><body>\n{body}\n</body></html>\n"


def escape(value: str) -> str:
    return html.escape(value, quote=True)
