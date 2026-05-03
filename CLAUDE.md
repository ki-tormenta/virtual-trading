# CLAUDE.md - 仮想売買アプリ開発ガイド

このファイルはClaude Codeが本プロジェクトで作業する際の常時参照ドキュメントです。
コードを書く前・書く中で必ずこのファイルの方針に従ってください。

## プロジェクト概要

株式投資の仮想売買アプリ。ユーザーが仮想資金で株を売買し、メモを残して振り返ることで投資判断の質を高めるツール。

- **対象市場**: 日本株 + 米国株（投資信託は除外）
- **ユーザー**: 開発者本人（Phase 1）、将来的に友人と共有（Phase 3）
- **データソース**: yfinance（終値ベース）
- **動作環境**: Windows 10/11、Python 3.12、Streamlit

## 開発時の絶対ルール

### 1. レイヤー分離を厳守
**Streamlitのコード（pages/）からyfinanceやSQLAlchemyを直接呼ばない。** 必ずservice層を経由すること。

```python
# ❌ NG: pages/で直接呼ぶ
import yfinance as yf
ticker = yf.Ticker("6501.T")  # 絶対NG

# ✅ OK: serviceを経由
from core.services.price_service import PriceService
price = PriceService().get_close_price("6501.T")
```

理由: Phase 3でStreamlitを別UIに移行する可能性、データソースを切り替える可能性があるため。

### 2. user_idは必ずget_current_user_id()経由で取得
DBクエリで`user_id`が必要な箇所では、ハードコードせず必ず以下を使う:

```python
from core.auth import get_current_user_id

user_id = get_current_user_id()  # Phase 1では1を返す
```

### 3. 設定値はsettings経由
ハードコード禁止。設定値は`config/settings.py`に集約。

```python
from config.settings import settings

initial_cash = settings.INITIAL_CASH  # 環境変数から取得
```

### 4. 型ヒントを必ず付ける
全ての関数定義に型ヒントを記述。Pylanceで型チェックする前提。

```python
def calculate_pnl(quantity: int, current_price: float, avg_price: float) -> float:
    return (current_price - avg_price) * quantity
```

### 5. Phase 2/3用カラムは「先に作るが使わない」
DBスキーマの`fee`、`tax`、`password_hash`等のカラムは作成するが、Phase 1では値を入れない（デフォルト値のまま）。

## 技術スタック（変更禁止）

```toml
[project.dependencies]
streamlit = ">=1.30.0"
yfinance = ">=0.2.40"
pandas = ">=2.0.0"
plotly = ">=5.18.0"
sqlalchemy = ">=2.0.0"
python-dotenv = ">=1.0.0"
openpyxl = ">=3.1.0"

[project.optional-dependencies.dev]
ruff = "*"
pytest = "*"
```

パッケージ管理は **uv** を使用。`pip install`ではなく`uv add`を使うこと。

## ディレクトリ構造（厳守）

```
virtual-trading/
├── app.py                          # Streamlitエントリポイント
├── pages/                          # Streamlit画面（薄く保つ）
│   ├── 1_📊_dashboard.py
│   ├── 2_🔍_trade.py
│   ├── 3_📋_positions.py
│   └── 4_📜_history.py
├── core/                           # ビジネスロジック層
│   ├── __init__.py
│   ├── auth.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── trade_service.py
│   │   ├── portfolio_service.py
│   │   └── price_service.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── transaction_repo.py
│   │   ├── position_repo.py
│   │   ├── stock_repo.py
│   │   ├── account_repo.py
│   │   └── snapshot_repo.py
│   └── models/
│       ├── __init__.py
│       ├── transaction.py
│       ├── position.py
│       ├── stock.py
│       ├── account.py
│       └── snapshot.py
├── infrastructure/
│   ├── __init__.py
│   ├── data_sources/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── yfinance_source.py
│   └── db/
│       ├── __init__.py
│       ├── connection.py
│       ├── init_db.py
│       └── load_stock_master.py
├── config/
│   ├── __init__.py
│   ├── settings.py
│   └── .env.example
├── data/
│   └── trading.db                  # gitignore
├── tests/
├── .gitignore
├── pyproject.toml
├── uv.lock
├── README.md
└── CLAUDE.md
```

