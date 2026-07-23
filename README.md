# ebay-assistant

A personal command-line assistant for eBay sellers, built by a low-volume
sportscard seller. It starts with the one thing eBay's automation can't do:
telling your buyer the moment their package is *actually* in the mail.

## Why

eBay knows when you print a shipping label and when the carrier first scans
the package — but not the moment you physically drop it at the post office.
That's a nice moment for a personal touch, especially for card buyers who
refresh tracking obsessively. This tool finds your recently labeled orders,
drafts a short friendly message per buyer, and sends it through eBay's
official Message API after you approve each one.

Nothing is ever sent without your confirmation.

## What it does

```
$ ebay-assistant notify
Fetching orders labeled in the last 7 days...
3 labeled orders; 1 already handled; 2 buyers to review.

==============================================================
[1/2] cardfan_88 — 1 order
  Order 12-34567-89012 (labeled Jul 22):
    1x 2023 Topps Chrome Jordan Walker RC #142
    -> USPS 9400111899223344556677

Draft (guessed "the card"):
  Hi! Just a quick note to let you know I dropped the card off at the
  post office — it's on the way to you. Thanks so much for your purchase!

[s]end  [v]ariant  [e]dit  [k]skip  [n]ever  [q]uit >
```

- **Contextual wording** — guesses "the card" / "the cards" / "the box" from
  quantities and title keywords (blaster, hobby, lot, sealed, ...). Pick a
  different variant or type your own with `v`, or edit the whole message
  in `$EDITOR` with `e`.
- **Combined shipping aware** — multiple orders from the same buyer get one
  message, and all of them are marked handled.
- **Never double-messages** — sent orders are recorded locally in
  `state.json` and skipped on the next run.
- **`--dry-run`** — see exactly what would be sent without sending anything.

## Install

Requires Python 3.11+.

```
git clone https://github.com/davidklotz/ebay_assistant.git
cd ebay_assistant
python3 -m venv .venv && .venv/bin/pip install .
.venv/bin/ebay-assistant --help    # or add .venv/bin to your PATH, or use pipx
```

## Setup (one time)

You need a (free) eBay developer account: <https://developer.ebay.com>.
Approval usually takes about a business day. Then run:

```
ebay-assistant init
```

The walkthrough covers everything, but in short:

1. **Keyset** — create a production keyset under *Your Account → Application
   Keys*. Production keys activate only after you handle the "Marketplace
   Account Deletion" requirement; since this tool runs locally and doesn't
   persist other users' data, choose the **"Not persisting eBay data"**
   exemption instead of hosting a notification endpoint.
2. **User token** — under *Your Account → User Access Tokens*, mint an OAuth
   token (not Auth'n'Auth) signed in as your seller account, with scopes:
   - `https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly`
   - `https://api.ebay.com/oauth/api_scope/commerce.message`

   Paste the **refresh token** into `init`. It lasts ~18 months; access
   tokens are refreshed automatically. When it expires, run
   `ebay-assistant init --refresh-token`.
3. `init` validates everything with a live read-only call.

## Usage

```
ebay-assistant orders               # read-only: recent orders + label status
ebay-assistant notify --dry-run     # preview drafts, send nothing
ebay-assistant notify               # the real thing
ebay-assistant notify --days 14     # wider look-back window
```

Suggested first run: `orders` (confirm your labels show up), then
`notify --dry-run`, then `notify`.

## Customizing the message

Edit `~/.config/ebay_assistant/template.txt`. Available placeholders:

| Placeholder         | Value                                    |
| ------------------- | ---------------------------------------- |
| `{package_desc}`    | "the card", "the cards", "the box", ...  |
| `{buyer_username}`  | buyer's eBay username                    |
| `{tracking_number}` | tracking number from the label           |
| `{carrier}`         | carrier code, e.g. USPS                  |

eBay's message limit is 2000 characters.

## Files

Everything lives in `~/.config/ebay_assistant/` (override with
`EBAY_ASSISTANT_CONFIG_DIR`):

| File               | Contents                                    |
| ------------------ | ------------------------------------------- |
| `config.toml`      | settings (environment, look-back window)    |
| `credentials.json` | keyset + refresh token (file mode 0600)     |
| `token_cache.json` | cached 2-hour access token (0600)           |
| `template.txt`     | your message template                       |
| `state.json`       | which orders were already messaged          |

Your credentials never leave your machine except in direct calls to
`api.ebay.com`. No buyer data is persisted anywhere — `state.json` records
only your own order IDs — which keeps the "Not persisting eBay data"
exemption from Setup step 1 accurate.

## Development

```
pip install -e ".[dev]"
pytest
```

## Roadmap

This repo is meant to slowly accumulate small quality-of-life tools for
sellers (hence the generic name). Ideas: relist helpers, offer-response
shortcuts, end-of-day shipping summaries. PRs and issues welcome.

## Disclaimer

Not affiliated with or endorsed by eBay. eBay does not publish rate limits
for the Message API — this tool is deliberately conservative (it only
messages actual buyers of your own recently shipped orders, one message per
buyer, each one human-approved), but use it responsibly.

## License

MIT
