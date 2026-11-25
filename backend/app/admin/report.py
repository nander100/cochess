"""`cli usage-report`: the overview as text, for when the web app is down (SPEC_V4 §10.3)."""

from app.admin.overview import Overview

MICROUSD_PER_CREDIT = 10_000  # CreditSettings.microusd_per_credit


def dollars(microusd: int | None) -> str:
    if microusd is None:
        return "-"
    sign = "-" if microusd < 0 else ""
    return f"{sign}${abs(microusd) / 1_000_000:,.2f}"


def credits(microusd: int) -> str:
    return f"{microusd / MICROUSD_PER_CREDIT:,.1f}".removesuffix(".0")


def usage_report(view: Overview) -> str:
    users, plans, money = view.users, view.plans, view.money
    statuses = ", ".join(f"{count} {status}" for status, count in sorted(users.by_status.items()))
    waiting = (
        f", waiting since {users.oldest_wait_since:%Y-%m-%d}" if users.oldest_wait_since else ""
    )
    since = f" (since {view.since:%Y-%m-%d %H:%M} UTC)" if view.since else ""
    lines = [
        f"Period: {view.period}{since}",
        f"Players: {users.total} ({statuses}); waitlist {users.waitlist}{waiting}",
        f"Subscribers {plans.subscribers}, past due {plans.past_due}, "
        f"cancelled this month {plans.cancelled_this_month}",
        f"Trial only: {plans.trial_with_credits} with credits, "
        f"{plans.trial_without_credits} without; at zero credits: {plans.zero_credits}",
    ]
    for activity in view.activity:
        lines.append(
            f"Last {activity.days} days: {activity.sign_ups} sign-ups, "
            f"{activity.acceptances} accepted, {activity.active_players} active, "
            f"{activity.games_added} games, {activity.coach_calls} coach calls"
        )
    hit = f"{money.cache_hit_rate:.0%}" if money.cache_hit_rate is not None else "-"
    tasks = ", ".join(f"{task} {n}" for task, n in sorted(view.calls_by_task.items())) or "none"
    lines += [
        f"Revenue {dollars(money.revenue_microusd)} (after {dollars(money.refunds_microusd)} "
        "refunded; before Stripe fees)",
        f"API cost {dollars(money.api_cost_microusd)}; difference "
        f"{dollars(money.difference_microusd)}",
        f"Per coached player {dollars(money.cost_per_player_microusd)}, per game "
        f"{dollars(money.cost_per_game_microusd)}; cache hit rate {hit}",
        f"Credits granted {credits(money.credits_granted_microusd)}, spent "
        f"{credits(money.credits_spent_microusd)}",
        f"Coach calls by task: {tasks}",
    ]
    return "\n".join(lines)