## DBスキーマ（SQLAlchemy 2.0スタイル）

```python
# core/models/base.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

### テーブル定義

```sql
-- users（Phase 3で活用、Phase 1はid=1固定）
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    email TEXT UNIQUE,
    password_hash TEXT,              -- Phase 3で使用
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 銘柄マスタ
CREATE TABLE stocks (
    ticker TEXT PRIMARY KEY,         -- '6501.T', 'AAPL'
    code TEXT NOT NULL,              -- '6501', 'AAPL'
    name TEXT NOT NULL,
    market TEXT NOT NULL,            -- 'JP' or 'US'
    sector TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_stocks_code ON stocks(code);

-- 価格履歴
CREATE TABLE price_history (
    ticker TEXT,
    date DATE,
    close_price REAL NOT NULL,
    PRIMARY KEY (ticker, date),
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);

-- 口座
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL DEFAULT 'メイン口座',
    initial_cash REAL NOT NULL DEFAULT 10000000,
    current_cash REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 取引履歴
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1,
    account_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('BUY', 'SELL')),
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    total_amount REAL NOT NULL,
    fee REAL DEFAULT 0,              -- Phase 2用
    tax REAL DEFAULT 0,              -- Phase 2用
    realized_pnl REAL,               -- 売却時のみ
    transaction_date DATE NOT NULL,
    memo TEXT,
    tags TEXT,                       -- カンマ区切り
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);
CREATE INDEX idx_transactions_user ON transactions(user_id);
CREATE INDEX idx_transactions_account ON transactions(account_id);

-- ポジション
CREATE TABLE positions (
    user_id INTEGER NOT NULL DEFAULT 1,
    account_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    avg_buy_price REAL NOT NULL,
    PRIMARY KEY (user_id, account_id, ticker),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);

-- 日次スナップショット
CREATE TABLE daily_snapshots (
    user_id INTEGER NOT NULL DEFAULT 1,
    account_id INTEGER NOT NULL,
    date DATE NOT NULL,
    cash REAL NOT NULL,
    market_value REAL NOT NULL,
    total_assets REAL NOT NULL,
    jp_market_value REAL DEFAULT 0,
    us_market_value REAL DEFAULT 0,
    PRIMARY KEY (user_id, account_id, date)
);
```

## 主要ロジック仕様

### 銘柄コード → ticker変換
```python
def normalize_ticker(code: str) -> str:
    """
    日本株: 4桁数字 → '{code}.T'
    米国株: アルファベット含む → そのまま
    """
    code = code.strip().upper()
    if code.isdigit() and len(code) == 4:
        return f"{code}.T"
    return code
```

### 買付処理
```python
def buy(ticker: str, quantity: int, memo: str, tags: str) -> Transaction:
    """
    1. 終値を取得（当日キャッシュ優先）
    2. 必要金額チェック（current_cash >= quantity * price）
    3. 平均取得単価を再計算
       new_avg = (old_qty * old_avg + new_qty * new_price) / (old_qty + new_qty)
    4. transactions追加、positions更新（UPSERT）、accounts.current_cash減算
    5. トランザクション内で実行
    """
```

### 売却処理
```python
def sell(ticker: str, quantity: int, memo: str, tags: str) -> Transaction:
    """
    1. 保有数量チェック
    2. 終値を取得
    3. realized_pnl = (current_price - avg_buy_price) * quantity
    4. transactions追加（realized_pnl記録）
    5. positions数量減算（quantity == 0なら削除、avg_buy_priceは維持）
    6. accounts.current_cash加算
    """
