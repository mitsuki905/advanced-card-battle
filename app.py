from flask import Flask, jsonify, request, render_template
import sqlite3
import json
import random
import os
from datetime import datetime

app = Flask(__name__)
DB_PATH = "game.db"


# ─────────────────────────────────────────
# DB 初期化
# ─────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    # 既存のゲーム状態テーブル（内部用）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS game_state (
            id            INTEGER PRIMARY KEY,
            player_hp     INTEGER,
            enemy_hp      INTEGER,
            player_block  INTEGER,
            energy        INTEGER,
            deck          TEXT,
            hand          TEXT,
            discard       TEXT,
            current_node  TEXT,
            phase         TEXT DEFAULT 'battle',
            reward_cards  TEXT DEFAULT '[]'
        )
    """)
    # 手動セーブテーブル
    conn.execute("""
        CREATE TABLE IF NOT EXISTS save_data (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT,
            player_hp     INTEGER,
            enemy_hp      INTEGER,
            player_block  INTEGER,
            energy        INTEGER,
            deck          TEXT,
            hand          TEXT,
            discard       TEXT,
            current_node  TEXT,
            phase         TEXT DEFAULT 'battle',
            reward_cards  TEXT DEFAULT '[]',
            created_at    TEXT
        )
    """)
    # 自動セーブテーブル
    conn.execute("""
        CREATE TABLE IF NOT EXISTS autosave (
            id            INTEGER PRIMARY KEY,
            player_hp     INTEGER,
            enemy_hp      INTEGER,
            player_block  INTEGER,
            energy        INTEGER,
            deck          TEXT,
            hand          TEXT,
            discard       TEXT,
            current_node  TEXT,
            phase         TEXT DEFAULT 'battle',
            reward_cards  TEXT DEFAULT '[]',
            updated_at    TEXT
        )
    """)
    # 既存テーブルへのカラム追加（マイグレーション）
    for table in ("game_state", "save_data", "autosave"):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN phase TEXT DEFAULT 'battle'")
        except Exception:
            pass
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN reward_cards TEXT DEFAULT '[]'")
        except Exception:
            pass
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# カード定義
# ─────────────────────────────────────────
CARD_DEFS = {
    "Strike":       {"cost": 1, "effect": "damage", "value": 6},
    "Defend":       {"cost": 1, "effect": "block",  "value": 5},
    "Draw":         {"cost": 1, "effect": "draw",   "value": 2},
    "Heavy Strike": {"cost": 2, "effect": "damage", "value": 10},
    "Bash":         {"cost": 2, "effect": "damage", "value": 8},
    "Iron Wave":    {"cost": 1, "effect": "damage_block", "value": 5},
    "Shrug It Off": {"cost": 1, "effect": "block",  "value": 8},
    "Pommel Strike":{"cost": 1, "effect": "damage_draw", "value": 9},
    "Twin Strike":  {"cost": 1, "effect": "damage2", "value": 5},
    "Armaments":    {"cost": 1, "effect": "block",  "value": 6},
}

INITIAL_DECK = (
    ["Strike"] * 5 +
    ["Defend"] * 4 +
    ["Draw"] * 1 +
    ["Heavy Strike"] * 1
)

# 報酬プール（初期デッキ以外のカード）
REWARD_POOL = [
    "Bash", "Iron Wave", "Shrug It Off", "Pommel Strike", "Twin Strike", "Armaments"
]


# ─────────────────────────────────────────
# マップ定義
# ─────────────────────────────────────────
MAP_NODES = [
    {"id": "n0", "type": "battle", "next": ["n1a", "n1b"]},
    {"id": "n1a", "type": "battle", "next": ["n2"]},
    {"id": "n1b", "type": "elite",  "next": ["n2"]},
    {"id": "n2",  "type": "rest",   "next": ["n3"]},
    {"id": "n3",  "type": "boss",   "next": []},
]

NODE_MAP = {n["id"]: n for n in MAP_NODES}

ENEMY_HP_TABLE = {
    "battle": 40,
    "elite":  60,
    "boss":   80,
}


# ─────────────────────────────────────────
# ゲーム状態ヘルパー
# ─────────────────────────────────────────
def load_state():
    conn = get_db()
    row = conn.execute("SELECT * FROM game_state WHERE id=1").fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "player_hp":    row["player_hp"],
        "enemy_hp":     row["enemy_hp"],
        "player_block": row["player_block"],
        "energy":       row["energy"],
        "deck":         json.loads(row["deck"]),
        "hand":         json.loads(row["hand"]),
        "discard":      json.loads(row["discard"]),
        "current_node": row["current_node"],
        "phase":        row["phase"] if row["phase"] else "battle",
        "reward_cards": json.loads(row["reward_cards"]) if row["reward_cards"] else [],
    }


def save_state(state):
    conn = get_db()
    conn.execute("DELETE FROM game_state WHERE id=1")
    conn.execute("""
        INSERT INTO game_state
            (id, player_hp, enemy_hp, player_block, energy, deck, hand, discard, current_node, phase, reward_cards)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        state["player_hp"],
        state["enemy_hp"],
        state["player_block"],
        state["energy"],
        json.dumps(state["deck"]),
        json.dumps(state["hand"]),
        json.dumps(state["discard"]),
        state["current_node"],
        state.get("phase", "battle"),
        json.dumps(state.get("reward_cards", [])),
    ))
    conn.commit()
    conn.close()


