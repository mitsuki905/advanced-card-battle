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
            game_mode     TEXT DEFAULT 'battle',
            reward_cards  TEXT DEFAULT '[]',
            enemy_intent  TEXT DEFAULT 'attack'
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
            game_mode     TEXT DEFAULT 'battle',
            reward_cards  TEXT DEFAULT '[]',
            enemy_intent  TEXT DEFAULT 'attack',
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
            game_mode     TEXT DEFAULT 'battle',
            reward_cards  TEXT DEFAULT '[]',
            enemy_intent  TEXT DEFAULT 'attack',
            updated_at    TEXT
        )
    """)
    # マイグレーション：旧 phase カラムを game_mode として扱う
    for table in ("game_state", "save_data", "autosave"):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN game_mode TEXT DEFAULT 'battle'")
        except Exception:
            pass
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN reward_cards TEXT DEFAULT '[]'")
        except Exception:
            pass
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN enemy_intent TEXT DEFAULT 'attack'")
        except Exception:
            pass
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN enemy_status TEXT DEFAULT '{{}}'")
        except Exception:
            pass
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN player_status TEXT DEFAULT '{{}}'")
        except Exception:
            pass
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN reward_type TEXT DEFAULT 'battle'")
        except Exception:
            pass
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN enemy_block INTEGER DEFAULT 0")
        except Exception:
            pass
        # 旧 phase カラムのデータを game_mode へ移行
        try:
            conn.execute(f"UPDATE {table} SET game_mode = phase WHERE game_mode IS NULL OR game_mode = ''")
        except Exception:
            pass
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# カード定義
# ─────────────────────────────────────────
CARD_DEFS = {

    # ───── 基本カード（序盤の基準） ─────
    "Strike":        {"cost": 1, "effect": "damage", "value": 6,  "rarity": "starter"},
    "Defend":        {"cost": 1, "effect": "block",  "value": 5,  "rarity": "starter"},
    "Draw":          {"cost": 1, "effect": "draw",   "value": 2,  "rarity": "starter"},
    "Heavy Strike":  {"cost": 2, "effect": "damage", "value": 10, "rarity": "starter"},

    # ───── コモン（安定カード） ─────
    # シンプルで扱いやすく、デッキの土台になる
    "Bash":          {"cost": 2, "effect": "damage",       "value": 8, "rarity": "common"},
    "Iron Wave":     {"cost": 1, "effect": "damage_block", "value": 5, "rarity": "common"},
    "Shrug It Off":  {"cost": 1, "effect": "block",        "value": 7, "rarity": "common"},
    "Jab":           {"cost": 0, "effect": "damage",       "value": 3, "rarity": "common"},
    "Brace":         {"cost": 0, "effect": "block",        "value": 3, "rarity": "common"},

    # ───── アンコモン（戦略カード） ─────
    # シナジーや状態異常を使って戦い方を広げる
    "Pommel Strike": {"cost": 1, "effect": "damage_draw",  "value": 8, "rarity": "uncommon"},
    "Twin Strike":   {"cost": 1, "effect": "damage2",      "value": 4, "rarity": "uncommon"},
    "Armaments":     {"cost": 1, "effect": "block",        "value": 7, "rarity": "uncommon"},

    # 毒ビルド用（ターン経過でダメージを伸ばす）
    "Poison Strike": {"cost": 1, "effect": "poison",       "value": 5, "rarity": "uncommon"},
    "Toxic Blow":    {"cost": 2, "effect": "damage_poison","value": 6, "rarity": "uncommon"},

    # 弱体ビルド用（敵の攻撃を抑える）
    "Weak Strike":   {"cost": 1, "effect": "weak",         "value": 2, "rarity": "uncommon"},
    "Weakening Hit": {"cost": 2, "effect": "damage_weak",  "value": 6, "rarity": "uncommon"},

    # ───── レア（ビルドの中心） ─────
    # 強力でゲームの方向性を決めるカード

    # 高火力系
    "Pummel":            {"cost": 3, "effect": "damage",      "value": 16, "rarity": "rare"},
    "Execution":         {"cost": 2, "effect": "damage",      "value": 16, "rarity": "rare"},

    # 防御特化
    "Fortress":          {"cost": 2, "effect": "block",       "value": 12, "rarity": "rare"},
    "Absolute Guard":    {"cost": 1, "effect": "block",       "value": 12, "rarity": "rare"},

    # リソース操作
    "Recharge":          {"cost": 1, "effect": "energy",      "value": 1,  "rarity": "rare"},
    "Overdrive":         {"cost": 0, "effect": "energy",      "value": 2,  "rarity": "rare"},
    "Deep Focus":        {"cost": 0, "effect": "draw",        "value": 3,  "rarity": "rare"},

    # 状態異常ビルド強化
    "Neurotoxin":        {"cost": 1, "effect": "poison",      "value": 8,  "rarity": "rare"},
    "Predator Strike":   {"cost": 1, "effect": "damage_draw", "value": 7,  "rarity": "rare"},
}

# ─────────────────────────────────────────
# 初期デッキ
# ─────────────────────────────────────────
INITIAL_DECK = (
    ["Strike"] * 5 +
    ["Defend"] * 4 +
    ["Draw"] * 1 +
    ["Heavy Strike"] * 1
)

# ─────────────────────────────────────────
# 報酬プール（バランス調整版）
# ─────────────────────────────────────────

# コモン（安定枠）
COMMON_REWARD_POOL = [
    "Bash",
    "Iron Wave",
    "Shrug It Off",
    "Jab",
    "Brace"
]

# アンコモン（ビルドの入口）
UNCOMMON_REWARD_POOL = [
    "Pommel Strike",
    "Twin Strike",
    "Armaments",

    # 状態異常（軸になる）
    "Poison Strike",
    "Toxic Blow",

    "Weak Strike",
    "Weakening Hit"
]

# レア（ビルド完成パーツ）
RARE_REWARD_POOL = [
    # 火力
    "Pummel",
    "Execution",

    # 防御
    "Fortress",
    "Absolute Guard",

    # リソース系
    "Recharge",
    "Overdrive",
    "Deep Focus",

    # 状態異常強化
    "Neurotoxin",
    "Predator Strike"
]

# ─────────────────────────────────────────
# マップ定義
# ─────────────────────────────────────────
MAP_NODES = [
    # 深さ0: 開始ノード（2分岐）
    {"id": "n0",  "type": "battle", "next": ["n1a", "n1b"]},

    # 深さ1: 左ルート（通常戦闘）/ 右ルート（エリート）
    {"id": "n1a", "type": "battle", "next": ["n2a", "n2b"]},
    {"id": "n1b", "type": "elite",  "next": ["n2b", "n2c"]},

    # 深さ2: 中盤分岐
    {"id": "n2a", "type": "battle", "next": ["n3a"]},
    {"id": "n2b", "type": "rest",   "next": ["n3a", "n3b"]},
    {"id": "n2c", "type": "battle", "next": ["n3b"]},

    # 深さ3: 中盤後半
    {"id": "n3a", "type": "elite",  "next": ["n4"]},
    {"id": "n3b", "type": "battle", "next": ["n4"]},

    # 深さ4: 合流後の休憩
    {"id": "n4",  "type": "rest",   "next": ["n5a", "n5b"]},

    # 深さ5: ボス前分岐
    {"id": "n5a", "type": "battle", "next": ["n6"]},
    {"id": "n5b", "type": "elite",  "next": ["n6"]},

    # 深さ6: ボス前最終戦闘
    {"id": "n6",  "type": "battle", "next": ["n7"]},

    # 深さ7: 休憩（ボス直前）
    {"id": "n7",  "type": "rest",   "next": ["n8"]},

    # 深さ8: ボス（合流）
    {"id": "n8",  "type": "boss",   "next": []},
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
def _get_game_mode(row):
    """rowから game_mode を取得（旧 phase カラムにも対応）"""
    try:
        val = row["game_mode"]
        if val:
            return val
    except Exception:
        pass
    try:
        val = row["phase"]
        if val:
            return val
    except Exception:
        pass
    return "battle"


def load_state():
    conn = get_db()
    row = conn.execute("SELECT * FROM game_state WHERE id=1").fetchone()
    conn.close()
    if row is None:
        return None
    # enemy_status / player_status の安全な読み込み
    try:
        enemy_status = json.loads(row["enemy_status"]) if row["enemy_status"] else {}
    except Exception:
        enemy_status = {}
    try:
        player_status = json.loads(row["player_status"]) if row["player_status"] else {}
    except Exception:
        player_status = {}
    return {
        "player_hp":     row["player_hp"],
        "enemy_hp":      row["enemy_hp"],
        "player_block":  row["player_block"],
        "enemy_block":   row["enemy_block"] if row["enemy_block"] else 0,
        "energy":        row["energy"],
        "deck":          json.loads(row["deck"]),
        "hand":          json.loads(row["hand"]),
        "discard":       json.loads(row["discard"]),
        "current_node":  row["current_node"],
        "game_mode":     _get_game_mode(row),
        "reward_cards":  json.loads(row["reward_cards"]) if row["reward_cards"] else [],
        "remove_cards":  [],
        "enemy_intent":  row["enemy_intent"] if row["enemy_intent"] else "attack",
        "reward_type":   row["reward_type"] if row["reward_type"] else "battle",
        "enemy_status":  enemy_status,
        "player_status": player_status,
        "floor": row["floor"] if "floor" in row.keys() else 1,
    }


def save_state(state):
    conn = get_db()
    conn.execute("DELETE FROM game_state WHERE id=1")
    conn.execute("""
        INSERT INTO game_state
            (id, player_hp, enemy_hp, player_block, enemy_block, energy, deck, hand, discard, current_node, game_mode, reward_cards, enemy_intent, enemy_status, player_status,floor)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        state["player_hp"],
        state["enemy_hp"],
        state["player_block"],
        state.get("enemy_block", 0),
        state["energy"],
        json.dumps(state["deck"]),
        json.dumps(state["hand"]),
        json.dumps(state["discard"]),
        state["current_node"],
        state.get("game_mode", "battle"),
        json.dumps(state.get("reward_cards", [])),
        state.get("enemy_intent", "attack"),
        json.dumps(state.get("enemy_status", {})),
        json.dumps(state.get("player_status", {})),
        state.get("floor", 1)
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
        state.get("game_mode", "battle"),
        json.dumps(state.get("reward_cards", [])),
    )


