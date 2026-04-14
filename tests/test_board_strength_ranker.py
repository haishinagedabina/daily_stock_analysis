from src.services.board_strength_ranker import BoardStrengthRanker


def test_ranker_orders_boards_by_relative_strength():
    ranker = BoardStrengthRanker()

    ranked = ranker.rank([
        {
            "board_name": "算力",
            "avg_pct_chg": 5.3,
            "median_pct": 4.8,
            "strong_stock_ratio_3pct": 0.75,
            "strong_stock_ratio_5pct": 0.50,
            "limit_up_count": 3,
            "limit_up_ratio": 0.30,
            "up_ratio": 0.90,
            "top3_avg": 7.5,
            "front_concentration": 0.74,
            "breadth_score": 0.76,
        },
        {
            "board_name": "机器人",
            "avg_pct_chg": 3.4,
            "median_pct": 3.0,
            "strong_stock_ratio_3pct": 0.50,
            "strong_stock_ratio_5pct": 0.20,
            "limit_up_count": 1,
            "limit_up_ratio": 0.10,
            "up_ratio": 0.70,
            "top3_avg": 5.0,
            "front_concentration": 0.58,
            "breadth_score": 0.60,
        },
        {
            "board_name": "银行",
            "avg_pct_chg": -0.5,
            "median_pct": -0.6,
            "strong_stock_ratio_3pct": 0.0,
            "strong_stock_ratio_5pct": 0.0,
            "limit_up_count": 0,
            "limit_up_ratio": 0.0,
            "up_ratio": 0.35,
            "top3_avg": 0.8,
            "front_concentration": 0.20,
            "breadth_score": 0.20,
        },
    ])

    assert [item["board_name"] for item in ranked] == ["算力", "机器人", "银行"]
    assert ranked[0]["status_bucket"] == "hot"
    assert ranked[-1]["status_bucket"] in {"neutral", "cold"}


def test_ranker_uses_secondary_metrics_to_break_ties():
    ranker = BoardStrengthRanker()

    ranked = ranker.rank([
        {
            "board_name": "A板块",
            "avg_pct_chg": 4.0,
            "median_pct": 4.0,
            "strong_stock_ratio_3pct": 0.5,
            "strong_stock_ratio_5pct": 0.2,
            "limit_up_count": 1,
            "limit_up_ratio": 0.1,
            "up_ratio": 0.8,
            "top3_avg": 5.0,
            "front_concentration": 0.4,
            "breadth_score": 0.6,
        },
        {
            "board_name": "B板块",
            "avg_pct_chg": 4.0,
            "median_pct": 4.0,
            "strong_stock_ratio_3pct": 0.5,
            "strong_stock_ratio_5pct": 0.2,
            "limit_up_count": 2,
            "limit_up_ratio": 0.2,
            "up_ratio": 0.8,
            "top3_avg": 5.0,
            "front_concentration": 0.4,
            "breadth_score": 0.6,
        },
    ])

    assert ranked[0]["board_name"] == "B板块"
    assert ranked[0]["board_strength_rank"] == 1


def test_ranker_respects_absolute_floor_when_only_one_board_exists():
    ranker = BoardStrengthRanker()

    ranked = ranker.rank([
        {
            "board_name": "冷门板块",
            "avg_pct_chg": -2.5,
            "median_pct": -2.0,
            "strong_stock_ratio_3pct": 0.0,
            "strong_stock_ratio_5pct": 0.0,
            "limit_up_count": 0,
            "limit_up_ratio": 0.0,
            "up_ratio": 0.10,
            "top3_avg": 0.5,
            "front_concentration": 0.1,
            "breadth_score": 0.1,
        },
    ])

    assert ranked[0]["board_strength_rank"] == 1
    assert ranked[0]["status_bucket"] in {"neutral", "cold"}