def state_to_row(state):
    return (
        state["player_hp"],
        state["enemy_hp"],
        state["player_block"],
        state["energy"],
        json.dumps(state["deck"]),
        json.dumps(state["hand"]),
        json.dumps(state["discard"]),
        state["current_node"],
        state.get("phase", "battle"),
        json.dumps(state.get("reward_cards", [])),
    )


def row_to_state(row):
    return {
        "player_hp":    row["player_hp"],
        "enemy_hp":     row["enemy_hp"],
        "player_block": row["player_block"],
        "energy":       row["energy"],
        "deck":         json.loads(row["deck"]),
        "hand":         json.loads(row["hand"]),
        "discard":      json.loads(row["discard"]),
        "current_node": row["current_node"],
        "phase":        row["phase"] if row["phase"] else "battle",
        "reward_cards": json.loads(row["reward_cards"]) if row["reward_cards"] else [],
    }


def draw_cards(state, n=1):
    """山札から n 枚ドロー（山札が空なら捨て札をシャッフルして補充）"""
    for _ in range(n):
        if not state["deck"]:
            if not state["discard"]:
                break
            state["deck"] = state["discard"][:]
            random.shuffle(state["deck"])
            state["discard"] = []
        if state["deck"]:
            state["hand"].append(state["deck"].pop(0))


def enemy_attack(state):
    """敵の攻撃（固定6ダメージ、ブロックで軽減）"""
    dmg = 6
    absorbed = min(state["player_block"], dmg)
    state["player_block"] = max(0, state["player_block"] - dmg)
    state["player_hp"] = max(0, state["player_hp"] - max(0, dmg - absorbed))


def node_info(node_id):
    return NODE_MAP.get(node_id)


def available_next_nodes(current_node_id):
    node = node_info(current_node_id)
    if node is None:
        return []
    return [NODE_MAP[nid] for nid in node["next"] if nid in NODE_MAP]


def generate_reward_cards():
    """報酬カードを3枚ランダムに選出"""
    pool = REWARD_POOL[:]
    random.shuffle(pool)
    return pool[:3]


# ─────────────────────────────────────────
# ゲーム状態の付加情報
# ─────────────────────────────────────────
def enrich_state(state):
    """フロントエンドに返す際に付加情報を追加"""
    node = node_info(state["current_node"])
    next_nodes = available_next_nodes(state["current_node"])
    in_battle = node["type"] in ("battle", "elite", "boss") if node else False

    result = dict(state)
    result["current_node_type"] = node["type"] if node else None
    result["next_nodes"] = [{"id": n["id"], "type": n["type"]} for n in next_nodes]
    result["in_battle"] = in_battle
    result["game_over"] = state["player_hp"] <= 0
    result["game_clear"] = (
        node is not None and
        node["type"] == "boss" and
        state["enemy_hp"] <= 0
    )
    # カード定義も付与
    result["card_defs"] = CARD_DEFS
    return result


# ─────────────────────────────────────────
# ルーティング
# ─────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start():
    deck = INITIAL_DECK[:]
    random.shuffle(deck)
    state = {
        "player_hp":    50,
        "enemy_hp":     0,
        "player_block": 0,
        "energy":       3,
        "deck":         deck,
        "hand":         [],
        "discard":      [],
        "current_node": "n0",
        "phase":        "battle",
        "reward_cards": [],
    }
    # 最初のノードが戦闘なら敵HPをセット
    node = node_info("n0")
    if node and node["type"] in ENEMY_HP_TABLE:
        state["enemy_hp"] = ENEMY_HP_TABLE[node["type"]]
        # ターン開始処理
        state["energy"] = 3
        state["player_block"] = 0
        draw_cards(state, 5)

    save_state(state)
    return jsonify(enrich_state(state))


@app.route("/state", methods=["GET"])
def get_state():
    state = load_state()
    if state is None:
        return jsonify({"error": "No game in progress"}), 404
    return jsonify(enrich_state(state))


