# Raid Review

A desktop companion for reviewing raid nights from Warcraft Logs. Paste a report link, pick a boss, and it shows:

- every death, grouped by player and pull, with what killed them
- a death recap: up to 30 seconds of damage, heals and health before the death
- whether a personal defensive, Healthstone or health potion was ready and unused
- whether healing was landing in the last 5 seconds, and how many healers were alive
- what triggered each wipe (five or more deaths within three seconds)
- damage taken by player, pull and ability, with an avoidable-only view
- nights compared side by side per boss
- a one-file export of any review to share in Discord

## Running it

Download `RaidReview.exe` and double-click it. A console window opens (close it to quit) and the app opens in your browser at `http://127.0.0.1:8765`.

From source, with Python 3.11 or newer and no other packages:

```
python -m raidreview
```

## First launch: your Warcraft Logs API client

Each person uses their own free API client, so nobody's secret is shared.

1. Open https://www.warcraftlogs.com/api/clients/ and sign in.
2. Click **Create Client**. Use any name, enter `http://localhost` as the redirect URL, and leave "Public Client" unticked.
3. Paste the client ID and secret into the app.

Everything is stored in `%APPDATA%\RaidReview`: `config.json` (client and avoidable lists), `reviews\` (one file per review) and `tips.json` (cached Wowhead descriptions).

## How deaths are judged

- **Wipe deaths**: once five players die within three seconds, or after the fifth death of a wipe, the rest are part of the wipe and left out of totals unless you include them. Kills have no wipe cutoff.
- **No damage logged**: no killing blow and the player was above 30% health in their last two seconds. Usually a knock off the platform, a fall or a scripted kill. Defensives and heals are not judged.
- **Avoidable**: the killing blow is an ability ticked in the review. Lists are saved per boss. Sszorak starts with a list from public guides; other bosses start empty.
- **Defensive ready**: a personal, Healthstone or health potion was off cooldown and the overkill was under 45% of max health. Only spells the player cast at least once in the review count, so untalented spells are never flagged. Cooldowns are base values, shortened when the player cast a spell faster than that.
- **No heals**: healing plus shield absorbs in the last 5 seconds came to under 10% of max health.

## Limits

- Warcraft Logs allows 3,600 API points an hour per client. A night of about 30 pulls costs around 1,500, so roughly two full reviews an hour. Saved reviews reopen for free.
- Private reports can't be read with a client-credentials API client.
- Replay links open the right pull in Warcraft Logs at the start; the death time is printed on the button. The replay view does not load when a time range is added to the link.
- Ability descriptions come from Wowhead; their damage numbers may not match the difficulty you raided.

## Building the exe

```
python -m pip install pyinstaller
.\build.ps1
```

This runs the tests and writes `dist\RaidReview.exe`.