def row_to_state(row):
    try:
        enemy_status = json.loads(row["enemy_status"]) if row["enemy_status"] else {}
    except Exception:
        enemy_status = {}
    try:
        player_status = json.loads(row["player_status"]) if row["player_status"] else {}
    except Exception:
        player_status = {}
    return {
        "player_hp":     row["player_hp"],
        "enemy_hp":      row["enemy_hp"],
        "player_block":  row["player_block"],
        "enemy_block":   row["enemy_block"] if row["enemy_block"] else 0,
        "energy":        row["energy"],
        "deck":          json.loads(row["deck"]),
        "hand":          json.loads(row["hand"]),
        "discard":       json.loads(row["discard"]),
        "current_node":  row["current_node"],
        "game_mode":     _get_game_mode(row),
        "reward_cards":  json.loads(row["reward_cards"]) if row["reward_cards"] else [],
        "enemy_status":  enemy_status,
        "player_status": player_status,
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
    # weak状態なら敵の攻撃力を0.75倍にする
    if state.get("enemy_status", {}).get("weak", 0) > 0:
        dmg = int(dmg * 0.75)
    absorbed = min(state["player_block"], dmg)
    state["player_block"] -= absorbed
    actual_damage = dmg - absorbed
    state["player_hp"] -= actual_damage


def apply_poison(state):
    """毒ダメージを処理する。enemy_status の poison 値分だけ敵HPを減少させ、値を1減らす"""
    poison_log = ""
    enemy_status = state.get("enemy_status", {})
    poison = enemy_status.get("poison", 0)
    if poison > 0:
        state["enemy_hp"] = max(0, state["enemy_hp"] - poison)
        new_poison = poison - 1
        if new_poison <= 0:
            del state["enemy_status"]["poison"]
        else:
            state["enemy_status"]["poison"] = new_poison
        poison_log = f" 毒で {poison} ダメージ！"
    return poison_log


def node_info(node_id):
    return NODE_MAP.get(node_id)


def available_next_nodes(current_node_id):
    node = node_info(current_node_id)
    if node is None:
        return []
    return [NODE_MAP[nid] for nid in node["next"] if nid in NODE_MAP]


import random

def generate_reward_cards(state):
    rewards = []

    floor = state.get("floor", 1)

    # 出現率（かなりバランスいい配分）
    common_rate   = 0.6
    uncommon_rate = 0.3
    rare_rate     = 0.1 + (floor - 1) * 0.05  # Actでレア増える

    for _ in range(3):
        r = random.random()

        if r < rare_rate:
            card = random.choice(RARE_REWARD_POOL)
        elif r < rare_rate + uncommon_rate:
            card = random.choice(UNCOMMON_REWARD_POOL)
        else:
            card = random.choice(COMMON_REWARD_POOL)

        rewards.append(card)

    return rewards



def decide_enemy_intent():
    """敵の次の行動をランダムに決定（"attack" または "block"）"""
    return random.choice(["attack", "block"])


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
    # 敵の行動意図をフロントに返す
    result["enemy_intent"] = state.get("enemy_intent", "attack")
    # 状態異常をフロントに返す
    result["enemy_status"] = state.get("enemy_status", {})
    result["player_status"] = state.get("player_status", {})
    # 報酬タイプをフロントに返す
    result["reward_type"] = state.get("reward_type", "battle")
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
        "player_hp":     50,
        "enemy_hp":      0,
        "player_block":  0,
        "enemy_block":   0,
        "energy":        3,
        "deck":          deck,
        "hand":          [],
        "discard":       [],
        "current_node":  "n0",
        "game_mode":     "battle",
        "reward_cards":  [],
        "reward_type":   "battle",
        "enemy_intent":  decide_enemy_intent(),
        "enemy_status":  {},
        "player_status": {},
        "floor" : 1
    }
    # 最初のノードが戦闘なら敵HPをセット
    node = node_info("n0")
    if node and node["type"] in ENEMY_HP_TABLE:
        state["enemy_hp"] = ENEMY_HP_TABLE[node["type"]]
        state["energy"] = 3
        state["player_block"] = 0
        state["enemy_block"] = 0
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

    # ───────── 状態初期化
    if "player_status" not in state:
        state["player_status"] = {}
    if "enemy_status" not in state:
        state["enemy_status"] = {}

    player_status = state["player_status"]
    enemy_status  = state["enemy_status"]

    # ───────── 共通ダメージ計算
    def calc_damage(base):
        dmg = base

        # 筋力
        dmg += player_status.get("strength", 0)

        # 弱体（攻撃ダウン）
        if player_status.get("weak", 0) > 0:
            dmg *= 0.75

        # 被ダメ増
        if enemy_status.get("vulnerable", 0) > 0:
            dmg *= 1.5

        return int(max(0, dmg))

    # ───────── カード使用
    state["energy"] -= card["cost"]
    effect = card["effect"]
    value = card["value"]

    log = ""

    # ───────── 攻撃系
    if effect == "damage":
        dmg = calc_damage(value)

        absorbed = min(state.get("enemy_block", 0), dmg)
        state["enemy_block"] -= absorbed
        dmg -= absorbed

        state["enemy_hp"] = max(0, state["enemy_hp"] - dmg)
        log = f"{card_name} で {dmg} ダメージ！"

    elif effect == "damage_block":
        dmg = calc_damage(value)

        absorbed = min(state.get("enemy_block", 0), dmg)
        state["enemy_block"] -= absorbed
        dmg -= absorbed

        state["enemy_hp"] = max(0, state["enemy_hp"] - dmg)
        state["player_block"] += value

        log = f"{card_name} で {dmg} ダメージ＆ブロック +{value}！"

    elif effect == "damage_draw":
        dmg = calc_damage(value)

        absorbed = min(state.get("enemy_block", 0), dmg)
        state["enemy_block"] -= absorbed
        dmg -= absorbed

        state["enemy_hp"] = max(0, state["enemy_hp"] - dmg)
        draw_cards(state, 1)

        log = f"{card_name} で {dmg} ダメージ＆1枚ドロー！"

    elif effect == "damage2":
        total = 0
        for _ in range(2):
            total += calc_damage(value)

        absorbed = min(state.get("enemy_block", 0), total)
        state["enemy_block"] -= absorbed
        total -= absorbed

        state["enemy_hp"] -= total
        log = f"{card_name} で {total} ダメージ（×2）！"

    # ───────── 防御
    elif effect == "block":
        block_val = value

        if player_status.get("frail", 0) > 0:
            block_val = int(block_val * 0.75)

        state["player_block"] += block_val
        log = f"{card_name} でブロック +{block_val}！"

    # ───────── ドロー
    elif effect == "draw":
        draw_cards(state, value)
        log = f"{card_name} で {value} 枚ドロー！"

    # ───────── 状態異常
    elif effect == "poison":
        enemy_status["poison"] = enemy_status.get("poison", 0) + value
        log = f"{card_name} で毒 +{value}！"

    elif effect == "weak":
        enemy_status["weak"] = enemy_status.get("weak", 0) + value
        log = f"{card_name} で弱体 +{value}！"

    elif effect == "vulnerable":
        enemy_status["vulnerable"] = enemy_status.get("vulnerable", 0) + value
        log = f"{card_name} で被ダメ増加 +{value}！"

    elif effect == "frail":
        enemy_status["frail"] = enemy_status.get("frail", 0) + value
        log = f"{card_name} で防御低下 +{value}！"

    # ───────── バフ
    elif effect == "strength":
        player_status["strength"] = player_status.get("strength", 0) + value
        log = f"{card_name} で筋力 +{value}！"

    # ───────── 複合
    elif effect == "damage_poison":
        dmg = calc_damage(value)

        absorbed = min(state.get("enemy_block", 0), dmg)
        state["enemy_block"] -= absorbed
        dmg -= absorbed

        state["enemy_hp"] = max(0, state["enemy_hp"] - dmg)
        enemy_status["poison"] = enemy_status.get("poison", 0) + value

        log = f"{card_name} で {dmg} ダメージ＆毒 +{value}！"

    elif effect == "damage_weak":
        dmg = calc_damage(value)

        absorbed = min(state.get("enemy_block", 0), dmg)
        state["enemy_block"] -= absorbed
        dmg -= absorbed

        state["enemy_hp"] = max(0, state["enemy_hp"] - dmg)
        enemy_status["weak"] = enemy_status.get("weak", 0) + value

        log = f"{card_name} で {dmg} ダメージ＆弱体 +{value}！"

    elif effect == "energy":
        state["energy"] = min(state["energy"] + value, 10)
        log = f"{card_name} でエネルギー +{value}！"

    # ───────── カード移動
    state["hand"].remove(card_name)
    state["discard"].append(card_name)

    # ───────── 撃破判定
    if state["game_mode"] == "battle" and state["enemy_hp"] <= 0:

        if node and node["type"] == "boss":
            state["floor"] = state.get("floor", 1) + 1
            state["current_node"] = "n0"
            state["game_mode"] = "map"

            save_state(state)

            enriched = enrich_state(state)
            enriched["log"] = f"{log} 🔥 ボス撃破！Act {state['floor']}へ！"
            return jsonify(enriched)

        reward_cards = generate_reward_cards(state)

        state["game_mode"] = "reward"
        state["reward_cards"] = reward_cards
        state["reward_type"] = "battle"

        save_state(state)

        enriched = enrich_state(state)
        enriched["log"] = log + " 戦闘に勝利！"
        return jsonify(enriched)

    # ───────── 通常保存
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

    # ───────── ステータス初期化
    if "player_status" not in state:
        state["player_status"] = {}
    if "enemy_status" not in state:
        state["enemy_status"] = {}

    player_status = state["player_status"]
    enemy_status  = state["enemy_status"]

    # ───────── 手札を捨て札へ
    state["discard"].extend(state["hand"])
    state["hand"] = []

    log = ""

    # ───────── 毒ダメージ
    poison = enemy_status.get("poison", 0)
    if poison > 0:
        state["enemy_hp"] -= poison
        log += f"毒で {poison} ダメージ！ "

    # ───────── 敵撃破チェック（超重要：先にやる）
    if state["enemy_hp"] <= 0:

        # ボス撃破
        if node and node["type"] == "boss":
            state["floor"] = state.get("floor", 1) + 1
            state["current_node"] = "n0"
            state["game_mode"] = "map"

            save_state(state)
            enriched = enrich_state(state)
            enriched["log"] = log + f"🔥 ボス撃破！Act {state['floor']}へ！"
            return jsonify(enriched)

        # 通常勝利
        reward_cards = generate_reward_cards(state)
        state["game_mode"] = "reward"
        state["reward_cards"] = reward_cards
        state["reward_type"] = "battle"

        save_state(state)
        enriched = enrich_state(state)
        enriched["log"] = log + "戦闘に勝利！"
        return jsonify(enriched)

    # ───────── 敵行動
    enemy_intent = state.get("enemy_intent", "attack")

    if enemy_intent == "attack":
        base = 6

        # 敵weak（攻撃低下）
        if enemy_status.get("weak", 0) > 0:
            base *= 0.75

        # プレイヤーvulnerable（被ダメ増）
        if player_status.get("vulnerable", 0) > 0:
            base *= 1.5

        dmg = int(base)

        absorbed = min(state.get("player_block", 0), dmg)
        state["player_block"] -= absorbed
        dmg -= absorbed

        state["player_hp"] = max(0, state["player_hp"] - dmg)

        log += f"敵が {dmg} ダメージ攻撃！ "

    elif enemy_intent == "block":
        state["enemy_block"] = state.get("enemy_block", 0) + 5
        log += "敵がブロック +5！ "

    # ───────── 状態減少（これ重要）
    def decay(status):
        for key in list(status.keys()):
            if key == "poison":
                continue  # 毒は減らない（スレスパ仕様）
            status[key] -= 1
            if status[key] <= 0:
                del status[key]

    decay(player_status)
    decay(enemy_status)

    # ───────── ブロックリセット
    state["player_block"] = 0

    # ───────── プレイヤー死亡
    if state["player_hp"] <= 0:
        save_state(state)
        enriched = enrich_state(state)
        enriched["log"] = log + "ゲームオーバー..."
        return jsonify(enriched)

    # ───────── 次ターン開始
    state["energy"] = 3
    draw_cards(state, 5)
    state["enemy_intent"] = decide_enemy_intent()

    save_state(state)
    enriched = enrich_state(state)
    enriched["log"] = log + "次のターン！"
    return jsonify(enriched)



