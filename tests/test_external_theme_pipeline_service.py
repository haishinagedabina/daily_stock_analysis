from src.services.external_theme_pipeline_service import ExternalThemePipelineService
from src.services.theme_context_ingest_service import ExternalTheme, OpenClawThemeContext


def test_build_summary_orders_themes_and_counts_heat_buckets():
    service = ExternalThemePipelineService()
    context = OpenClawThemeContext(
        source="openclaw",
        trade_date="2026-03-27",
        market="cn",
        themes=[
            ExternalTheme(
                name="机器人",
                heat_score=72.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["机器人", "减速器"],
                evidence=[],
            ),
            ExternalTheme(
                name="AI芯片",
                heat_score=90.0,
                confidence=0.90,
                catalyst_summary="算力催化",
                keywords=["AI", "芯片", "算力"],
                evidence=[],
            ),
            ExternalTheme(
                name="创新药",
                heat_score=65.0,
                confidence=0.70,
                catalyst_summary="业绩催化",
                keywords=["创新药"],
                evidence=[],
            ),
        ],
        accepted_at="2026-03-27T15:00:00",
    )

    summary = service.build_summary(context)

    assert summary["source"] == "openclaw"
    assert summary["trade_date"] == "2026-03-27"
    assert summary["market"] == "cn"
    assert summary["accepted_theme_count"] == 3
    assert summary["hot_theme_count"] == 2
    assert summary["focus_theme_count"] == 1
    assert summary["top_theme_names"] == ["AI芯片", "机器人概念", "创新药"]
    assert summary["themes"][0]["name"] == "AI芯片"
    assert summary["themes"][0]["keyword_count"] == 3


def test_build_summary_returns_empty_theme_summary_when_no_themes():
    service = ExternalThemePipelineService()
    context = OpenClawThemeContext(
        source="openclaw",
        trade_date="2026-03-27",
        market="cn",
        themes=[],
        accepted_at="2026-03-27T15:00:00",
    )

    summary = service.build_summary(context)

    assert summary["accepted_theme_count"] == 0
    assert summary["hot_theme_count"] == 0
    assert summary["focus_theme_count"] == 0
    assert summary["top_theme_names"] == []
    assert summary["themes"] == []


def test_build_summary_normalizes_alias_theme_name():
    service = ExternalThemePipelineService()
    context = OpenClawThemeContext(
        source="openclaw",
        trade_date="2026-03-27",
        market="cn",
        themes=[
            ExternalTheme(
                name="算力芯片",
                heat_score=88.0,
                confidence=0.91,
                catalyst_summary="算力链催化",
                keywords=["算力", "芯片"],
                evidence=[],
            )
        ],
        accepted_at="2026-03-27T15:00:00",
    )

    summary = service.build_summary(context)

    assert summary["top_theme_names"] == ["AI芯片"]
    assert summary["themes"][0]["name"] == "AI芯片"
    assert summary["themes"][0]["normalized_name"] == "AI芯片"
    assert summary["themes"][0]["raw_name"] == "算力芯片"
    assert summary["themes"][0]["normalization_status"] == "high_confidence"


def test_build_summary_skips_empty_theme_name():
    service = ExternalThemePipelineService()
    context = OpenClawThemeContext(
        source="openclaw",
        trade_date="2026-03-27",
        market="cn",
        themes=[
            ExternalTheme(
                name="",
                heat_score=88.0,
                confidence=0.91,
                catalyst_summary="空名称",
                keywords=[],
                evidence=[],
            )
        ],
        accepted_at="2026-03-27T15:00:00",
    )

    summary = service.build_summary(context)

    assert summary["accepted_theme_count"] == 0
    assert summary["top_theme_names"] == []
    assert summary["themes"] == []
