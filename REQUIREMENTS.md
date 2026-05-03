# 仮想売買アプリ 要件定義書

## 1. プロジェクト概要

### 目的
株式投資の練習・振り返りができる仮想売買アプリ。実際の株価データを使い、仮想資金で売買体験を積み、判断の質を高めることを目的とする。

### 背景
- 現物資金がないと「買ってみたかった銘柄」の検証ができない
- 売買を記録しないと、自分の判断が正しかったかを忘れてしまう
- 売買時のメモを残し、後から振り返ることで投資スキルを向上させたい

### 想定ユーザー
- Phase 1: 開発者本人（個人利用）
- Phase 3以降: 友人を含む小規模グループ

## 2. スコープ

### Phase 1（MVP - 今回の対象）
- ✅ 銘柄コードによる検索（例: `6501` → 日立製作所）
- ✅ 終値ベースの売買（成行・即約定）
- ✅ 自由記述メモ・タグ機能
- ✅ ポジション一覧（市場別フィルタ）
- ✅ 取引履歴一覧
- ✅ ダッシュボード（総資産、評価損益、市場別損益）
- ✅ 資産推移グラフ
- ✅ SQLiteで永続化
- ✅ JPX銘柄マスタの初期化

### Phase 1で実装しないもの
- ❌ 構造化メモ（カテゴリ、想定保有期間など）
- ❌ 売却時の買い時メモ表示・自己評価機能
- ❌ 投資パターン分析
- ❌ 手数料・税金計算
- ❌ 単元株ルール（1株から購入可能）
- ❌ 認証・マルチユーザー
- ❌ リアルタイム価格
- ❌ 指値・逆指値
- ❌ 配当・株式分割対応
- ❌ ベンチマーク比較
- ❌ 投資信託対応

### Phase 2以降の拡張予定
- Phase 2: 手数料・税金、単元株ルール、ベンチマーク比較
- Phase 3: マルチユーザー、認証、PostgreSQL移行、Streamlit Cloudデプロイ

## 3. 機能要件

### 3.1 銘柄検索・売買
- ユーザーが証券コードを入力（日本株: 4桁数字、米国株: アルファベット）
- 入力されたコードから銘柄名・現在値（終値）を表示
- 株価チャート（過去1年）をPlotlyで表示
- 売買フォーム（数量、メモ、タグ）から注文
- 売却時は保有銘柄から選択可能

### 3.2 ダッシュボード
**表示KPI:**
- 総資産（現金 + 評価額）
- 評価損益（金額・%）
- 実現損益（累計）
- 含み損益
- 総合損益率（対初期資金）

**ビジュアル:**
- 資産推移グラフ（1ヶ月/3ヶ月/6ヶ月/1年/全期間切替）
- ポートフォリオ構成円グラフ
- 市場別評価額（日本株・米国株・現金）
- 保有銘柄ランキング（値上がり/値下がり Top3）

### 3.3 ポジション一覧
- 保有銘柄の一覧表示
- 各銘柄の数量、平均取得単価、現在値、評価損益、損益率
- 市場別フィルタ（日本株のみ/米国株のみ/全て）
- タグでフィルタ

### 3.4 取引履歴
- 全トランザクションの時系列表示
- フィルタ機能: 期間、銘柄、タグ、買い/売り
- メモの表示・編集

### 3.5 設定
- 初期資金のリセット
- 全データのエクスポート（CSV）
- データの完全リセット

## 4. 非機能要件

### 4.1 パフォーマンス
- アプリ起動: 5秒以内
- 売買処理: 3秒以内
- 株価取得: キャッシュ活用で2秒以内

### 4.2 データ
- SQLite（ローカルファイル）
- 株価データはアプリ起動時に取得・キャッシュ
- 日次スナップショットで資産推移を保持

### 4.3 拡張性
- ビジネスロジックをUI層から分離
- データソースを抽象化（yfinance → 他APIへ切替可能）
- DB接続を抽象化（SQLite → PostgreSQL移行可能）
- `user_id`を最初から保持（マルチユーザー対応の伏線）

### 4.4 動作環境
- OS: Windows 10/11
- Python: 3.11以上（推奨3.12）
- ブラウザ: Chrome、Edge、Firefox

## 5. 技術スタック

### 言語・フレームワーク
- Python 3.12
- Streamlit（UI）
- SQLAlchemy（ORM）

### 主要ライブラリ
| ライブラリ | 用途 |
|---|---|
| streamlit | Web UI |
| yfinance | 株価データ取得 |
| pandas | データ処理 |
| plotly | グラフ描画 |
| sqlalchemy | ORM・DB抽象化 |
| python-dotenv | 環境変数管理 |
| openpyxl | JPX銘柄一覧Excel読み込み |

### 開発ツール
- uv（パッケージ管理）
- Ruff（リンタ・フォーマッタ）
- pytest（テスト）

## 6. アーキテクチャ

### レイヤー構造
```
[UI Layer]      pages/*.py        (Streamlit画面、薄く保つ)
     ↓
[Service Layer] core/services/    (ビジネスロジック、UI非依存)
     ↓
[Repository]    core/repositories/ (DB操作の抽象化)
     ↓
[Infrastructure] infrastructure/   (yfinance、DB接続)
```

