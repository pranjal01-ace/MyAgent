import sys
import os
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath("."))

from backend.memory.conversation import (
    add_message,
    get_budgeted_messages,
    estimate_tokens,
    clear_conversation
)

def run_diagnostic():
    session_id = f"diag_session_{int(time.time())}"
    clear_conversation(session_id)

    # 1. Construct a conversation with 35 messages (exceeding 30)
    # Each message is approx 240 chars (~61 tokens), total ~2135 tokens (well over 1200 budget)
    total_to_create = 35
    created_messages = []
    
    print(f"Creating {total_to_create} conversation messages in session '{session_id}'...")
    for i in range(1, total_to_create + 1):
        sender = "user" if i % 2 != 0 else "assistant"
        content = (
            f"[Message #{i:02d}] "
            f"Detailed discussion turn #{i} explaining architectural concepts in distributed systems. "
            f"This content ensures consistent length for reliable token budgeting calculation. "
            f"Index reference: MSG_{i:03d}."
        )
        add_message(sender=sender, message=content, session_id=session_id)
        created_messages.append({"role": sender, "content": content, "index": i})

    total_supplied = len(created_messages)
    total_tokens_supplied = sum(estimate_tokens(m["content"]) for m in created_messages)
    print(f"Total messages created: {total_supplied}")
    print(f"Total estimated tokens created: {total_tokens_supplied} (exceeds budget: {total_tokens_supplied > 1200})")

    # 2. Call the existing production history-budgeting function with default parameters
    # Note: Default configured budget in production is max_tokens=1200, max_count=25
    budgeted = get_budgeted_messages(session_id=session_id)

    # 3. Calculate metrics
    retained_count = len(budgeted)
    discarded_count = total_supplied - retained_count
    tokens_retained = sum(estimate_tokens(m["content"]) for m in budgeted)
    first_retained = budgeted[0]["content"] if budgeted else None
    newest_retained = budgeted[-1]["content"] if budgeted else None
    configured_budget = 1200

    # 4. Report details
    print("\n" + "=" * 60)
    print("CONVERSATION HISTORY BUDGETING DIAGNOSTIC REPORT")
    print("=" * 60)
    print(f"Total messages supplied:   {total_supplied}")
    print(f"Retained messages:         {retained_count}")
    print(f"Discarded messages:        {discarded_count}")
    print(f"Estimated tokens retained: {tokens_retained}")
    print(f"Configured token budget:   {configured_budget}")
    print("-" * 60)
    print(f"First retained message:    {first_retained}")
    print(f"Newest retained message:   {newest_retained}")
    print("=" * 60)

    # 5. Verifications
    # Verification A: Newest message is retained
    expected_newest = created_messages[-1]["content"]
    assert newest_retained == expected_newest, (
        f"Verification FAILED: Newest message not retained! Expected: '{expected_newest}', Got: '{newest_retained}'"
    )
    print("[PASS] Verification 1: Newest message is correctly retained as the latest in history.")

    # Verification B: Tokens retained do not exceed configured budget
    assert tokens_retained <= configured_budget, (
        f"Verification FAILED: Tokens retained ({tokens_retained}) exceeds budget ({configured_budget})!"
    )
    print(f"[PASS] Verification 2: Retained tokens ({tokens_retained}) <= configured budget ({configured_budget}).")

    # Verification C: Correct chronological ordering (oldest retained -> newest retained)
    first_index_in_retained = created_messages[total_supplied - retained_count]["content"]
    assert first_retained == first_index_in_retained, (
        f"Verification FAILED: Chronological ordering mismatch."
    )
    print(f"[PASS] Verification 3: Correct chronological order preserved from message #{total_supplied - retained_count + 1} to #{total_supplied}.")

    # Cleanup test session
    clear_conversation(session_id)
    print("[INFO] Test session cleaned up successfully.")

if __name__ == "__main__":
    run_diagnostic()
