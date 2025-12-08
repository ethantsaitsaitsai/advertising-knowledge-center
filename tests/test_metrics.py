
import pandas as pd
from nodes.data_fusion import data_fusion_node
from schemas.state import AgentState

def test_metrics_calculation():
    # Mock State
    state = AgentState(
        messages=[],
        extracted_filters={},
        analysis_needs={
            "dimensions": ["Campaign_Name"],
            "metrics": ["CTR", "VTR", "ER"],
            "calculation_type": "Total"
        },
        sql_result=[
            {"cmpid": 1, "campaign_name": "Test Campaign", "budget": 1000}
        ],
        sql_result_columns=["cmpid", "campaign_name", "budget"],
        clickhouse_result=[
            {
                "cmpid": 1,
                "total_impressions": 1000,
                "effective_impressions": 500, # Mocking a different value to test independence
                "total_clicks": 20,
                "views_100": 200,
                "views_3s": 800,
                "total_engagements": 50
            }
        ]
    )

    # Run Node
    result = data_fusion_node(state)
    
    # Verify
    final_df_list = result["final_dataframe"]
    if not final_df_list:
        print("Error: No result returned")
        return

    row = final_df_list[0]
    print("Result Row:", row)

    # Assertions
    # CTR = 20 / 1000 = 2.0
    assert row['CTR'] == 2.0, f"Expected CTR 2.0, got {row.get('CTR')}"
    
    # VTR = 800 / 1000 = 80.0
    assert row['VTR'] == 80.0, f"Expected VTR 80.0, got {row.get('VTR')}"
    
    # ER = 50 / 1000 = 5.0
    assert row['ER'] == 5.0, f"Expected ER 5.0, got {row.get('ER')}"

    print("All tests passed!")

if __name__ == "__main__":
    test_metrics_calculation()