```

### 平均取得単価の重要ルール
- **買付時のみ更新**: 加重平均で再計算
- **売却時は不変**: 数量だけ減らし、avg_buy_priceは保持
- **全売却時**: positionsレコード削除

### 株価取得（キャッシュ戦略）
```python
def get_close_price(ticker: str, date: date | None = None) -> float:
    """
    1. dateが指定されない場合は最新営業日
    2. price_historyテーブルにキャッシュがあればそれを返す
    3. なければyfinanceから取得し、price_historyにINSERT
    4. 失敗時はリトライ（最大3回、指数バックオフ）
    """
```

## コーディング規約

### 命名規則
- ファイル名: `snake_case.py`
- クラス名: `PascalCase`
- 関数名・変数名: `snake_case`
- 定数: `UPPER_SNAKE_CASE`
- プライベート: `_leading_underscore`

### docstring
全public関数にGoogleスタイルのdocstring:
```python
def buy(ticker: str, quantity: int) -> Transaction:
    """銘柄を買付する。

    Args:
        ticker: 銘柄ティッカー（例: '6501.T'）
        quantity: 購入数量

    Returns:
        作成されたトランザクション

    Raises:
        InsufficientFundsError: 残高不足の場合
    """
```

### エラーハンドリング
カスタム例外を定義し、ビジネスロジックエラーを明確化:
```python
# core/exceptions.py
class TradingError(Exception):
    """売買関連エラーの基底クラス"""

class InsufficientFundsError(TradingError):
    """残高不足"""

class InsufficientSharesError(TradingError):
    """保有数不足"""

class StockNotFoundError(TradingError):
    """銘柄が見つからない"""
```

### Streamlitでのstate管理
```python
# 必ずst.session_stateで状態を保持
if 'selected_ticker' not in st.session_state:
    st.session_state.selected_ticker = None
```

### 日付・時刻の扱い
- DBには`DATE`型で保存（ISO 8601形式の文字列）
- タイムゾーン: 日本株はAsia/Tokyo、米国株はAmerica/New_York
- 表示: ユーザーローカル（Asia/Tokyo）

## UI設計指針

### Streamlitページ命名
ファイル名にナンバリングと絵文字を含めると自動でサイドバーに表示される:
- `pages/1_📊_dashboard.py`
- `pages/2_🔍_trade.py`
- `pages/3_📋_positions.py`
- `pages/4_📜_history.py`

### 数値フォーマット
```python
# 金額（円）
f"{amount:,.0f}円"  # 1,234,567円

# 損益率
f"{pct:+.2f}%"  # +5.23% / -2.10%

# 数量
f"{qty:,d}株"  # 1,000株
```

### Plotlyでの日本語フォント
Windowsで文字化け防止のため必ず指定:
```python
fig.update_layout(
    font=dict(family='Meiryo, Yu Gothic, Hiragino Sans, sans-serif')
)
```

### 色使い（損益表示）
- 利益: 緑 `#26a69a`
- 損失: 赤 `#ef5350`
- 中立: グレー `#9e9e9e`

## テスト方針

### Phase 1のテストスコープ
- core/services/ の単体テストは必須
- repositoriesは結合テストでカバー
- Streamlit UIは手動テスト

### テスト例
```python
# tests/test_trade_service.py
def test_buy_updates_avg_price_correctly():
    """複数回買付した時の平均単価計算を検証"""
    service = TradeService(...)
    service.buy("6501.T", 100, price=3000)
    service.buy("6501.T", 100, price=3500)
    position = service.get_position("6501.T")
    assert position.avg_buy_price == 3250.0
```

## 開発ステップ（順序厳守）

### Step 1: プロジェクト初期化
```bash
uv init --python 3.12
uv add streamlit yfinance pandas plotly sqlalchemy python-dotenv openpyxl
uv add --dev ruff pytest
```
- `.gitignore` 作成
- `config/settings.py` 作成
- `.env.example` 作成
- 空のディレクトリ構造を作成

