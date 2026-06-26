# 要件定義書

## スレスパ風カードバトルゲーム（Web版・DB・セーブ・デッキ構築・カード拡張対応・完成版）

***

# 1. 概要

本システムは、Slay the Spire風のターン制カードバトルゲームをWebアプリケーションとして構築するものである。  
SQLite3による状態管理とセーブ／ロード機能を備え、戦闘後カード報酬によるデッキ構築要素を実装することで、戦略的かつ継続的にプレイ可能なゲーム体験を提供する。

***

# 2. 動作環境

## 2.1 フロントエンド

* Webブラウザ（Chrome推奨）
* HTML / CSS / JavaScript

## 2.2 バックエンド

* Python 3.x
* Flask

## 2.3 データベース

* SQLite3

***

# 3. システム構成

```
ブラウザ
↓
Flask（API）
↓
SQLite3
```

***

# 4. スコープ

## 4.1 含む機能

* ターン制カードバトル
* デッキ／手札／捨て札管理
* マップ進行
* 戦闘／回復イベント
* 戦闘後カード報酬（デッキ構築）
* セーブ／ロード機能
* 自動セーブ機能
* DBによる状態永続化

## 4.2 含まない機能

* ユーザー認証
* マルチプレイヤー
* アニメーション演出

***

# 5. ゲーム基本仕様

***

## 5.1 基本ルール

* ターン制バトル
* プレイヤーと敵が交互に行動
* HPが0で敗北
* ボス撃破でゲームクリア

***

## 5.2 プレイヤー

* HP：50
* エネルギー：3（ターン開始時回復）
* ブロック：ターン終了時リセット

***

## 5.3 敵仕様

| 種類  | HP |
| --- | -- |
| 通常敵 | 40 |
| 強敵  | 60 |
| ボス  | 80 |

***

# 6. カードシステム

***

## 6.1 初期デッキ（スターターカード）

* Strike ×5
* Defend ×4
* Draw ×1
* Heavy Strike ×1

***

## 6.2 スターターカード仕様

### Strike

* Cost：1
* 6ダメージ

### Defend

* Cost：1
* Block +5

### Draw

* Cost：1
* 2枚ドロー

### Heavy Strike

* Cost：2
* 10ダメージ

***

## 6.3 報酬カード（追加カードプール）

スターターとは別管理する

***

### ▼ 報酬カード一覧

#### Power Strike

* Cost：1
* 8ダメージ

#### Guard

* Cost：1
* Block +8

#### Quick Draw

* Cost：0
* 1枚ドロー

#### Double Strike

* Cost：2
* 12ダメージ

#### Shield Up

* Cost：2
* Block +12

#### Energy Boost

* Cost：0
* エネルギー +1

***

## 6.4 カード使用ルール

* エネルギー不足時は使用不可
* 使用後は捨て札へ移動

***

# 7. デッキ管理

***

## 7.1 構成

* deck（山札）
* hand（手札）
* discard（捨て札）

***

## 7.2 ドロー処理

* 手札が5枚になるまで補充
* 山札が空の場合：
  * 捨て札をシャッフルして再利用

***

# 8. 戦闘フロー

```
ターン開始
↓
エネルギー回復
↓
ドロー
↓
プレイヤー行動
↓
ターン終了
↓
敵行動
↓
ダメージ処理
↓
勝敗判定
```

***

# 9. マップ機能

***

## 9.1 ノード種類

* battle（通常敵）
* elite（強敵）
* rest（回復）
* boss（ボス）

***

## 9.2 ノード処理

| 種類     | 内容       |
| ------ | -------- |
| battle | 通常戦闘     |
| elite  | 強敵戦      |
| rest   | HP +15回復 |
| boss   | ボス戦      |

***

## 9.3 マップ構造

```
通常敵
↓
分岐
├ 通常敵
└ 強敵
↓
休憩
↓
ボス
```

***

## 9.4 ノード構造

```python
class Node:
    def __init__(self, type, next_nodes=None):
        self.type = type
        self.next_nodes = next_nodes or []
```

***

# 10. デッキ構築（戦闘後カード報酬）

***

## 10.1 発生条件

* 通常敵勝利
* 強敵勝利
* ボス勝利

***

## 10.2 処理フロー

```
戦闘勝利
↓
報酬画面
↓
カード候補3枚表示
↓
1枚選択
↓
デッキ追加
↓
マップに戻る
```

***

## 10.3 カード生成ルール

* reward\_card\_poolからランダム抽選
* 3枚提示
* 同一カード重複なし（推奨）
* スターターカードは除外

***

## 10.4 選択仕様

* 必ず1枚選択する
* スキップ不可

***

## 10.5 状態管理

```
game_mode = "reward"
```

***

## 10.6 API

```
GET  /reward
POST /reward/select
```

***

# 11. セーブ機能

***

## 11.1 手動セーブ

* 任意タイミング
* 複数保存可能

***

## 11.2 自動セーブ

* ブラウザ終了時
* ページ離脱時
* 最新1件のみ保持

***

## 11.3 ロード

* 手動セーブ選択
* 自動セーブ復元

***

# 12. フロントエンド仕様

***

## 戦闘画面

* HP表示
* エネルギー表示
* カードボタン
* ログ

***

## マップ画面

* ノード選択ボタン

***

## 報酬画面

```
カードを選択してください

[カード1]
[カード2]
[カード3]
```

***

## セーブ画面

* セーブ一覧
* セーブ／ロード操作

***

# 13. API一覧

```
POST /start
GET  /state
POST /action/card
POST /action/end_turn
POST /map/select

POST /save
GET  /save/list
POST /load
POST /autosave

GET  /reward
POST /reward/select
```

***

# 14. データベース設計

***

## save\_data（手動）

| カラム           | 内容    |
| ------------- | ----- |
| id            | 主キー   |
| name          | セーブ名  |
| player\_hp    | HP    |
| enemy\_hp     | HP    |
| player\_block | ブロック  |
| energy        | エネルギー |
| deck          | JSON  |
| hand          | JSON  |
| discard       | JSON  |
| current\_node | ノード   |
| game\_mode    | 状態    |
| reward\_cards | JSON  |
| created\_at   | 作成日時  |

***

## autosave

| カラム           | 内容    |
| ------------- | ----- |
| id            | 主キー   |
| player\_hp    | HP    |
| enemy\_hp     | HP    |
| player\_block | ブロック  |
| energy        | エネルギー |
| deck          | JSON  |
| hand          | JSON  |
| discard       | JSON  |
| current\_node | ノード   |
| game\_mode    | 状態    |
| reward\_cards | JSON  |
| updated\_at   | 更新日時  |

***

# 15. データ構造

```python
class Card:
    def __init__(self, name, cost, effect):
        self.name = name
        self.cost = cost
        self.effect = effect
```

***

```python
class GameState:
    player_hp
    enemy_hp
    player_block
    energy
    deck
    hand
    discard
    current_node
    game_mode
    reward_cards
```

***

# 16. 画面遷移

```
開始
↓
マップ
↓
戦闘
↓
報酬選択
↓
マップ
↓
セーブ（任意）
↓
ボス
↓
終了
```

***

# 17. 非機能要件

* レスポンス1秒以内
* データ永続化保証
* シンプルUI
* 操作しやすい設計

***

# 18. 開発方針

* 段階的実装
* 機能分割
* DB中心設計
* AI活用

***

# 19. 拡張方針

***

## フェーズ3

* 状態異常（毒・バフ）
* レアカード導入

***

## フェーズ4

* マップランダム生成
* UI強化

***

## フェーズ5

* ユーザー管理
* クラウド対応

***
