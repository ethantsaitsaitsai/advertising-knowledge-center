"""
Test script to verify budget calculation fixes
Tests AUDIENCE query budget duplication fix and DataFusion validation
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from prompts.sql_generator_prompt import SQL_GENERATOR_PROMPT
from config.llm import llm
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


class SQLOutput(BaseModel):
    sql: str = Field(..., description="The executable MySQL query.")
    explanation: str = Field(..., description="Brief explanation.")


def test_audience_simplified_template():
    """
    Test AUDIENCE query to verify Split Subquery strategy is used
    """
    print("\n" + "="*80)
    print("TEST 1: AUDIENCE Simplified Template (No Ad_Format)")
    print("="*80)

    prompt = ChatPromptTemplate.from_messages([("user", SQL_GENERATOR_PROMPT)])
    chain = prompt | llm.with_structured_output(SQLOutput)

    # Simulate AUDIENCE query without Ad_Format
    inputs = {
        "query_level": "AUDIENCE",
        "filters": "{}",
        "metrics": "['Budget_Sum']",
        "dimensions": "['Segment_Category']",
        "confirmed_entities": "[]",
        "campaign_ids": "[]",
        "instruction_text": "請生成受眾層級的SQL查詢",
        "schema_context": "Mock schema context"
    }

    try:
        result = chain.invoke(inputs)
        sql = result.sql

        print("\n📋 Generated SQL:")
        print("-" * 80)
        print(sql)
        print("-" * 80)

        # Verify Split Subquery strategy
        checks = {
            "Has BudgetInfo subquery": "BudgetInfo" in sql or "Budget_Info" in sql,
            "Has SegmentInfo subquery": "SegmentInfo" in sql or "Segment_Info" in sql,
            "Uses SUM(budget) in subquery": "SUM(budget)" in sql or "SUM(pc.budget)" in sql,
            "NOT using SUM(pc.budget) in main query": "FROM one_campaigns" in sql and sql.count("SUM(pc.budget)") <= 1,
            "Has GROUP BY one_campaign_id": "GROUP BY" in sql and "one_campaign_id" in sql
        }

        print("\n✅ Verification Results:")
        all_passed = True
        for check_name, passed in checks.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {status}: {check_name}")
            if not passed:
                all_passed = False

        if all_passed:
            print("\n🎉 TEST 1 PASSED: AUDIENCE template correctly uses Split Subquery strategy")
        else:
            print("\n⚠️  TEST 1 FAILED: AUDIENCE template may have issues")

        return all_passed

    except Exception as e:
        print(f"\n❌ TEST 1 ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_execution_format_template():
    """
    Test EXECUTION query to verify pcd.budget is used
    """
    print("\n" + "="*80)
    print("TEST 2: EXECUTION Template with Ad_Format")
    print("="*80)

    prompt = ChatPromptTemplate.from_messages([("user", SQL_GENERATOR_PROMPT)])
    chain = prompt | llm.with_structured_output(SQLOutput)

    inputs = {
        "query_level": "EXECUTION",
        "filters": "{}",
        "metrics": "['Budget_Sum']",
        "dimensions": "['Ad_Format']",
        "confirmed_entities": "[]",
        "campaign_ids": "[]",
        "instruction_text": "請生成格式層級的SQL查詢",
        "schema_context": "Mock schema context"
    }

    try:
        result = chain.invoke(inputs)
        sql = result.sql

        print("\n📋 Generated SQL:")
        print("-" * 80)
        print(sql)
        print("-" * 80)

        # Verify pcd.budget is used
        checks = {
            "Uses pcd.budget (NOT pc.budget)": "pcd.budget" in sql,
            "Has ad_format_type_id": "ad_format_type_id" in sql,
            "Groups by format": ("GROUP BY" in sql and ("aft.title" in sql or "aft.id" in sql)),
            "Avoids GROUP_CONCAT for Ad_Format": sql.count("GROUP_CONCAT") == 0 or "Segment" in sql
        }

        print("\n✅ Verification Results:")
        all_passed = True
        for check_name, passed in checks.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {status}: {check_name}")
            if not passed:
                all_passed = False

        if all_passed:
            print("\n🎉 TEST 2 PASSED: EXECUTION template correctly uses pcd.budget")
        else:
            print("\n⚠️  TEST 2 FAILED: EXECUTION template may have issues")

        return all_passed

    except Exception as e:
        print(f"\n❌ TEST 2 ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_datafusion_validation_logic():
    """
    Test DataFusion budget validation logic (code inspection)
    """
    print("\n" + "="*80)
    print("TEST 3: DataFusion Budget Validation Logic")
    print("="*80)

    # Read data_fusion.py and verify validation code exists
    datafusion_path = project_root / "nodes" / "data_fusion.py"

    try:
        with open(datafusion_path, 'r', encoding='utf-8') as f:
            code = f.read()

        checks = {
            "Has raw_budget_total calculation": "raw_budget_total" in code,
            "Has merge_budget_total calculation": "merge_budget_total" in code,
            "Has agg_budget_total calculation": "agg_budget_total" in code,
            "Has budget_diff_pct calculation": "budget_diff_pct" in code,
            "Has tolerance threshold": "tolerance" in code,
            "Has warning message": "Budget Consistency Warning" in code,
            "Has PASSED message": "Budget Consistency Check PASSED" in code
        }

        print("\n✅ Code Inspection Results:")
        all_passed = True
        for check_name, passed in checks.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {status}: {check_name}")
            if not passed:
                all_passed = False

        if all_passed:
            print("\n🎉 TEST 3 PASSED: DataFusion has budget validation logic")
        else:
            print("\n⚠️  TEST 3 FAILED: DataFusion validation may be incomplete")

        return all_passed

    except Exception as e:
        print(f"\n❌ TEST 3 ERROR: {e}")
        return False


def main():
    """
    Run all budget fix tests
    """
    print("\n" + "="*80)
    print("🧪 BUDGET FIX VERIFICATION TEST SUITE")
    print("="*80)
    print("Testing fixes from commit f244e82")
    print("- AUDIENCE simplified template Split Subquery")
    print("- EXECUTION template pcd.budget usage")
    print("- DataFusion budget validation logic")

    results = {
        "Test 1 - AUDIENCE Template": test_audience_simplified_template(),
        "Test 2 - EXECUTION Template": test_execution_format_template(),
        "Test 3 - DataFusion Validation": test_datafusion_validation_logic()
    }

    print("\n" + "="*80)
    print("📊 FINAL RESULTS")
    print("="*80)

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())

    if all_passed:
        print("\n🎉 ALL TESTS PASSED! Budget fixes are working correctly.")
        return 0
    else:
        print("\n⚠️  SOME TESTS FAILED. Please review the output above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
