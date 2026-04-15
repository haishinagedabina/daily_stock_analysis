import sqlite3, sys, json

conn = sqlite3.connect(r'E:\daily_stock_analysis\data\stock_analysis.db')
cursor = conn.cursor()

# All runs summary
print("ALL SCREENING RUNS:")
cursor.execute("""
    SELECT r.run_id, r.trade_date, r.status, r.universe_size, r.candidate_count, r.ai_top_k,
           COUNT(c.id) as actual_candidates,
           GROUP_CONCAT(DISTINCT c.code) as codes
    FROM screening_runs r
    LEFT JOIN screening_candidates c ON r.run_id = c.run_id
    GROUP BY r.run_id
    ORDER BY r.trade_date DESC
""")
cols = [desc[0] for desc in cursor.description]
for row in cursor.fetchall():
    d = dict(zip(cols, row))
    print(f"  {d['trade_date']} | candidates={d['actual_candidates']} | codes={d['codes']}")
sys.stdout.flush()

# Strategy hit distribution across all candidates  
print("\nSTRATEGY HIT DISTRIBUTION:")
cursor.execute("SELECT matched_strategies_json FROM screening_candidates")
from collections import Counter
strat_counter = Counter()
for (ms_json,) in cursor.fetchall():
    if ms_json:
        strategies = json.loads(ms_json)
        for s in strategies:
            strat_counter[s] += 1
for s, cnt in strat_counter.most_common():
    print(f"  {s}: {cnt} times")
sys.stdout.flush()

# Candidates with big yin candle (当日大阴线但仍入选)
print("\nCANDIDATES WITH BIG_YIN CANDLE (bearish day but still selected):")
cursor.execute("SELECT code, name, rule_score, factor_snapshot_json FROM screening_candidates")
for code, name, score, fs_json in cursor.fetchall():
    if fs_json:
        fs = json.loads(fs_json)
        if fs.get('candle_pattern') == 'big_yin':
            print(f"  {code} {name} score={score} pct_chg={fs.get('pct_chg')} close_strength={fs.get('close_strength')}")
sys.stdout.flush()

# Candidates with extreme ma5_distance_pct (far from MA5)
print("\nCANDIDATES WITH MA5 DISTANCE > 10% (追高风险):")
cursor.execute("SELECT code, name, rule_score, factor_snapshot_json, matched_strategies_json FROM screening_candidates")
for code, name, score, fs_json, ms_json in cursor.fetchall():
    if fs_json:
        fs = json.loads(fs_json)
        ma5_dist = fs.get('ma5_distance_pct', 0)
        if ma5_dist and ma5_dist > 10:
            print(f"  {code} {name} score={score:.1f} ma5_dist={ma5_dist:.1f}% pct_chg={fs.get('pct_chg'):.1f}% strategies={ms_json}")
sys.stdout.flush()

# AI review results summary
print("\nAI REVIEW SUMMARY:")
cursor.execute("""
    SELECT ai_operation_advice, COUNT(*) as cnt
    FROM screening_candidates
    WHERE ai_operation_advice IS NOT NULL
    GROUP BY ai_operation_advice
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}")
sys.stdout.flush()

# Count candidates with is_limit_up = true
print("\nLIMIT UP CANDIDATES (涨停入选):")
cursor.execute("SELECT code, name, rule_score, factor_snapshot_json FROM screening_candidates")
limit_up_count = 0
for code, name, score, fs_json in cursor.fetchall():
    if fs_json:
        fs = json.loads(fs_json)
        if fs.get('is_limit_up'):
            limit_up_count += 1
            print(f"  {code} {name} score={score:.1f} pct_chg={fs.get('pct_chg'):.1f}%")
print(f"  Total limit-up candidates: {limit_up_count}")
sys.stdout.flush()

# unique codes across all runs
print("\nUNIQUE STOCKS EVER SELECTED:")
cursor.execute("SELECT DISTINCT code, name FROM screening_candidates ORDER BY code")
for code, name in cursor.fetchall():
    print(f"  {code} {name}")
sys.stdout.flush()

conn.close()
