# Clawback 🧾

[![CI](https://github.com/yhyatt/clawback/actions/workflows/ci.yml/badge.svg)](https://github.com/yhyatt/clawback/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)](https://github.com/yhyatt/clawback/actions)
[![PyPI](https://img.shields.io/pypi/v/clawback)](https://pypi.org/project/clawback/)
[![Python](https://img.shields.io/pypi/pyversions/clawback)](https://pypi.org/project/clawback/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Group expense splitting that understands how you actually talk.**

No forms. No dropdowns. Just say what happened.

---

## Why Clawback?

Every expense app makes you fill in fields. Clawback lets you describe what happened, like you'd tell a friend:

```
Dan paid ₪340 for dinner, split equally between Dan, Yonatan, Louise, and Zoe
```

Or in Hebrew:

```
דן שילם 340 שקל על ארוחת ערב, מחולק שווה בין דן, יונתן, לואיז וזואי
```

Both work. You get the same result. No app required — just a WhatsApp group and a shared Google Sheet.

---

## What Makes It Different

| Feature | Clawback | Splitwise | Tricount |
|---|---|---|---|
| Natural language input | ✅ | ❌ | ❌ |
| Hebrew / multilingual | ✅ | ❌ | ❌ |
| WhatsApp-native | ✅ | ❌ | ❌ |
| Google Sheets backend | ✅ | ❌ | ❌ |
| Zero-LLM reads | ✅ | — | — |
| Open source | ✅ | ❌ | ❌ |
| API-free for reads | ✅ | ❌ | ❌ |

---

## Features

- **🗣️ Natural language** — parse expenses as you'd say them in English or Hebrew
- **💱 Multi-currency** — ILS (`₪`), USD (`$`), EUR (`€`), GBP (`£`), JPY (`¥`); live FX via [frankfurter.app](https://www.frankfurter.app) (free, no key)
- **🌍 Multilingual** — Hebrew and English input, Hebrew payer names, space-separated thousands (`1 200`)
- **⚖️ Flexible splits** — equal split, split among specific people, or custom amounts per person
- **📊 Google Sheets backend** — shared live view for all trip members; no app install needed
- **⚡ Zero-LLM reads** — balances, summaries, and participant lists are instant and free (no API call)
- **✅ Confirmation workflow** — write operations show a preview before committing; cancel anytime
- **🔢 Decimal arithmetic** — all financial math uses Python `Decimal`, never floats
- **🏦 Audit log** — append-only ledger; full history always preserved
- **517 tests** — unit tests + 130 oracle edge cases (Hebrew names, SQL injection inputs, duplicate deduplication, space-separated amounts, and more)

---

## Quick Examples

### English

```bash
# Create a trip
clawback handle mytrip "kai trip Greece Vacation base EUR"
# → Confirm? yes

# Add an expense — equal split among all
clawback handle mytrip "kai add dinner €120 paid by Dan"

# Add an expense — specific people only
clawback handle mytrip "kai add wine €60 paid by Avi only Dan, Sara"

# Custom split amounts
clawback handle mytrip "kai add hotel ₪1200 paid by Yonatan custom Dan:400, Sara:400, Yonatan:400"

# Record a settlement
clawback handle mytrip "kai settle Sara paid Dan €40"

# Check balances (zero LLM calls)
clawback handle mytrip "kai balances"
clawback handle mytrip "kai balances in USD"

# Full summary
clawback handle mytrip "kai summary"
```

### Hebrew

```bash
clawback handle mytrip "קאי הוסף ארוחת ערב ₪340 שולם על ידי דן"
clawback handle mytrip "קאי יתרות"
```

Hebrew payer names and Hebrew numerals are supported. The parser handles both scripts in the same message.

---

## Token Economy

Clawback is designed to cost almost nothing to run.

| Operation | LLM calls | Cost |
|---|---|---|
| `kai balances` | 0 | Free |
| `kai summary` | 0 | Free |
| `kai who` | 0 | Free |
| `kai add ...` (write) | 0 (parser is regex) | Free |
| Confirmation step | 0 (template render) | Free |
| **Oracle test suite** | ~11 batch calls (Haiku) | ~$0.01 total |

**Reads are completely free.** No API call, no latency.

**Writes** use a regex parser — also no LLM. The confirmation message is template-rendered. The only time an LLM is optionally involved is the `--haiku` oracle validation test, which runs 130 edge cases in ~11 batched Haiku calls (~100s, ~$0.01).

This makes Clawback safe to run in a busy WhatsApp group all day without burning your API budget.

---

## Installation

```bash
pip install clawback
```

### Optional: Google Sheets integration

Clawback uses the [`gog` CLI](https://github.com/yhyatt/gog) for Sheets:

```bash
npm install -g gog
gog auth login
export GOG_KEYRING_PASSWORD=your-keyring-password
```

Without `gog`, Clawback works in local-only mode (state stored in `~/.clawback/`).

---

## CLI Reference

```bash
# Parse a message (debug/dry-run)
clawback parse "kai add dinner ₪100 paid by Dan"

# Handle a message for a chat session
clawback handle <chat_id> "<message>"

# List all trips
clawback trips

# Show balances for a trip
clawback balances "<trip name>"
```

### Command Syntax

| Command | Example |
|---|---|
| `kai add <desc> <amount> paid by <name>` | `kai add dinner ₪340 paid by Dan` |
| `kai add ... only <names>` | `kai add wine €60 paid by Avi only Dan, Sara` |
| `kai add ... custom <name>:<amt>, ...` | `kai add hotel ₪900 paid by Dan custom Dan:300, Sara:600` |
| `kai settle <from> paid <to> <amount>` | `kai settle Sara paid Dan €40` |
| `kai balances [in <currency>]` | `kai balances in USD` |
| `kai summary` | `kai summary` |
| `kai who` | `kai who` |
| `kai undo` | `kai undo` |
| `kai trip <name> [base <currency>]` | `kai trip Greece base EUR` |
| `kai help` | `kai help` |

---

## Confirmation Flow

Write commands show a preview before committing:

```
User:  kai add dinner ₪340 paid by Yonatan
Bot:   💬 Got it: *dinner* ₪340 paid by Yonatan, split equally →
       Dan ₪85 · Sara ₪85 · Louise ₪85 · Yonatan ₪85
       Add this? (yes/no)
User:  yes
Bot:   ✅ *dinner* ₪340 (paid by Yonatan)
       Dan ₪85 · Sara ₪85 · Louise ₪85 · Yonatan ₪85

       📊 Running debts:
       • Dan → Yonatan: ₪85
       • Sara → Yonatan: ₪85
       • Louise → Yonatan: ₪85
```

Pending confirmations expire after 5 minutes. Say `no` to cancel.

---

## OpenClaw Integration

Clawback is built to run as a native [OpenClaw](https://openclaw.dev) skill. Kai (OpenClaw's AI assistant) can parse expense messages directly from WhatsApp or Telegram groups and update the shared ledger — no manual CLI needed.

```
[WhatsApp group]
Yonatan: Dan paid ₪340 for dinner split equally
Kai: 💬 Got it: dinner ₪340 paid by Dan, split equally → ...
Yonatan: yes
Kai: ✅ Added. Running debts: Sara → Dan: ₪85 ...
```

See [`deploy/openclaw-skill/`](deploy/openclaw-skill/) for the skill definition.

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│           WhatsApp / Telegram / CLI              │
└─────────────────┬────────────────────────────────┘
                  │ text
                  ▼
┌──────────────────────────────────────────────────┐
│          Parser  (regex, zero LLM)               │
│          Handles EN + Hebrew, multi-currency     │
└─────────────────┬────────────────────────────────┘
                  │ ParsedCommand
                  ▼
┌──────────────────────────────────────────────────┐
│              CommandHandler                      │
│  reads  → execute immediately (zero LLM)        │
│  writes → preview → confirm → execute            │
└──────────┬─────────────────┬────────────────────┘
           ▼                 ▼
   ┌──────────────┐  ┌──────────────────┐
   │    Ledger    │  │  Google Sheets   │
   │  (pure math) │  │  (gog CLI sync)  │
   └──────────────┘  └──────────────────┘
```

---

## Google Sheets Structure

Each trip creates a spreadsheet with 5 tabs:

| Tab | Type | Contents |
|---|---|---|
| **Expenses** | append-only | expense_id, timestamp, description, amount, currency, paid_by |
| **Splits** | append-only | expense_id, person, amount_owed, currency |
| **Settlements** | append-only | settlement_id, timestamp, from, to, amount, currency |
| **Balances** | rewritten | person, net_balance, currency |
| **Summary** | rewritten | from, to, amount, currency |

---

## Development

```bash
git clone https://github.com/yhyatt/clawback
cd clawback
pip install -e ".[dev]"

# Lint + type check
ruff check src tests
mypy src

# Run tests (default CI — no oracle, no Haiku)
pytest

# Run with coverage
pytest --cov=clawback --cov-report=term --cov-fail-under=90
```

### Oracle Test Suite

The oracle suite validates 130 edge cases against ground-truth strings. It is **not** part of default CI (expensive and slow).

**Trigger via GitHub Actions:**
→ Actions → "Oracle Validation" → Run workflow → optionally enable `haiku_validation`

**Run manually:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
pytest -m oracle --haiku
```

This runs ~11 batched Haiku calls (~100s, ~$0.01) rather than one call per case.

---

## State

Local state is stored in `~/.clawback/`:

```
~/.clawback/
  trips.json     # All trip data (expenses, settlements, participants)
  pending.json   # Pending confirmations (5-minute TTL)
  active.json    # Chat ID → active trip mapping
```

---

## License

MIT © [yhyatt](https://github.com/yhyatt)