@app.route("/action/card", methods=["POST"])
def use_card():
    data = request.get_json()
    card_name = data.get("card")
    state = load_state()
    if state is None:
        return jsonify({"error": "No game in progress"}), 404

    node = node_info(state["current_node"])
    if node is None or node["type"] not in ("battle", "elite", "boss"):
        return jsonify({"error": "Not in battle"}), 400

    if card_name not in state["hand"]:
        return jsonify({"error": "Card not in hand"}), 400

    card = CARD_DEFS.get(card_name)
    if card is None:
        return jsonify({"error": "Unknown card"}), 400

    if state["energy"] < card["cost"]:
        return jsonify({"error": "Not enough energy"}), 400

    # カード効果適用
    state["energy"] -= card["cost"]
    effect = card["effect"]
    value = card["value"]

    log = ""
    if effect == "damage":
        actual = max(0, value)
        state["enemy_hp"] = max(0, state["enemy_hp"] - actual)
        log = f"{card_name} で {actual} ダメージ！"
    elif effect == "block":
        state["player_block"] += value
        log = f"{card_name} でブロック +{value}！"
    elif effect == "draw":
        draw_cards(state, value)
        log = f"{card_name} で {value} 枚ドロー！"
    elif effect == "damage_block":
        # ダメージ＋ブロック両方
        state["enemy_hp"] = max(0, state["enemy_hp"] - value)
        state["player_block"] += value
        log = f"{card_name} で {value} ダメージ＆ブロック +{value}！"
    elif effect == "damage_draw":
        # ダメージ＋ドロー
        state["enemy_hp"] = max(0, state["enemy_hp"] - value)
        draw_cards(state, 1)
        log = f"{card_name} で {value} ダメージ＆1枚ドロー！"
    elif effect == "damage2":
        # 2回攻撃
        total = value * 2
        state["enemy_hp"] = max(0, state["enemy_hp"] - total)
        log = f"{card_name} で {value}×2 = {total} ダメージ！"

    # 手札から捨て札へ
    state["hand"].remove(card_name)
    state["discard"].append(card_name)

    save_state(state)
    enriched = enrich_state(state)
    enriched["log"] = log
    return jsonify(enriched)


@app.route("/action/end_turn", methods=["POST"])
def end_turn():
    state = load_state()
    if state is None:
        return jsonify({"error": "No game in progress"}), 404

    node = node_info(state["current_node"])
    if node is None or node["type"] not in ("battle", "elite", "boss"):
        return jsonify({"error": "Not in battle"}), 400

    # 手札を全て捨て札へ
    state["discard"].extend(state["hand"])
    state["hand"] = []

    # ブロックリセット
    state["player_block"] = 0

    # 敵行動
    log = ""
    if state["enemy_hp"] > 0:
        enemy_attack(state)
        log = "敵が 6 ダメージ攻撃！"

    # 勝敗チェック
    if state["player_hp"] <= 0:
        save_state(state)
        enriched = enrich_state(state)
        enriched["log"] = log + " ゲームオーバー..."
        return jsonify(enriched)

    if state["enemy_hp"] <= 0:
        # 戦闘勝利 → 報酬フェーズへ
        reward_cards = generate_reward_cards()
        state["phase"] = "reward"
        state["reward_cards"] = reward_cards
        save_state(state)
        enriched = enrich_state(state)
        enriched["log"] = log + " 敵を倒した！カードを選択してください。"
        return jsonify(enriched)

    # 次のプレイヤーターン開始
    state["energy"] = 3
    draw_cards(state, 5)

    save_state(state)
    enriched = enrich_state(state)
    enriched["log"] = log + " 次のターン開始！"
    return jsonify(enriched)


@app.route("/map/select", methods=["POST"])
def map_select():
    data = request.get_json()
    node_id = data.get("node_id")
    state = load_state()
    if state is None:
        return jsonify({"error": "No game in progress"}), 404

    # 報酬フェーズ中は移動不可
    if state.get("phase") == "reward":
        return jsonify({"error": "Please select a reward card first"}), 400

    # 現在ノードの敵が生きていたら移動不可
    current = node_info(state["current_node"])
    if current and current["type"] in ("battle", "elite", "boss") and state["enemy_hp"] > 0:
        return jsonify({"error": "Battle not finished"}), 400

    next_nodes = available_next_nodes(state["current_node"])
    next_ids = [n["id"] for n in next_nodes]
    if node_id not in next_ids:
        return jsonify({"error": "Invalid node selection"}), 400

    state["current_node"] = node_id
    node = node_info(node_id)

    log = ""
    if node["type"] == "rest":
        state["player_hp"] = min(50, state["player_hp"] + 15)
        log = "休憩！HP +15 回復。"
        state["enemy_hp"] = 0
        state["phase"] = "map"
    elif node["type"] in ENEMY_HP_TABLE:
        state["enemy_hp"] = ENEMY_HP_TABLE[node["type"]]
        state["energy"] = 3
        state["player_block"] = 0
        state["discard"].extend(state["hand"])
        state["hand"] = []
        draw_cards(state, 5)
        state["phase"] = "battle"
        log = f"{node['type']} との戦闘開始！"

    state["reward_cards"] = []
    save_state(state)
    enriched = enrich_state(state)
    enriched["log"] = log
    return jsonify(enriched)