### ディレクトリ構造
```
virtual-trading/
├── app.py                          # Streamlitエントリポイント
├── pages/                          # Streamlit画面
│   ├── 1_📊_dashboard.py
│   ├── 2_🔍_trade.py
│   ├── 3_📋_positions.py
│   └── 4_📜_history.py
├── core/                           # ビジネスロジック層
│   ├── services/
│   │   ├── trade_service.py
│   │   ├── portfolio_service.py
│   │   └── price_service.py
│   ├── repositories/
│   │   ├── transaction_repo.py
│   │   ├── position_repo.py
│   │   ├── stock_repo.py
│   │   └── snapshot_repo.py
│   ├── models/
│   │   ├── transaction.py
│   │   ├── position.py
│   │   └── stock.py
│   └── auth.py                    # get_current_user_id()
├── infrastructure/                 # 外部依存層
│   ├── data_sources/
│   │   ├── base.py                # PriceDataSource抽象クラス
│   │   └── yfinance_source.py
│   └── db/
│       ├── connection.py
│       ├── init_db.py
│       └── load_stock_master.py
├── config/
│   ├── settings.py
│   └── .env.example
├── data/
│   └── trading.db
├── tests/
├── pyproject.toml
├── uv.lock
└── README.md
```

## 7. データベース設計

### テーブル一覧
1. `users` - ユーザー情報（Phase 3で活用）
2. `stocks` - 銘柄マスタ
3. `price_history` - 価格履歴（終値）
4. `accounts` - 口座
5. `transactions` - 取引履歴
6. `positions` - 現在ポジション
7. `daily_snapshots` - 日次資産スナップショット

### 主要なリレーション
- users (1) → (N) accounts
- accounts (1) → (N) transactions
- accounts (1) → (N) positions
- stocks (1) → (N) transactions
- stocks (1) → (N) price_history

詳細スキーマは別ドキュメント `SCHEMA.md` または `CLAUDE.md` 参照。

## 8. 主要なビジネスロジック

### 8.1 買付処理
1. 銘柄コード → tickerに変換（例: `6501` → `6501.T`、`AAPL` はそのまま）
2. 終値を取得（当日キャッシュがあれば使用、なければyfinanceから取得）
3. 必要金額 = 数量 × 終値、現金残高チェック
4. 平均取得単価を再計算: `(既存数量×既存平均 + 新規数量×新規価格) / 合計数量`
5. transactions, positions, accounts を更新
6. メモ・タグを保存

### 8.2 売却処理
1. 保有数量チェック
2. 終値を取得
3. 売却益 = (現在値 - 平均取得単価) × 数量
4. transactions に記録（realized_pnl も保存）
5. positions の数量を減算（全売却なら削除、平均取得単価は維持）
6. accounts の現金を増やす

### 8.3 損益計算（平均取得単価方式）
- 評価損益 = Σ((現在値 - 平均取得単価) × 数量)
- 実現損益 = Σ(transactions.realized_pnl)
- 総合損益 = 総資産 - 初期資金
- **重要**: 売却時に平均取得単価は変わらない（買付時のみ更新）

### 8.4 スナップショット作成
アプリ起動時に実行:
1. 全保有銘柄の最新終値を取得
2. 評価額・市場別評価額を計算
3. daily_snapshots に当日分をINSERT or UPDATE（UPSERT）

## 9. 銘柄マスタの初期化

### 日本株
- データソース: JPX公式 上場銘柄一覧Excel
- URL: https://www.jpx.co.jp/markets/statistics-equities/misc/01.html
- 初回起動時にダウンロード→SQLiteに投入
- ticker形式: `{コード}.T`（例: `6501.T`）

### 米国株
- 都度追加方式（ユーザーが入力したコードを動的に登録）
- yfinanceから`Ticker.info['longName']`で銘柄名取得
- ticker形式: `{コード}`（例: `AAPL`）

## 10. 開発ステップ

### Step 1: プロジェクト初期化
- ディレクトリ構造、`pyproject.toml`、`README.md`、`.gitignore`
- `config/settings.py`、`.env.example`

### Step 2: DB初期化
- SQLAlchemyモデル定義
- `init_db.py`（テーブル作成、初期ユーザー・口座投入）
- JPX銘柄マスタダウンロード→投入スクリプト

### Step 3: コアロジック
- `price_service.py`（yfinanceラッパー、キャッシュ）
- `trade_service.py`（買付・売却）
- `portfolio_service.py`（損益計算、スナップショット）

### Step 4: Streamlit UI
- `app.py`（エントリポイント、サイドバー）
- 4つのページを順次実装

### Step 5: 仕上げ
- エラーハンドリング
- 動作確認、バグ修正
- README整備

## 11. リスクと対策

| リスク | 影響 | 対策 |
|---|---|---|
| yfinanceのレート制限 | 株価取得失敗 | 当日終値をDBにキャッシュ、リトライ実装 |
| yfinance仕様変更 | 動作不能 | データソースを抽象化、バージョン固定 |
| Streamlitのrerun問題 | 状態消失 | st.session_stateで管理、DB永続化 |
| 廃止銘柄の扱い | エラー | 例外処理を明示的に書く |
| 米国株の時差 | 日付ズレ | ticker側のタイムゾーンに合わせる |

## 12. 用語定義

| 用語 | 定義 |
|---|---|
| ticker | yfinanceで使う銘柄識別子（例: `6501.T`, `AAPL`） |
| code | ユーザーが入力する証券コード（例: `6501`, `AAPL`） |
| 平均取得単価 | 同一銘柄を複数回買付した際の加重平均価格 |
| 評価損益 | 未売却ポジションの含み損益 |
| 実現損益 | 売却によって確定した損益 |
| スナップショット | ある時点の総資産の記録 |
