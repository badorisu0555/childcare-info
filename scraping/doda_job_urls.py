"""doda の求人検索結果ページから、求人詳細ページの URL を集めて CSV に保存するスクリプト。

使い方の例:
    # 1ページ目だけ
    python doda_job_urls.py

    # 2〜5ページ目
    python doda_job_urls.py --start 2 --end 5

    # 保存先とアクセス間隔を指定
    python doda_job_urls.py --start 1 --end 3 --output urls.csv --interval 5

    # ネットに繋がず、保存済みの HTML ファイルで動作確認する
    python doda_job_urls.py --html page1.html

必要なライブラリ:
    pip install requests beautifulsoup4
"""

import argparse
import csv
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# サイトのドメイン。href は "/DodaFront/..." という相対パスなので、
# これを頭に付けて完全な URL にする
BASE_URL = "https://doda.jp"

# 検索条件（データサイエンティスト職）の1ページ目の URL。
# 2ページ目以降は、この後ろに "-page__2/" のように付け足した URL になる
SEARCH_URL = "https://doda.jp/DodaFront/View/JobSearchList/j_oc__0320M/-preBtn__3/"

# ブラウザからのアクセスに見せるためのヘッダー。
# 付けないと、プログラムからのアクセスとして拒否されることがある
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


def build_page_url(page: int) -> str:
    """ページ番号から、そのページの URL を作る。"""
    # 1ページ目だけは "-page__1/" を付けない URL になっている（サイトの仕様に合わせる）
    if page == 1:
        return SEARCH_URL
    return f"{SEARCH_URL}-page__{page}/"


def fetch_html(url: str) -> str:
    """URL にアクセスして HTML の文字列を返す。"""
    # timeout を付けないと、相手が応答しないときにいつまでも待ち続けてしまう
    response = requests.get(url, headers=HEADERS, timeout=30)
    # 404 や 500 などのエラーが返ったら、ここで例外にして気づけるようにする
    response.raise_for_status()
    return response.text


def extract_job_urls(html: str) -> list[str]:
    """HTML から、求人一覧に並んでいる求人の詳細 URL だけを取り出す。"""
    soup = BeautifulSoup(html, "html.parser")

    urls = []
    # 求人カードの見出しリンク（a.jobCard-header__link）だけを狙う。
    # ページ内のリンクを全部取ると、「よく閲覧されている求人」やランキングまで混ざるため。
    # カード下の「求人詳細を見る」ボタンも同じ URL なので、こちらは使わない
    for a in soup.select("a.jobCard-header__link"):
        href = a.get("href")
        if not href:
            continue
        full_url = urljoin(BASE_URL, href)  # 相対パス → 完全な URL
        # 念のため重複を除く。set ではなく list で確認するのは、ページ上の並び順を残すため
        if full_url not in urls:
            urls.append(full_url)
    return urls


def save_csv(rows: list[tuple[int, str]], path: str) -> None:
    """(ページ番号, URL) のリストを CSV に書き出す。"""
    # Excel で開いても文字化けしないように、BOM 付き UTF-8（utf-8-sig）にする。
    # newline="" は、Windows で空行が挟まるのを防ぐためのお決まりの書き方
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["page", "url"])  # 見出し行
        writer.writerows(rows)


def main() -> None:
    # コマンドラインから、取得するページの範囲などを選べるようにする
    parser = argparse.ArgumentParser(description="doda の求人詳細 URL を CSV に保存する")
    parser.add_argument("--start", type=int, default=1, help="開始ページ（既定: 1）")
    parser.add_argument("--end", type=int, default=None, help="終了ページ（省略時は開始ページと同じ）")
    parser.add_argument("--output", default="doda_job_urls.csv", help="保存する CSV ファイル名")
    parser.add_argument("--interval", type=float, default=3.0, help="ページ間で待つ秒数（既定: 3）")
    parser.add_argument("--html", default=None, help="ネットに繋がず、保存済み HTML ファイルを解析する")
    args = parser.parse_args()

    rows = []

    if args.html:
        # 動作確認用：ファイルを読むだけなので、相手のサイトにアクセスしない
        with open(args.html, encoding="utf-8") as f:
            for url in extract_job_urls(f.read()):
                rows.append((args.start, url))
    else:
        end = args.end if args.end is not None else args.start
        if args.start < 1 or end < args.start:
            parser.error("ページ範囲が正しくありません（1 <= start <= end にしてください）")

        for page in range(args.start, end + 1):
            url = build_page_url(page)
            print(f"[{page}ページ目] 取得中: {url}")
            try:
                urls = extract_job_urls(fetch_html(url))
            except requests.RequestException as e:
                # 1ページ失敗しても、それまでに取れた分は CSV に残せるよう、止めずに次へ進む
                print(f"  → 取得に失敗しました: {e}")
                urls = []
            print(f"  → {len(urls)} 件")

            # 最後のページを越えると求人が 0 件になるので、そこで打ち切る
            if not urls:
                print("求人が見つからなかったため終了します")
                break

            rows.extend((page, u) for u in urls)

            # 相手のサーバーに負担をかけないよう、次のページの前に少し待つ
            if page < end:
                time.sleep(args.interval)

    save_csv(rows, args.output)
    print(f"合計 {len(rows)} 件を {args.output} に保存しました")


if __name__ == "__main__":
    main()
