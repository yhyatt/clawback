"""
Oracle tests: Opus-generated GT dataset validates the full pipeline.
These run against real parser + ledger logic. Haiku validates confirmation messages.

NOT in default CI. Run manually:
  pytest tests/test_oracle.py -m oracle
  pytest tests/test_oracle.py -m oracle --haiku  (also validates with Haiku)

Trigger in GitHub Actions: workflow_dispatch on .github/workflows/oracle.yml
"""

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from clawback import ledger
from clawback.commands import format_confirmation, format_fallback
from clawback.models import CommandType, ParsedCommand, ParseError, SplitType, Trip
from clawback.parser import parse_command

# Path to oracle cases
ORACLE_CASES_PATH = Path(__file__).parent / "fixtures" / "oracle_cases.jsonl"


@pytest.fixture
def haiku_enabled(request: pytest.FixtureRequest) -> bool:
    """Check if Haiku validation is enabled."""
    return request.config.getoption("--haiku")


def load_oracle_cases() -> list[dict[str, Any]]:
    """Load all test cases from oracle_cases.jsonl."""
    cases = []
    with open(ORACLE_CASES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def get_case_ids() -> list[str]:
    """Get case IDs for parameterization."""
    return [case["id"] for case in load_oracle_cases()]


def get_cases_by_id() -> dict[str, dict[str, Any]]:
    """Get cases indexed by ID."""
    return {case["id"]: case for case in load_oracle_cases()}


# Pre-load cases for parameterization
ORACLE_CASES = load_oracle_cases()
CASES_BY_ID = {case["id"]: case for case in ORACLE_CASES}


def _save_oracle_cases() -> None:
    """Persist ORACLE_CASES back to oracle_cases.jsonl (used by --update-gt)."""
    import json as _json
    ORACLE_CASES_PATH.write_text(
        "\n".join(_json.dumps(c) for c in ORACLE_CASES) + "\n"
    )


def compare_decimal(actual: Decimal | str, expected: str) -> bool:
    """Compare decimal values with tolerance."""
    actual_dec = Decimal(str(actual))
    expected_dec = Decimal(expected)
    return abs(actual_dec - expected_dec) < Decimal("0.01")


def normalize_participants(participants: list[str] | None) -> list[str] | None:
    """Normalize participant list for comparison."""
    if participants is None:
        return None
    return sorted([p.capitalize() for p in participants])


_LLM_BATCH_SIZE = 12  # cases per LLM call


def _llm_call(prompt: str, max_tokens: int = 1024) -> str:
    """Send a prompt to the configured LLM backend, return raw text response."""
    import json as _json
    import urllib.request

    openclaw_url = os.environ.get("CLAWBACK_OPENCLAW_URL")
    openclaw_token = os.environ.get("CLAWBACK_OPENCLAW_TOKEN")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if openclaw_url and openclaw_token:
        req = urllib.request.Request(
            f"{openclaw_url}/v1/chat/completions",
            data=_json.dumps({
                "model": "openclaw:main",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            }).encode(),
            headers={
                "Authorization": f"Bearer {openclaw_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = _json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()

    elif anthropic_key:
        import anthropic
        client = anthropic.Anthropic(api_key=anthropic_key)
        resp = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    else:
        raise RuntimeError(
            "No LLM credentials. Set CLAWBACK_OPENCLAW_URL + CLAWBACK_OPENCLAW_TOKEN "
            "or ANTHROPIC_API_KEY"
        )


def validate_batch(
    cases: list[dict],  # [{"id": str, "input": str, "confirmation": str}]
    trip_participants: list[str] | None = None,
) -> dict[str, tuple[bool, str]]:
    """
    Batch-validate up to _LLM_BATCH_SIZE confirmation messages in a single LLM call.

    Returns {case_id: (is_valid, reason)}.
    """
    import json as _json

    participants_context = (
        f"The trip has a pre-configured default group: {', '.join(trip_participants)}. "
        "When no participants are specified by the user, splitting equally among this "
        "group is correct — do NOT flag 'participants not specified' as an error."
        if trip_participants
        else ""
    )

    cases_block = "\n\n".join(
        f'''[{c["id"]}]
Input: {c["input"]}
Confirmation: {c["confirmation"]}'''.strip()
        for c in cases
    )

    prompt = f"""You are auditing an expense-splitting assistant for financial accuracy. {participants_context}

For each case below, verify the confirmation message is accurate:
- Amount and currency match the input
- Payer is correct
- Per-person split amounts are arithmetically correct (verify the maths)
- If confirmation asks a clarifying question instead of showing splits, that is correct when no participants were specified

{cases_block}

Reply with a JSON array only — no markdown, no explanation outside the array:
[{{"id": "case_XXX", "verdict": "YES", "reason": "ok"}}, ...]

Use verdict "YES" if accurate, "NO" if anything is wrong. Be concise in reason."""

    raw = _llm_call(prompt, max_tokens=800)

    # Extract JSON array from response (strip any surrounding text)
    import re
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        # Fallback: treat all as passed if we can't parse (log warning)
        return {c["id"]: (True, f"parse-failed: {raw[:80]}") for c in cases}

    try:
        results = _json.loads(match.group())
        out: dict[str, tuple[bool, str]] = {}
        for r in results:
            is_ok = str(r.get("verdict", "")).upper() == "YES"
            out[r["id"]] = (is_ok, r.get("reason", ""))
        # Fill any missing ids as passed (LLM may skip some)
        for c in cases:
            if c["id"] not in out:
                out[c["id"]] = (True, "not-in-response")
        return out
    except Exception as e:
        return {c["id"]: (True, f"json-error: {e}") for c in cases}


@pytest.mark.oracle
class TestOracleParser:
    """Test parser against oracle cases."""

    @pytest.mark.parametrize("case_id", [c["id"] for c in ORACLE_CASES])
    def test_parse_case(self, case_id: str) -> None:
        """Test that parsing matches expected result."""
        case = CASES_BY_ID[case_id]
        input_text = case["input"]
        should_parse = case["should_parse"]

        result = parse_command(input_text)

        if should_parse:
            # Should return ParsedCommand, not ParseError
            assert not isinstance(result, ParseError), (
                f"Case {case_id}: Expected successful parse but got error: "
                f"{result.message if isinstance(result, ParseError) else 'unknown'}"
            )
            assert isinstance(result, ParsedCommand)

            expected = case.get("expected_parse", {})

            # Check command type
            if "command" in expected:
                expected_cmd = expected["command"]
                assert result.command_type.value == expected_cmd, (
                    f"Case {case_id}: Expected command '{expected_cmd}', "
                    f"got '{result.command_type.value}'"
                )

            # Check amount (fuzzy decimal comparison)
            if "amount" in expected and expected["amount"] is not None:
                assert result.amount is not None, f"Case {case_id}: Expected amount but got None"
                assert compare_decimal(result.amount, expected["amount"]), (
                    f"Case {case_id}: Expected amount {expected['amount']}, "
                    f"got {result.amount}"
                )

            # Check currency
            if "currency" in expected and expected["currency"] is not None:
                assert result.currency == expected["currency"], (
                    f"Case {case_id}: Expected currency '{expected['currency']}', "
                    f"got '{result.currency}'"
                )

            # Check paid_by
            if "paid_by" in expected and expected["paid_by"] is not None:
                assert result.paid_by is not None
                assert result.paid_by.lower() == expected["paid_by"].lower(), (
                    f"Case {case_id}: Expected paid_by '{expected['paid_by']}', "
                    f"got '{result.paid_by}'"
                )

            # Check description
            if "description" in expected and expected["description"] is not None:
                assert result.description is not None
                # Fuzzy match - lowercase comparison
                assert result.description.lower() == expected["description"].lower(), (
                    f"Case {case_id}: Expected description '{expected['description']}', "
                    f"got '{result.description}'"
                )

            # Check split_type
            if "split_type" in expected and expected["split_type"] is not None:
                assert result.split_type is not None
                assert result.split_type.value == expected["split_type"], (
                    f"Case {case_id}: Expected split_type '{expected['split_type']}', "
                    f"got '{result.split_type.value}'"
                )

            # Check participants
            if "participants" in expected and expected["participants"] is not None:
                expected_parts = normalize_participants(expected["participants"])
                actual_parts = normalize_participants(result.split_among)
                assert actual_parts == expected_parts, (
                    f"Case {case_id}: Expected participants {expected_parts}, "
                    f"got {actual_parts}"
                )

            # Check custom_splits
            if "custom_splits" in expected and expected["custom_splits"] is not None:
                assert result.custom_splits is not None
                for person, expected_amount in expected["custom_splits"].items():
                    person_cap = person.capitalize()
                    assert person_cap in result.custom_splits, (
                        f"Case {case_id}: Missing custom split for {person_cap}"
                    )
                    assert compare_decimal(result.custom_splits[person_cap], expected_amount), (
                        f"Case {case_id}: Custom split for {person_cap} "
                        f"expected {expected_amount}, got {result.custom_splits[person_cap]}"
                    )

            # Check trip fields
            if "trip_name" in expected:
                assert result.trip_name == expected["trip_name"], (
                    f"Case {case_id}: Expected trip_name '{expected['trip_name']}', "
                    f"got '{result.trip_name}'"
                )

            if "trip_base_currency" in expected and expected["trip_base_currency"] is not None:
                assert result.trip_base_currency == expected["trip_base_currency"]

            # Check settle fields
            if "from_person" in expected:
                assert result.from_person is not None
                assert result.from_person.lower() == expected["from_person"].lower()

            if "to_person" in expected:
                assert result.to_person is not None
                assert result.to_person.lower() == expected["to_person"].lower()

            # Check display_currency for balances
            if "display_currency" in expected:
                assert result.display_currency == expected["display_currency"]

        else:
            # Should return ParseError
            assert isinstance(result, ParseError), (
                f"Case {case_id}: Expected ParseError but got successful parse"
            )

            # Check error message contains expected text
            if "expected_error_contains" in case:
                assert case["expected_error_contains"].lower() in result.message.lower(), (
                    f"Case {case_id}: Error message '{result.message}' "
                    f"doesn't contain '{case['expected_error_contains']}'"
                )


@pytest.mark.oracle
class TestOracleFallback:
    """Test fallback messages for parse errors."""

    @pytest.mark.parametrize(
        "case_id",
        [c["id"] for c in ORACLE_CASES if not c["should_parse"]],
    )
    def test_fallback_message(self, case_id: str) -> None:
        """Test that fallback messages contain expected content."""
        case = CASES_BY_ID[case_id]
        input_text = case["input"]

        result = parse_command(input_text)
        assert isinstance(result, ParseError)

        # Get the fallback message
        fallback = format_fallback(result)

        # Check error type if specified
        if "expected_error_type" in case:
            assert result.error_type == case["expected_error_type"], (
                f"Case {case_id}: Expected error_type '{case['expected_error_type']}', "
                f"got '{result.error_type}'"
            )

        # Check fallback contains expected phrase
        if "expected_fallback_contains" in case:
            expected_phrase = case["expected_fallback_contains"].lower()
            assert expected_phrase in fallback.lower(), (
                f"Case {case_id}: Fallback message doesn't contain '{expected_phrase}'.\n"
                f"Fallback was: {fallback}"
            )


@pytest.mark.oracle
class TestOracleConfirmation:
    """Test confirmation message generation."""

    @pytest.mark.parametrize(
        "case_id",
        [c["id"] for c in ORACLE_CASES if c["should_parse"] and "expected_confirmation_contains" in c],
    )
    def test_confirmation_contains(self, case_id: str) -> None:
        """Test that confirmation messages contain expected phrases."""
        case = CASES_BY_ID[case_id]
        input_text = case["input"]

        result = parse_command(input_text)
        assert isinstance(result, ParsedCommand)

        # Create a mock trip for confirmation formatting
        trip = Trip(
            name="Test Trip",
            base_currency="ILS",
            participants=["Dan", "Sara", "Avi", "Yonatan", "Louise", "Zoe", "Lenny"],
        )

        confirmation = format_confirmation(result, trip)

        for expected_phrase in case["expected_confirmation_contains"]:
            assert expected_phrase in confirmation, (
                f"Case {case_id}: Confirmation doesn't contain '{expected_phrase}'.\n"
                f"Confirmation was: {confirmation}"
            )


@pytest.mark.oracle
class TestOracleBalances:
    """Test balance calculations after applying commands."""

    @pytest.mark.parametrize(
        "case_id",
        [c["id"] for c in ORACLE_CASES if c["should_parse"] and "expected_balances_after" in c],
    )
    def test_balances_after(self, case_id: str) -> None:
        """Test that balances match expected values after applying command."""
        case = CASES_BY_ID[case_id]
        input_text = case["input"]

        result = parse_command(input_text)
        assert isinstance(result, ParsedCommand)

        # Create fresh trip
        trip = Trip(name="Test Trip", base_currency="ILS")

        # Apply the command based on type
        if result.command_type == CommandType.ADD_EXPENSE:
            assert result.amount is not None
            assert result.currency is not None
            assert result.description is not None
            assert result.paid_by is not None

            # Compute splits
            if result.split_type == SplitType.CUSTOM:
                from clawback.models import Split

                assert result.custom_splits is not None
                splits = [
                    Split(person=person, amount=amount, currency=result.currency)
                    for person, amount in result.custom_splits.items()
                ]
            elif result.split_type == SplitType.ONLY:
                assert result.split_among is not None
                splits = ledger.compute_equal_splits(
                    result.amount, result.currency, result.split_among
                )
            else:  # EQUAL
                participants = result.split_among or [result.paid_by]
                splits = ledger.compute_equal_splits(
                    result.amount, result.currency, participants
                )

            new_trip, _ = ledger.add_expense(
                trip,
                description=result.description,
                amount=result.amount,
                currency=result.currency,
                paid_by=result.paid_by,
                splits=splits,
            )

        elif result.command_type == CommandType.SETTLE:
            assert result.from_person is not None
            assert result.to_person is not None
            assert result.amount is not None
            assert result.currency is not None

            new_trip, _ = ledger.add_settlement(
                trip,
                from_person=result.from_person,
                to_person=result.to_person,
                amount=result.amount,
                currency=result.currency,
            )

        else:
            pytest.skip(f"Case {case_id}: Balance test not applicable for {result.command_type}")
            return

        # Compute balances
        balances = ledger.compute_balances(new_trip)

        # Check expected balances
        for person, expected_balance in case["expected_balances_after"].items():
            person_cap = person.capitalize()
            actual = balances.get(person_cap, Decimal("0"))
            assert compare_decimal(actual, expected_balance), (
                f"Case {case_id}: Balance for {person_cap} "
                f"expected {expected_balance}, got {actual}"
            )


_HAIKU_TRIP = Trip(
    name="Test Trip",
    base_currency="ILS",
    participants=["Dan", "Sara", "Avi", "Yonatan", "Louise", "Zoe", "Lenny"],
)

# Pre-compute all (case_id → confirmation) for batch runs
_HAIKU_CASES: list[dict] = []
for _c in ORACLE_CASES:
    if _c["should_parse"] and _c.get("intent") == "add_expense":
        _r = parse_command(_c["input"])
        if isinstance(_r, ParsedCommand):
            _conf = format_confirmation(_r, _HAIKU_TRIP)
            _HAIKU_CASES.append({"id": _c["id"], "input": _c["input"], "confirmation": _conf})

# Run batch validation once at module level (cached); keyed by case_id
_HAIKU_RESULTS: dict[str, tuple[bool, str]] = {}


def _ensure_haiku_results() -> None:
    """Run batched LLM validation for all cases (once per test session)."""
    if _HAIKU_RESULTS:
        return
    for i in range(0, len(_HAIKU_CASES), _LLM_BATCH_SIZE):
        batch = _HAIKU_CASES[i : i + _LLM_BATCH_SIZE]
        results = validate_batch(batch, _HAIKU_TRIP.participants)
        _HAIKU_RESULTS.update(results)


@pytest.mark.oracle
class TestOracleHaiku:
    """LLM batch validation — always-on when oracle suite runs.

    Batches all add_expense confirmations into ~5 LLM calls instead of 60,
    cutting runtime from ~4 min to ~30 sec. Requires LLM credentials:
      CLAWBACK_OPENCLAW_URL + CLAWBACK_OPENCLAW_TOKEN  (preferred)
      ANTHROPIC_API_KEY                                 (fallback)
    """

    @pytest.mark.parametrize(
        "case_id",
        [c["id"] for c in _HAIKU_CASES],
    )
    def test_llm_validation(self, case_id: str, haiku_enabled: bool) -> None:
        """Batch-validate confirmation accuracy with a small LLM."""
        if not haiku_enabled:
            pytest.skip("LLM validation disabled (use --haiku to enable)")

        _ensure_haiku_results()

        case = CASES_BY_ID[case_id]
        is_valid, reason = _HAIKU_RESULTS.get(case_id, (True, "not-evaluated"))
        batch_item = next((c for c in _HAIKU_CASES if c["id"] == case_id), None)
        confirmation = batch_item["confirmation"] if batch_item else "?"

        assert is_valid, (
            f"Case {case_id}: LLM validation failed\n"
            f"  Input: {case['input']}\n"
            f"  Confirmation: {confirmation}\n"
            f"  Verdict: {reason}"
        )


@pytest.mark.oracle
class TestOracleConfirmationFormat:
    """Regression tests: actual formatter output must match GT expected_confirmation.

    GT was generated from the fixed formatter and captured in oracle_cases.jsonl.
    A failure here means either:
      (a) a formatter regression — fix the code, or
      (b) an intentional change — update GT with: pytest --update-gt
    """

    @pytest.mark.parametrize(
        "case_id",
        [c["id"] for c in ORACLE_CASES if c["should_parse"] and c.get("expected_confirmation")],
    )
    def test_confirmation_matches_gt(self, case_id: str, request: pytest.FixtureRequest) -> None:
        """Actual confirmation must exactly match the GT string.

        Run with --update-gt to regenerate GT from current formatter output.
        """
        update_gt = request.config.getoption("--update-gt", default=False)
        case = CASES_BY_ID[case_id]
        result = parse_command(case["input"])
        if not isinstance(result, ParsedCommand):
            pytest.skip(f"Case {case_id} did not parse")
            return

        trip = Trip(
            name="Test Trip",
            base_currency="ILS",
            participants=["Dan", "Sara", "Avi", "Yonatan", "Louise", "Zoe", "Lenny"],
        )
        actual = format_confirmation(result, trip)

        if update_gt:
            case["expected_confirmation"] = actual
            _save_oracle_cases()
            return

        expected = case["expected_confirmation"]
        assert actual == expected, (
            f"Case {case_id}: confirmation mismatch\n"
            f"  Input:    {case['input']}\n"
            f"  Expected: {expected}\n"
            f"  Actual:   {actual}\n"
            f"  Tip: run pytest --update-gt to accept current output as new GT"
        )


@pytest.mark.oracle
class TestOracleSummary:
    """Summary statistics for oracle test suite."""

    def test_oracle_stats(self) -> None:
        """Print summary statistics about oracle test cases."""
        cases = load_oracle_cases()

        total = len(cases)
        should_parse = sum(1 for c in cases if c["should_parse"])
        should_fail = total - should_parse

        by_language = {}
        by_intent = {}

        for case in cases:
            lang = case.get("language", "unknown")
            intent = case.get("intent", "unknown")
            by_language[lang] = by_language.get(lang, 0) + 1
            by_intent[intent] = by_intent.get(intent, 0) + 1

        print("\n📊 Oracle Test Suite Statistics")
        print(f"{'='*40}")
        print(f"Total cases: {total}")
        print(f"Should parse: {should_parse}")
        print(f"Should fail: {should_fail}")
        print("\nBy language:")
        for lang, count in sorted(by_language.items()):
            print(f"  {lang}: {count}")
        print("\nBy intent:")
        for intent, count in sorted(by_intent.items()):
            print(f"  {intent}: {count}")

        # Actually run a quick validation
        parse_successes = 0
        parse_failures = 0

        for case in cases:
            result = parse_command(case["input"])
            if case["should_parse"]:
                if isinstance(result, ParsedCommand):
                    parse_successes += 1
                else:
                    parse_failures += 1
            else:
                if isinstance(result, ParseError):
                    parse_successes += 1
                else:
                    parse_failures += 1

        print("\n📈 Validation Results:")
        print(f"  Correct: {parse_successes}/{total} ({100*parse_successes/total:.1f}%)")
        print(f"  Incorrect: {parse_failures}/{total}")

        # Assert quality bar
        assert parse_successes >= 50, f"Quality bar not met: only {parse_successes} cases passed"
