from src.services.theme_pipeline_fusion_service import ThemePipelineFusionService


def test_merge_supports_external_only_pipeline():
    service = ThemePipelineFusionService()
    external_pipeline = {
        "trade_date": "2026-03-27",
        "market": "cn",
        "top_theme_names": ["AI芯片", "机器人"],
        "themes": [
            {
                "name": "AI芯片",
                "heat_score": 90.0,
                "confidence": 0.9,
                "keyword_count": 3,
            },
            {
                "name": "机器人",
                "heat_score": 72.0,
                "confidence": 0.85,
                "keyword_count": 2,
            },
        ],
    }

    fused = service.merge(local_pipeline=None, external_pipeline=external_pipeline)

    assert fused["trade_date"] == "2026-03-27"
    assert fused["market"] == "cn"
    assert fused["active_sources"] == ["external"]
    assert fused["selected_theme_names"] == ["AI芯片", "机器人"]
    assert fused["merged_theme_count"] == 2
    assert fused["merged_themes"][0]["name"] == "AI芯片"
    assert fused["merged_themes"][0]["source"] == "external"


def test_merge_returns_empty_result_when_no_sources_present():
    service = ThemePipelineFusionService()

    fused = service.merge(local_pipeline=None, external_pipeline=None)

    assert fused["trade_date"] is None
    assert fused["market"] is None
    assert fused["active_sources"] == []
    assert fused["selected_theme_names"] == []
    assert fused["merged_theme_count"] == 0
    assert fused["merged_themes"] == []


def test_merge_deduplicates_same_theme_and_prefers_local_fields():
    service = ThemePipelineFusionService()
    local_pipeline = {
        "trade_date": "2026-03-27",
        "market": "cn",
        "selected_theme_names": ["AI芯片", "机器人"],
        "themes": [
            {
                "name": "AI芯片",
                "heat_score": 88.0,
                "source_board": "AI芯片",
                "stock_count": 18,
            },
            {
                "name": "机器人",
                "heat_score": 76.0,
                "source_board": "机器人",
                "stock_count": 20,
            },
        ],
    }
    external_pipeline = {
        "trade_date": "2026-03-27",
        "market": "cn",
        "top_theme_names": ["AI芯片", "创新药"],
        "themes": [
            {
                "name": "AI芯片",
                "heat_score": 92.0,
                "confidence": 0.9,
                "keyword_count": 3,
            },
            {
                "name": "创新药",
                "heat_score": 72.0,
                "confidence": 0.82,
                "keyword_count": 2,
            },
        ],
    }

    fused = service.merge(local_pipeline=local_pipeline, external_pipeline=external_pipeline)

    assert fused["active_sources"] == ["local", "external"]
    assert fused["selected_theme_names"] == ["AI芯片", "机器人", "创新药"]
    assert fused["merged_theme_count"] == 3
    assert fused["merged_themes"][0]["name"] == "AI芯片"
    assert fused["merged_themes"][0]["source"] == "local"
    assert fused["merged_themes"][0]["matched_sources"] == ["local", "external"]
    assert fused["merged_themes"][0]["source_board"] == "AI芯片"
    assert fused["merged_themes"][0]["confidence"] == 0.9


def test_merge_deduplicates_alias_themes_by_normalized_name_and_tracks_raw_names():
    service = ThemePipelineFusionService()
    local_pipeline = {
        "trade_date": "2026-03-27",
        "market": "cn",
        "selected_theme_names": ["AI芯片"],
        "themes": [
            {
                "name": "AI芯片",
                "normalized_name": "AI芯片",
                "raw_name": "AI芯片",
                "heat_score": 88.0,
                "source_board": "AI芯片",
            }
        ],
    }
    external_pipeline = {
        "trade_date": "2026-03-27",
        "market": "cn",
        "top_theme_names": ["AI芯片"],
        "themes": [
            {
                "name": "AI芯片",
                "normalized_name": "AI芯片",
                "raw_name": "算力芯片",
                "heat_score": 92.0,
                "confidence": 0.9,
            }
        ],
    }

    fused = service.merge(local_pipeline=local_pipeline, external_pipeline=external_pipeline)

    assert fused["selected_theme_names"] == ["AI芯片"]
    assert fused["merged_theme_count"] == 1
    assert fused["merged_themes"][0]["name"] == "AI芯片"
    assert fused["merged_themes"][0]["normalized_name"] == "AI芯片"
    assert fused["merged_themes"][0]["raw_names"] == ["AI芯片", "算力芯片"]
    assert fused["merged_themes"][0]["priority_source"] == "local"
    assert fused["merged_themes"][0]["matched_sources"] == ["local", "external"]


def test_merge_prefers_local_trade_date_and_market_metadata():
    service = ThemePipelineFusionService()
    local_pipeline = {
        "trade_date": "2026-03-27",
        "market": "cn",
        "themes": [
            {
                "name": "AI芯片",
                "normalized_name": "AI芯片",
                "raw_name": "AI芯片",
            }
        ],
    }
    external_pipeline = {
        "trade_date": "2026-03-28",
        "market": "us",
        "themes": [
            {
                "name": "AI芯片",
                "normalized_name": "AI芯片",
                "raw_name": "算力芯片",
            }
        ],
    }

    fused = service.merge(local_pipeline=local_pipeline, external_pipeline=external_pipeline)

    assert fused["trade_date"] == "2026-03-27"
    assert fused["market"] == "cn"
