"""JPX公式の上場銘柄一覧ExcelをダウンロードしてDBに投入するスクリプト。"""

import urllib.request
from pathlib import Path

import pandas as pd

from core.models.stock import Stock
from infrastructure.db.connection import SessionLocal

JPX_EXCEL_URL = (
    "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
)
CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "stock_master.xls"

# JPX Excel の列インデックス（0-based）
_COL_CODE = 1
_COL_NAME = 2
_COL_SECTOR = 5


def download_jpx_excel(force: bool = False) -> Path:
    """JPX銘柄一覧Excelをダウンロードしてキャッシュする。

    Args:
        force: Trueならキャッシュを無視して再ダウンロード

    Returns:
        キャッシュファイルのパス
    """
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if force or not CACHE_PATH.exists():
        print(f"Downloading from {JPX_EXCEL_URL} ...")
        urllib.request.urlretrieve(JPX_EXCEL_URL, CACHE_PATH)
        print("Download complete.")
    return CACHE_PATH


def load_stock_master(force_download: bool = False) -> int:
    """JPX銘柄マスタをDBにUPSERTする。

    Args:
        force_download: Trueならキャッシュを無視して再ダウンロード

    Returns:
        新規追加した銘柄数
    """
    path = download_jpx_excel(force=force_download)
    df = pd.read_excel(path, dtype=str, header=0)

    count = 0
    with SessionLocal() as session:
        for _, row in df.iterrows():
            code = str(row.iloc[_COL_CODE]).strip().zfill(4)
            if not code.isdigit() or len(code) != 4:
                continue

            name = str(row.iloc[_COL_NAME]).strip()
            sector_raw = str(row.iloc[_COL_SECTOR]).strip() if len(row) > _COL_SECTOR else None
            sector = sector_raw if sector_raw and sector_raw.lower() != "nan" else None

            ticker = f"{code}.T"
            existing = session.get(Stock, ticker)
            if existing is None:
                session.add(
                    Stock(ticker=ticker, code=code, name=name, market="JP", sector=sector)
                )
                count += 1
            else:
                existing.name = name
                existing.sector = sector

        session.commit()

    return count


if __name__ == "__main__":
    n = load_stock_master(force_download=True)
    print(f"Loaded {n} new stocks.")