@app.route("/map/select", methods=["POST"])
def map_select():
    data = request.get_json()
    node_id = data.get("node_id")

    state = load_state()
    if state is None:
        return jsonify({"error": "No game in progress"}), 404

    # 報酬フェーズ中は移動不可
    if state.get("game_mode") == "reward":
        return jsonify({"error": "Please select a reward card first"}), 400

    # 現在ノードの敵が生きていたら移動不可
    current = node_info(state["current_node"])
    if current and current["type"] in ("battle", "elite", "boss") and state["enemy_hp"] > 0:
        return jsonify({"error": "Battle not finished"}), 400

    next_nodes = available_next_nodes(state["current_node"])
    next_ids = [n["id"] for n in next_nodes]
    if node_id not in next_ids:
        return jsonify({"error": "Invalid node selection"}), 400

    # ノード更新
    state["current_node"] = node_id
    node = node_info(node_id)

    log = ""

    # ──────────────
    # 休憩ノード
    # ──────────────
    if node["type"] == "rest":
        state["enemy_hp"] = 0
        state["game_mode"] = "rest_choice"
        log = "休憩ノードに到達！「休憩」か「ショップ」を選んでください。"

    # ──────────────
    # 戦闘ノード
    # ──────────────
    elif node["type"] in ENEMY_HP_TABLE:

        # ✅ 基本HP
        base_hp = ENEMY_HP_TABLE[node["type"]]

        # ✅ floor取得（なければ1）
        floor = state.get("floor", 1)

        # ✅ 🎯 HP強化（ここが超重要）
        state["enemy_hp"] = base_hp + (floor - 1) * 20

        # 初期化
        state["energy"] = 3
        state["player_block"] = 0
        state["enemy_block"] = 0

        # 手札→discard
        state["discard"].extend(state["hand"])
        state["hand"] = []

        # ドロー
        draw_cards(state, 5)

        # 戦闘開始
        state["game_mode"] = "battle"
        state["enemy_intent"] = decide_enemy_intent()

        # 状態異常リセット
        state["enemy_status"] = {}
        state["player_status"] = {}

        # ✅ ログ（階層表示付き）
        
        current_floor = state.get("floor", 1)
        log = f"{node['type']} との戦闘開始！（Act {current_floor}）"


    # 報酬リセット
    state["reward_cards"] = []

    save_state(state)

    enriched = enrich_state(state)
    enriched["log"] = log
    return jsonify(enriched)



