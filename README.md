# Clawback 🧾

**Token-efficient group expense splitting library and CLI.**

Clawback is designed for AI agents (like [OpenClaw](https://openclaw.dev)) to manage trip expenses via WhatsApp groups, with Google Sheets as the shared ledger. The primary design goal is **minimal LLM token usage** during active use.

## Design Philosophy

- **Deterministic parsing**: Natural language commands are parsed via regex patterns, not LLM calls
- **Confirmation workflow**: Write commands require human confirmation before execution (accuracy > speed)
- **Template-based responses**: All output text is template-rendered, easily swappable
- **Decimal arithmetic**: All financial math uses Python `Decimal`, never floats
- **Pure ledger logic**: Financial calculations are pure functions with no I/O

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    WhatsApp / Chat UI                       │
└─────────────────┬───────────────────────────────────────────┘
                  │ text message
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   Parser (regex-based)                      │
│              Zero LLM - deterministic only                  │
└─────────────────┬───────────────────────────────────────────┘
                  │ ParsedCommand
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   CommandHandler                            │
│  • Read commands → execute immediately                      │
│  • Write commands → confirmation → pending → execute        │
└─────────────────┬───────────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
┌───────────────┐   ┌───────────────┐
│    Ledger     │   │    Sheets     │
│  (pure math)  │   │  (gog CLI)    │
└───────────────┘   └───────────────┘
```

## Command Reference

| Command | Example | Description |
|---------|---------|-------------|
| `kai add` | `kai add Dinner ₪340 paid by Dan` | Add expense, split equally among all |
| `kai add ... only` | `kai add wine €60 paid by Avi only Dan & Sara` | Split among specific people |
| `kai add ... custom` | `kai add gifts ₪100 paid by Dan custom Sara:60, Avi:40` | Custom split amounts |
| `kai settle` | `kai settle Sara paid Dan ₪100` | Record a settlement payment |
| `kai balances` | `kai balances` or `kai balances in EUR` | Show who owes what |
| `kai summary` | `kai summary` | Full trip summary |
| `kai who` | `kai who` | List participants |
| `kai undo` | `kai undo` | Undo last action |
| `kai trip` | `kai trip Beach Vacation base EUR` | Create/switch trip |
| `kai help` | `kai help` | Show help |

### Currencies

Supported: `₪`/`ILS`, `$`/`USD`, `€`/`EUR`, `£`/`GBP`, `¥`/`JPY`

## Setup

### Install

```bash
pip install clawback
```

### Google Sheets (optional)

Clawback uses the `gog` CLI for Sheets integration:

```bash
npm install -g gog
gog auth login
export GOG_KEYRING_PASSWORD=your-keyring-password
```

### CLI Usage

```bash
# Parse a command (debug)
clawback parse "kai add dinner ₪100 paid by Dan"

# Handle a message (interactive)
clawback handle chat123 "kai trip Beach Vacation"
clawback handle chat123 "yes"
clawback handle chat123 "kai add dinner ₪300 paid by Dan only Dan, Sara, Avi"
clawback handle chat123 "yes"
clawback handle chat123 "kai balances"

# List trips
clawback trips

# Show balances for a trip
clawback balances "Beach Vacation"
```

### Library Usage

```python
from decimal import Decimal
from clawback.state import TripManager
from clawback.commands import CommandHandler

# Initialize
manager = TripManager()  # Uses ~/.clawback by default
handler = CommandHandler(manager, create_sheets=False)

# Handle messages
response = handler.handle_message("chat123", "kai trip Test Trip")
print(response)  # Confirmation prompt

response = handler.handle_message("chat123", "yes")
print(response)  # Trip created!

response = handler.handle_message("chat123", "kai add lunch ₪60 paid by Dan only Dan, Sara")
print(response)  # Confirmation prompt

response = handler.handle_message("chat123", "yes")
print(response)  # Expense added with debt summary
```

## Confirmation Workflow

Write commands (add, settle, undo, trip create) require confirmation:

```
User: kai add dinner ₪340 paid by Yonatan
Bot:  💬 Got it: *dinner* ₪340 paid by Yonatan, split equally → Dan ₪85, Sara ₪85, Avi ₪85, Yonatan ₪85. Add this? (yes/no)
User: yes
Bot:  ✅ *dinner* ₪340 (paid by Yonatan)
      Dan ₪85, Sara ₪85, Avi ₪85, Yonatan ₪85

      📊 Running debts:
      • Dan → Yonatan: ₪85
      • Sara → Yonatan: ₪85
      • Avi → Yonatan: ₪85
```

Read commands (balances, summary, who, help) execute immediately.

## Development

```bash
# Clone and install dev dependencies
git clone https://github.com/openclaw/clawback
cd clawback
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=clawback --cov-report=term --cov-fail-under=90

# Lint
ruff check src tests
ruff format src tests

# Type check
mypy src
```

## State Storage

Clawback stores state in `~/.clawback/`:
- `trips.json` - All trip data (expenses, settlements, participants)
- `pending.json` - Pending confirmations (expire after 5 minutes)
- `active.json` - Chat ID to active trip mapping

## Google Sheets Structure

Each trip creates a sheet with 5 tabs:
- **Expenses** (append-only): expense_id, timestamp, description, amount, currency, paid_by
- **Splits** (append-only): expense_id, person, amount_owed, currency
- **Settlements** (append-only): settlement_id, timestamp, from, to, amount, currency, notes
- **Balances** (rewritten): person, net_balance, currency
- **Summary** (rewritten): from, to, amount, currency

## License

MIT
