import sys
import os
import time

sys.path.insert(0, os.path.abspath("."))

from backend.memory.conversation import (
    add_message,
    get_budgeted_messages,
    estimate_tokens,
    clear_conversation
)

def run_test_12():
    session_id = f"session_test_12_long_{int(time.time())}"
    clear_conversation(session_id)

    total_to_create = 80 # Between 50-100 messages
    print("=" * 65)
    print("TEST 12: LONG CONVERSATION STRESS TEST")
    print(f"Creating {total_to_create} conversation messages in '{session_id}'...")
    print("=" * 65)

    created = []
    for i in range(1, total_to_create + 1):
        role = "user" if i % 2 != 0 else "assistant"
        content = (
            f"[Turn #{i:03d}] Extended conversational text discussing distributed caching, "
            f"database indexing strategies, and agentic workflows. Ensuring deterministic token estimation. "
            f"Identifier tag: MSG_KEY_{i:04d}."
        )
        add_message(sender=role, message=content, session_id=session_id)
        created.append({"role": role, "content": content, "idx": i})

    total_supplied = len(created)
    total_tokens = sum(estimate_tokens(m["content"]) for m in created)
    configured_budget = 1200

    print(f"Total messages created: {total_supplied}")
    print(f"Total estimated tokens: {total_tokens} (Configured budget: {configured_budget})")

    # Call production budgeted retrieval
    budgeted = get_budgeted_messages(session_id=session_id)

    retained_count = len(budgeted)
    discarded_count = total_supplied - retained_count
    retained_tokens = sum(estimate_tokens(m["content"]) for m in budgeted)
    oldest_retained = budgeted[0]["content"] if budgeted else None
    newest_retained = budgeted[-1]["content"] if budgeted else None

    # Verifications
    expected_newest = created[-1]["content"]
    newest_preserved = (newest_retained == expected_newest)

    # Check chronological order
    chronological_order = True
    for idx, msg in enumerate(budgeted):
        expected_idx_msg = created[total_supplied - retained_count + idx]["content"]
        if msg["content"] != expected_idx_msg:
            chronological_order = False
            break

    within_budget = retained_tokens <= configured_budget

    passed = (
        total_supplied == total_to_create
        and total_tokens > configured_budget
        and within_budget
        and newest_preserved
        and chronological_order
        and retained_count > 0
    )

    # Clean up test session
    clear_conversation(session_id)

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 12")
    print("=" * 65)
    print("Test 12:")
    print(f"Total messages: {total_supplied}")
    print(f"Total estimated tokens: {total_tokens}")
    print(f"Configured budget: {configured_budget}")
    print(f"Retained messages: {retained_count}")
    print(f"Discarded messages: {discarded_count}")
    print(f"Retained tokens: {retained_tokens}")
    print(f"Oldest retained: {oldest_retained[:70]}...")
    print(f"Newest retained: {newest_retained[:70]}...")
    print(f"Newest preserved: {'TRUE' if newest_preserved else 'FALSE'}")
    print(f"Chronological order: {'TRUE' if chronological_order else 'FALSE'}")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    run_test_12()