# ─────────────────────────────────────────
# 報酬選択
# ─────────────────────────────────────────
@app.route("/reward/select", methods=["POST"])
def reward_select():
    data = request.get_json()
    card_name = data.get("card")
    state = load_state()
    if state is None:
        return jsonify({"error": "No game in progress"}), 404

    if state.get("phase") != "reward":
        return jsonify({"error": "Not in reward phase"}), 400

    # スキップ対応
    if card_name == "__skip__":
        state["phase"] = "map"
        state["reward_cards"] = []
        save_state(state)
        enriched = enrich_state(state)
        enriched["log"] = "カード報酬をスキップしました。マップへ戻ります。"
        return jsonify(enriched)

    if card_name not in state.get("reward_cards", []):
        return jsonify({"error": "Invalid card selection"}), 400

    # カードをデッキに追加
    state["deck"].append(card_name)
    state["phase"] = "map"
    state["reward_cards"] = []

    save_state(state)
    enriched = enrich_state(state)
    enriched["log"] = f"「{card_name}」をデッキに追加しました！マップへ戻ります。"
    return jsonify(enriched)


# ─────────────────────────────────────────
# セーブ / ロード
# ─────────────────────────────────────────
@app.route("/save", methods=["POST"])
def manual_save():
    data = request.get_json()
    save_name = data.get("name", "セーブデータ")
    state = load_state()
    if state is None:
        return jsonify({"error": "No game in progress"}), 404

    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO save_data
            (name, player_hp, enemy_hp, player_block, energy, deck, hand, discard, current_node, phase, reward_cards, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (save_name,) + state_to_row(state) + (now,))
    conn.commit()
    conn.close()
    return jsonify({"message": f"「{save_name}」にセーブしました。", "saved_at": now})


@app.route("/save/list", methods=["GET"])
def save_list():
    conn = get_db()
    rows = conn.execute("SELECT id, name, created_at, player_hp, current_node FROM save_data ORDER BY created_at DESC").fetchall()
    conn.close()
    saves = [{"id": r["id"], "name": r["name"], "created_at": r["created_at"],
              "player_hp": r["player_hp"], "current_node": r["current_node"]} for r in rows]
    return jsonify({"saves": saves})


@app.route("/load", methods=["POST"])
def load_save():
    data = request.get_json()
    save_id = data.get("id")
    conn = get_db()
    row = conn.execute("SELECT * FROM save_data WHERE id=?", (save_id,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "Save not found"}), 404

    state = row_to_state(row)
    save_state(state)
    enriched = enrich_state(state)
    enriched["log"] = f"「{row['name']}」をロードしました。"
    return jsonify(enriched)


@app.route("/autosave", methods=["POST"])
def autosave():
    state = load_state()
    if state is None:
        return jsonify({"error": "No game in progress"}), 404

    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM autosave WHERE id=1")
    conn.execute("""
        INSERT INTO autosave
            (id, player_hp, enemy_hp, player_block, energy, deck, hand, discard, current_node, phase, reward_cards, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, state_to_row(state) + (now,))
    conn.commit()
    conn.close()
    return jsonify({"message": "自動セーブしました。", "updated_at": now})


@app.route("/autosave/load", methods=["POST"])
def autosave_load():
    conn = get_db()
    row = conn.execute("SELECT * FROM autosave WHERE id=1").fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "No autosave found"}), 404

    state = row_to_state(row)
    save_state(state)
    enriched = enrich_state(state)
    enriched["log"] = f"自動セーブ（{row['updated_at']}）からロードしました。"
    return jsonify(enriched)


@app.route("/autosave/info", methods=["GET"])
def autosave_info():
    conn = get_db()
    row = conn.execute("SELECT id, updated_at, player_hp, current_node FROM autosave WHERE id=1").fetchone()
    conn.close()
    if row is None:
        return jsonify({"autosave": None})
    return jsonify({"autosave": {
        "updated_at": row["updated_at"],
        "player_hp": row["player_hp"],
        "current_node": row["current_node"],
    }})


# ─────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