### Step 2: DB層
1. `core/models/base.py` - DeclarativeBase
2. `core/models/*.py` - 各モデル定義（SQLAlchemy 2.0スタイル）
3. `infrastructure/db/connection.py` - エンジン・セッション
4. `infrastructure/db/init_db.py` - テーブル作成、初期ユーザー(id=1)・口座作成
5. `infrastructure/db/load_stock_master.py` - JPX銘柄一覧取り込み

### Step 3: データソース層
1. `infrastructure/data_sources/base.py` - PriceDataSource抽象クラス
2. `infrastructure/data_sources/yfinance_source.py` - yfinance実装

### Step 4: Repository層
1. `core/repositories/*_repo.py` - 各リポジトリ
2. CRUD操作のみ、ビジネスロジックは含めない

### Step 5: Service層
1. `core/auth.py` - get_current_user_id()
2. `core/services/price_service.py` - 価格取得（キャッシュ含む）
3. `core/services/trade_service.py` - 買付・売却ロジック
4. `core/services/portfolio_service.py` - 損益計算・スナップショット

### Step 6: UI層
1. `app.py` - エントリポイント
2. `pages/2_🔍_trade.py` - 売買画面（先に作る、これがないと他が動かない）
3. `pages/3_📋_positions.py` - ポジション一覧
4. `pages/4_📜_history.py` - 取引履歴
5. `pages/1_📊_dashboard.py` - ダッシュボード（最後、他のデータが揃ってから）

### Step 7: 仕上げ
- エラーハンドリング全体見直し
- README.md整備
- 動作確認

## よくある落とし穴

| 落とし穴 | 対策 |
|---|---|
| Streamlitでrerunすると変数がリセット | `st.session_state` を使う |
| yfinanceで日本株が取得できない | tickerに`.T`が付いているか確認 |
| 米国株の終値が日本時間とズレる | UTC基準で取得、表示時にタイムゾーン変換 |
| 複数買付後の平均単価がおかしい | 加重平均の式を再確認、テストを書く |
| Plotlyの日本語が豆腐 | font_familyに'Meiryo'指定 |
| SQLite同時アクセスエラー | StreamlitセッションごとにSession分離 |
| 廃止銘柄でyfinanceがエラー | try/exceptでStockNotFoundError発生 |

## やってはいけないこと

- ❌ pages/から直接yfinanceやSQLAlchemyを呼ぶ
- ❌ user_idをハードコードする（必ずget_current_user_id()経由）
- ❌ DBスキーマからuser_idカラムを削除する
- ❌ 平均取得単価方式以外の損益計算を実装する（Phase 1）
- ❌ 手数料・税金の計算ロジックを書く（Phase 2の領域）
- ❌ 認証機能を実装する（Phase 3の領域）
- ❌ 単元株チェックを入れる（Phase 2の領域）
- ❌ Streamlitのキャッシュ（@st.cache_data）でDBデータをキャッシュする（古いデータが表示される）
- ❌ 投資信託の銘柄を追加する（Phase 1スコープ外）

## 参考情報

### yfinanceのticker命名
- 東証: `{4桁コード}.T`（例: `7203.T` トヨタ）
- NYSE/NASDAQ: コードのみ（例: `AAPL`, `GOOGL`）
- ロンドン: `{コード}.L`
- 香港: `{コード}.HK`

### JPX銘柄一覧URL
- ダウンロードページ: https://www.jpx.co.jp/markets/statistics-equities/misc/01.html
- 直接URL（変更される可能性あり、要確認）: https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls

### Streamlitドキュメント
- https://docs.streamlit.io/
- 特に確認すべき: `st.session_state`, `st.cache_data`の使い分け、`st.rerun()`

## 質問・判断に迷ったら

実装中に方針判断が必要になった場合:
1. 本ドキュメントを再確認
2. REQUIREMENTS.mdを確認
3. それでも不明な場合は実装を止めて確認を求める

特に以下は勝手に判断せず確認すること:
- Phase 1スコープ外の機能を「ついでに」実装する
- DBスキーマの変更
- 技術スタックの変更
- アーキテクチャ層の追加・削除
