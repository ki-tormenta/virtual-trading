# 仮想売買アプリ

実際の株価データ（yfinance）を使って仮想資金で日本株・米国株を売買し、メモを残して投資判断を振り返るツール。

## 機能

- **売買**: 銘柄コード入力 → 終値で即約定（成行）。メモ・タグ付き記録
- **ポジション一覧**: 保有銘柄の評価損益を市場別フィルタ付きで確認
- **取引履歴**: 期間・銘柄・種別でフィルタ。メモ・タグを確認
- **ダッシュボード**: 総資産・含み損益・実現損益・資産推移グラフ・ポートフォリオ円グラフ

### 対応市場
| 市場 | ティッカー形式 | 例 |
|---|---|---|
| 東証（日本株） | `{4桁コード}.T` | `7203.T`（トヨタ） |
| NYSE / NASDAQ | コードのまま | `AAPL`, `GOOGL` |

現金残高は **円（JPY）** で一元管理。米国株の売買時は約定時点の USD/JPY レートで円換算する。

## セットアップ

### 必要環境
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

### インストール

```bash
git clone <repository-url>
cd virtual-trading
uv sync
```

### 環境変数（任意）

```bash
cp config/.env.example .env
# .env を編集して初期資金などを変更
```

| 変数 | デフォルト | 説明 |
|---|---|---|
| `INITIAL_CASH` | `10000000` | 初期資金（円） |
| `DB_PATH` | `data/trading.db` | SQLite DBのパス |

### DB初期化

```bash
uv run python -m infrastructure.db.init_db
```

初回実行時に `data/trading.db` が作成され、ユーザー（id=1）と口座が登録される。

### 銘柄マスタ読み込み（日本株）

JPX公式の上場銘柄一覧を取り込む（初回のみ推奨）:

```bash
uv run python -m infrastructure.db.load_stock_master
```

※ 米国株はユーザーが銘柄コードを入力した時点で自動登録される。

## 起動

```bash
uv run streamlit run app.py
```

ブラウザで `http://localhost:8501` が開く。

## アーキテクチャ

```
pages/          UI層（Streamlit）      ← 薄く保つ
core/services/  サービス層（ビジネスロジック）
core/repositories/ リポジトリ層（DB操作）
infrastructure/ インフラ層（yfinance・DB接続）
```

- pages/ は service 経由でのみ DB・外部APIにアクセスする
- 現金残高は常に円建て。米国株取引時に usd_jpy レートで換算
- 実現損益（`realized_pnl`）は常に円換算でDBに保存

## 開発

```bash
# テスト
uv run pytest

# リント
uv run ruff check .
uv run ruff format .
```

## データ管理

- DBファイル: `data/trading.db`（`.gitignore` 対象）
- DBリセットが必要な場合は `data/trading.db` を削除して再初期化

## Phase ロードマップ

| Phase | 内容 |
|---|---|
| **Phase 1**（現在） | 個人利用MVP。仮想売買・損益確認・メモ |
| Phase 2 | 手数料・税金計算、単元株ルール、ベンチマーク比較 |
| Phase 3 | マルチユーザー・認証、PostgreSQL移行、Streamlit Cloud |
