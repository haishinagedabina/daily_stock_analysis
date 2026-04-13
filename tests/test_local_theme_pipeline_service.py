from src.services.local_theme_pipeline_service import LocalThemePipelineService


def test_build_summary_extracts_hot_and_warm_local_themes():
    service = LocalThemePipelineService()
    decision_context = {
        "sector_heat_results": [
            {
                "board_name": "AI芯片",
                "canonical_theme": "AI芯片",
                "sector_hot_score": 92.0,
                "sector_status": "hot",
                "sector_stage": "main_rise",
                "stock_count": 18,
                "up_count": 12,
                "limit_up_count": 3,
            },
            {
                "board_name": "机器人",
                "canonical_theme": "机器人",
                "sector_hot_score": 76.0,
                "sector_status": "warm",
                "sector_stage": "expand",
                "stock_count": 20,
                "up_count": 10,
                "limit_up_count": 1,
            },
            {
                "board_name": "银行",
                "canonical_theme": "银行",
                "sector_hot_score": 40.0,
                "sector_status": "neutral",
                "sector_stage": "idle",
                "stock_count": 30,
                "up_count": 5,
                "limit_up_count": 0,
            },
        ],
        "hot_theme_count": 1,
        "warm_theme_count": 1,
    }

    summary = service.build_summary(
        trade_date="2026-03-27",
        market="cn",
        decision_context=decision_context,
    )

    assert summary["source"] == "local"
    assert summary["trade_date"] == "2026-03-27"
    assert summary["market"] == "cn"
    assert summary["hot_theme_count"] == 1
    assert summary["warm_theme_count"] == 1
    assert summary["selected_theme_names"] == ["AI芯片", "机器人概念"]
    assert summary["themes"][0]["name"] == "AI芯片"
    assert summary["themes"][0]["source_board"] == "AI芯片"


def test_build_summary_returns_empty_when_no_sector_results():
    service = LocalThemePipelineService()

    summary = service.build_summary(
        trade_date="2026-03-27",
        market="cn",
        decision_context={},
    )

    assert summary["source"] == "local"
    assert summary["selected_theme_names"] == []
    assert summary["themes"] == []


def test_build_summary_normalizes_local_theme_name_with_alias_mapping():
    service = LocalThemePipelineService()
    decision_context = {
        "sector_heat_results": [
            {
                "board_name": "机器人",
                "canonical_theme": "机器人",
                "sector_hot_score": 78.0,
                "sector_status": "warm",
                "sector_stage": "expand",
                "stock_count": 15,
                "up_count": 8,
                "limit_up_count": 1,
            }
        ],
        "hot_theme_count": 0,
        "warm_theme_count": 1,
    }

    summary = service.build_summary(
        trade_date="2026-03-27",
        market="cn",
        decision_context=decision_context,
    )

    assert summary["selected_theme_names"] == ["机器人概念"]
    assert summary["themes"][0]["name"] == "机器人概念"
    assert summary["themes"][0]["normalized_name"] == "机器人概念"
    assert summary["themes"][0]["raw_name"] == "机器人"
    assert summary["themes"][0]["normalization_status"] == "high_confidence"
