import os
import json
import re
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError
from logging import getLogger , StreamHandler , Formatter , DEBUG , INFO , ERROR , WARNING , CRITICAL

logger = getLogger(__name__)
handler = StreamHandler()
handler.setLevel(DEBUG)
formatter = Formatter('[%(levelname)s%(asctime)s%(message)s%(name)s]')
handler.setFormatter(formatter)
logger.setLevel(DEBUG)
logger.addHandler(handler)

logger.info('2_deliver_from_LINE.py is starting...')
JST = timezone(timedelta(hours=9))

env_path = os.path.join(os.path.dirname(__file__), "../.env")
load_dotenv(dotenv_path=env_path, override=True)
LINE_user_id = os.getenv("LINE_user_id")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

TABLE1_NAME = "childcare-info-tests-table1-deliverycontent"


def build_delivery_items(generated_content, user_id):
    # LINE表示用のitemsと、DynamoDB保存用のdb_itemsを組み立てるだけの処理(DB通信は行わない)。
    # DynamoDBへの保存(save_delivery_contents)を分離しておくことで、保存に失敗してもLINE配信は続行できるようにする。
    # score, ttlは初期状態(未評価)として登録しておき、ユーザーの評価postback受信時(Lambda2側)に更新する想定
    now_jst = datetime.now(JST)
    delivered_at_str = now_jst.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    delivered_date_str = now_jst.strftime("%Y%m%d")
    ttl_epoch = int((now_jst + timedelta(days=7)).timestamp())

    items = []
    db_items = []
    seq = 1
    for child in generated_content["children"]:
        logger.debug(f"[DEBUG] Processing child: {child.get('child_name', 'Unknown')}")
        child_name = child["child_name"]
        for content in child["contents"]:
            delivery_id = f"{user_id}#{delivered_date_str}#{seq:02d}"
            db_items.append({
                "delivery_id": delivery_id,
                "user_id": user_id,
                "delivered_at": delivered_at_str,
                "category": content["category"],
                "body": content["body"],
                "summary": content["summary"],
                "ttl": ttl_epoch,
            })
            items.append({
                "delivery_id": delivery_id,
                "header": f"{child_name}・{content['category']}",
                "body": content["body"],
            })
            seq += 1
    return items, db_items


def save_delivery_contents(db_items):
    logger.info('Writing delivery contents to DynamoDB...')
    dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
    table = dynamodb.Table(TABLE1_NAME)

    try:
        for item in db_items:
            table.put_item(Item=item)
    except ClientError as e:
        # 書き込みに失敗してもLINE配信は止めない方針のため、ここでは例外を再送出しない。
        # (代わりにpostbackでのスコア更新は効かなくなるが、情報が届くことを優先する)
        # ALARM: プレフィックスはCloudWatch Logsメトリクスフィルタで拾うための目印(他の失敗と区別するため)
        logger.error(f"[ALARM:DYNAMO_WRITE_FAILED] table={TABLE1_NAME}, error={e}")


def build_score_button(delivery_id, score):
    return {
        "type": "box",
        "layout": "vertical",
        "cornerRadius": "6px",
        "backgroundColor": "#EFEFEF",
        "paddingTop": "4px",
        "paddingBottom": "4px",
        "action": {
            "type": "postback",
            "label": str(score),
            "data": f"delivery_id={delivery_id}&score={score}"
        },
        "contents": [
            {"type": "text", "text": str(score), "align": "center", "size": "xs", "color": "#4A90D9"}
        ]
    }


def format_to_flex_carousel(delivery_items):
    # --- 文字列で届いた場合はJSONとしてパースする ---
    if isinstance(delivery_items, str):
        try:
            logger.debug("[DEBUG] Data is string type. Attempting json.loads...")
            delivery_items = json.loads(delivery_items)
        except Exception as e:
            logger.error(f"[ERROR] Failed to parse string to JSON: {e}")
            return None

    # 型チェック：この時点でリスト（list）になっていない場合は異常
    if not isinstance(delivery_items, list):
        logger.error(f"[ERROR] Expected list but got {type(delivery_items)}")
        return None

    if len(delivery_items) == 0:
        logger.error("[ERROR] delivery_items is empty")
        return None

    logger.debug(f"[DEBUG] Successfully converted to list. Items: {len(delivery_items)}")

    bubbles = []
    for item in delivery_items[:12]:
        # 必要なフィールドを get() で安全に取得
        bubble = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#4A90D9",
                "paddingAll": "12px",
                "contents": [
                    {"type": "text", "text": item.get("header", ""), "color": "#FFFFFF", "weight": "bold", "size": "md", "wrap": True}
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "16px",
                "contents": [
                    {"type": "text", "text": item.get("body", ""), "wrap": True, "size": "sm", "color": "#333333"}
                ]
            },
            "footer": {
                "type": "box",
                "layout": "horizontal",
                "spacing": "xs",
                "paddingAll": "8px",
                "contents": [build_score_button(item["delivery_id"], score) for score in range(1, 6)]
            }
        }
        bubbles.append(bubble)

    return {"type": "carousel", "contents": bubbles}


def push_line_message(user_id, flex_contents):
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": "本日の子育てのお役立ち情報を配信いたします！良いと感じたら下のボタンから評価をお願いします。"
            },
            {
                "type": "flex",
                "altText": "本日の育児情報が届きました",
                "contents": flex_contents
            }
        ]
    }

    url = "https://api.line.me/v2/bot/message/push"
    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        logger.info("Flex Messageが正常に送信されました")
    else:
        # ALARM: プレフィックスはCloudWatch Logsメトリクスフィルタで拾うための目印(他の失敗と区別するため)
        logger.error(f"[ALARM:LINE_DELIVERY_FAILED] status={response.status_code}, body={response.text}")
        # ここで例外を送出しないと、LINE配信に失敗してもLambdaは正常終了(exit code 0)扱いになり、
        # CloudWatchアラームがLambdaの Errors メトリクスで検知できなくなるため、あえて呼び出し元に伝播させる
        raise RuntimeError(f"LINE API Error: status={response.status_code}, body={response.text}")

    return response

logger.info('opening output.json...')
output_path = os.path.join(os.path.dirname(__file__), "output.json")
with open(output_path, "r", encoding="utf-8") as f:
    generated_content = json.load(f)

delivery_items, db_items = build_delivery_items(generated_content, LINE_user_id)
save_delivery_contents(db_items)

flex_contents = format_to_flex_carousel(delivery_items)

if flex_contents is None:
    logger.info("[ABORT] No contents to send. Skipping LINE API call.")
else:
    push_line_message(LINE_user_id, flex_contents)