# ─────────────────────────────────────────
# 休憩選択
# ─────────────────────────────────────────
@app.route("/rest/select", methods=["POST"])
def rest_select():
    data = request.get_json()
    choice = data.get("choice")
    state = load_state()
    if state is None:
        return jsonify({"error": "No game in progress"}), 404

    if state.get("game_mode") != "rest_choice":
        return jsonify({"error": "Not in rest choice phase"}), 400

    if choice == "heal":
        state["player_hp"] = min(50, state["player_hp"] + 15)
        state["game_mode"] = "map"
        save_state(state)
        enriched = enrich_state(state)
        enriched["log"] = "休憩！HP +15 回復。マップへ戻ります。"
        return jsonify(enriched)
    elif choice == "shop":
        reward_cards = generate_reward_cards(state)
        state["game_mode"] = "reward"
        state["reward_cards"] = reward_cards
        state["reward_type"] = "shop"
        save_state(state)
        enriched = enrich_state(state)
        enriched["log"] = "ショップ！カードを1枚選んでデッキに追加できます。"
        return jsonify(enriched)
    elif choice == "remove":
        remove_cards = (
        state["deck"][:] +
        state["hand"][:] +
        state["discard"][:]
        )

        state["game_mode"] = "remove"
        enriched = enrich_state(state)
        enriched["remove_cards"] = remove_cards
        enriched["log"] = "カード削除モード。削除するカードを選んでください。"
        save_state(state)
        return jsonify(enriched)
    else:
        return jsonify({"error": "Invalid choice. Use 'heal', 'shop', or 'remove'"}), 400


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

    if state.get("game_mode") != "reward":
        return jsonify({"error": "Not in reward phase"}), 400

    # スキップ対応
    if card_name == "__skip__":
        state["game_mode"] = "map"
        state["reward_cards"] = []
        save_state(state)
        enriched = enrich_state(state)
        enriched["log"] = "カード報酬をスキップしました。マップへ戻ります。"
        return jsonify(enriched)

    if card_name not in state.get("reward_cards", []):
        return jsonify({"error": "Invalid card selection"}), 400

    # カードをデッキに追加
    state["deck"].append(card_name)
    state["game_mode"] = "map"
    state["reward_cards"] = []

    save_state(state)
    enriched = enrich_state(state)
    enriched["log"] = f"「{card_name}」をデッキに追加しました！マップへ戻ります。"
    return jsonify(enriched)


# ─────────────────────────────────────────
# カード削除
# ─────────────────────────────────────────
@app.route("/remove/select", methods=["POST"])
def remove_select():
    data = request.get_json()
    card_name = data.get("card")

    state = load_state()
    if state is None:
        return jsonify({"error": "No game in progress"}), 404

    if state.get("game_mode") != "remove":
        return jsonify({"error": "Not in remove mode"}), 400

    removed = False

    # ✅ ★ここが修正ポイント（hand優先にする）
    for zone in ["hand", "deck", "discard"]:
        if card_name in state[zone]:
            state[zone].remove(card_name)
            print("削除:", card_name, "from", zone)  # デバッグ用
            removed = True
            break

    if not removed:
        return jsonify({"error": "Card not found"}), 400

    # ✅ 削除後はマップへ戻す
    state["game_mode"] = "map"

    save_state(state)

    enriched = enrich_state(state)
    enriched["log"] = f"{card_name} を削除しました！"

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
            (name, player_hp, enemy_hp, player_block, energy, deck, hand, discard, current_node, game_mode, reward_cards, created_at)
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
            (id, player_hp, enemy_hp, player_block, energy, deck, hand, discard, current_node, game_mode, reward_cards, updated_at)
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
