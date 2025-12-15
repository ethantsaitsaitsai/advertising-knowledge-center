#!/usr/bin/env python3
"""
Test script to verify the is_ambiguous clearing fix.
This script simulates the conversation flow that was previously broken:
1. User asks about "悠遊卡" (ambiguous)
2. System shows clarification options
3. User responds with entity + date
4. System should CLEAR is_ambiguous and execute query
"""

from langchain_core.messages import HumanMessage, AIMessage
from graph.graph import app
from dotenv import load_dotenv
from schemas.state import AgentState
import uuid

def test_is_ambiguous_clearing():
    """Test that is_ambiguous flag is cleared when user provides entities + date during clarification."""

    load_dotenv()

    state: AgentState = {
        "messages": [],
        "next": "IntentAnalyzer",
        "supervisor_instructions": "",
        "user_intent": None,
        "campaign_data": None,
        "performance_data": None,
        "extracted_filters": {},
        "analysis_needs": {},
        "clarification_pending": False,
    }

    thread_id = str(uuid.uuid4())

    print("=" * 80)
    print("TEST: is_ambiguous Clearing Fix")
    print("=" * 80)

    # Test 1: Ambiguous query
    print("\n[TEST 1] User asks ambiguous query: '悠遊卡 成效'")
    print("-" * 80)
    state["messages"] = [HumanMessage(content="悠遊卡 成效")]

    final_state = app.invoke(state, {"configurable": {"thread_id": thread_id}})
    state = final_state

    # Check if is_ambiguous was set
    if state.get("user_intent"):
        print(f"✓ user_intent.is_ambiguous = {state['user_intent'].is_ambiguous}")
        print(f"✓ user_intent.entities = {state['user_intent'].entities}")
        print(f"✓ user_intent.date_range = {state['user_intent'].date_range}")

        if state['user_intent'].is_ambiguous:
            print("✓ Correctly detected as ambiguous (as expected for first query)")

        if state["messages"]:
            last_msg = state["messages"][-1]
            print(f"✓ System response preview: {str(last_msg.content)[:150]}...")

    # Test 2: User provides clarification with entity + date
    print("\n[TEST 2] User provides clarification: '悠遊卡股份有限公司 2025年'")
    print("-" * 80)
    state["messages"].append(HumanMessage(content="悠遊卡股份有限公司 2025年"))
    state["clarification_pending"] = True  # Mark that we're in clarification context

    final_state = app.invoke(state, {"configurable": {"thread_id": thread_id}})
    state = final_state

    # Check if is_ambiguous was cleared
    if state.get("user_intent"):
        print(f"✓ user_intent.is_ambiguous = {state['user_intent'].is_ambiguous}")
        print(f"✓ user_intent.entities = {state['user_intent'].entities}")
        print(f"✓ user_intent.date_range = {state['user_intent'].date_range}")

        if not state['user_intent'].is_ambiguous:
            print("✅ SUCCESS: is_ambiguous WAS CLEARED (this is the fix!)")
        else:
            print("❌ FAILED: is_ambiguous was NOT cleared (fix not working)")

        if state["messages"]:
            last_msg = state["messages"][-1]
            print(f"✓ System response preview: {str(last_msg.content)[:150]}...")

            # Check that we're not seeing repeated clarification messages
            if "我需要您提供更多信息" in str(last_msg.content):
                print("⚠️  WARNING: Still seeing clarification message (should be executing query)")
            else:
                print("✓ Not showing repeated clarification message")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    test_is_ambiguous_clearing()
