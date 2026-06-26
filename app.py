from flask import Flask, jsonify, request, render_template
import sqlite3
import json
import random
import os

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
            current_node  TEXT
        )
    """)
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
}

INITIAL_DECK = (
    ["Strike"] * 5 +
    ["Defend"] * 4 +
    ["Draw"] * 1 +
    ["Heavy Strike"] * 1
)


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
    }


def save_state(state):
    conn = get_db()
    conn.execute("DELETE FROM game_state WHERE id=1")
    conn.execute("""
        INSERT INTO game_state
            (id, player_hp, enemy_hp, player_block, energy, deck, hand, discard, current_node)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        state["player_hp"],
        state["enemy_hp"],
        state["player_block"],
        state["energy"],
        json.dumps(state["deck"]),
        json.dumps(state["hand"]),
        json.dumps(state["discard"]),
        state["current_node"],
    ))
    conn.commit()
    conn.close()


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
        actual = max(0, value - 0)  # 敵ブロックは今回なし
        state["enemy_hp"] = max(0, state["enemy_hp"] - actual)
        log = f"{card_name} で {actual} ダメージ！"
    elif effect == "block":
        state["player_block"] += value
        log = f"{card_name} でブロック +{value}！"
    elif effect == "draw":
        draw_cards(state, value)
        log = f"{card_name} で {value} 枚ドロー！"

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
        save_state(state)
        enriched = enrich_state(state)
        enriched["log"] = log + " 敵を倒した！"
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
        # 休憩ノードは戦闘なし
        state["enemy_hp"] = 0
    elif node["type"] in ENEMY_HP_TABLE:
        state["enemy_hp"] = ENEMY_HP_TABLE[node["type"]]
        # ターン開始
        state["energy"] = 3
        state["player_block"] = 0
        state["discard"].extend(state["hand"])
        state["hand"] = []
        draw_cards(state, 5)
        log = f"{node['type']} との戦闘開始！"

    save_state(state)
    enriched = enrich_state(state)
    enriched["log"] = log
    return jsonify(enriched)


# ─────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
