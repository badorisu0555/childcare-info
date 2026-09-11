import pandas as pd
import boto3
from botocore.exceptions import ClientError
from langchain_core.prompts import PromptTemplate
import os
from dotenv import load_dotenv
import anthropic
from datetime import datetime, timedelta, timezone , date
from boto3.dynamodb.conditions import Key
from dateutil.relativedelta import relativedelta 
import json
import re
from logging import getLogger , StreamHandler , Formatter , DEBUG , INFO , ERROR , WARNING , CRITICAL

logger = getLogger(__name__)
handler = StreamHandler()
handler.setLevel(DEBUG)
formatter = Formatter('[%(levelname)s%(asctime)s%(message)s%(name)s]')
handler.setFormatter(formatter)
logger.setLevel(DEBUG)
logger.addHandler(handler)

logger.info('1_deliver_contents.py is starting...')
JST = timezone(timedelta(hours=9))

def load_api_key():
    # override=True にすることで、.env のセットアップが既存の環境変数を上書きします
    logger.info('Loading API key from .env file...')
    env_path = os.path.join(os.path.dirname(__file__), "../.env")
    load_dotenv(dotenv_path=env_path, override=True)
    os.environ["ANTHROPIC_API_KEY"] = os.getenv("Anthropic_API_Key")

def extract_json(text):
    if text is None:
        return None
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text

def create_response(prompt_text,today,deliverycontent,userprofile,categoryscore):
    logger.info('Creating AI response...')
    client = anthropic.Anthropic()
    prompt = PromptTemplate(
        input_variables=["today", "deliverycontent", "userprofile", "categoryscore"],
        template = prompt_text)
    prompt = prompt.format(today=today, deliverycontent=deliverycontent, userprofile=userprofile, categoryscore=categoryscore)

    message = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=5000,
    messages=[
        {
            "role": "user",
            "content": prompt,
        }
    ],
    tools = [
        {"type":"web_search_20260318","name":"web_search"}
    ]
    )

    answer_text = None
    for block in message.content:
        if block.type == "text":
            answer_text = block.text

    return extract_json(answer_text)

def create_childhood_content(deliverycontent,userprofile,categoryscore):
    logger.info('Creating childhood content from dynamodb...')
    load_api_key()

    prompt_path = os.path.join(os.path.dirname(__file__), "../app/api/prompt.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_text = f.read()
    today = datetime.now(JST).strftime("%Y-%m-%d")
    answer = create_response(prompt_text, today, deliverycontent, userprofile, categoryscore)
    return answer

def get_dynamo_data(table_name,user_id,index_name=None,days=None,region_name='ap-northeast-1'):
    logger.info(f'Getting data from DynamoDB table: {table_name}, user_id: {user_id}, index_name: {index_name}, days: {days}')
    dynamodb = boto3.resource('dynamodb', region_name=region_name)
    table = dynamodb.Table(table_name)


    if index_name is not None:
        if days is None:
            raise ValueError("query時はdaysを指定してください。")

        now_jst = datetime.now(JST)
        start_time_str = (now_jst - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S+09:00")
        end_time_str = now_jst.strftime("%Y-%m-%dT%H:%M:%S+09:00")

        try:
            response = table.query(
                IndexName = index_name,
                KeyConditionExpression=(
                    Key("user_id").eq(user_id) &
                    Key("delivered_at").between(start_time_str, end_time_str)
                )
            )
        except ClientError as e:
            # 読み取りに失敗した日はコンテンツを生成できないため配信自体をスキップする方針。
            # ALARM: プレフィックスはCloudWatch Logsメトリクスフィルタで拾うための目印(他の失敗と区別するため)
            logger.error(f"[ALARM:DYNAMO_READ_FAILED] table={table_name}, user_id={user_id}, error={e}")
            raise

        items = response.get('Items', [])
        return items

    else:
        try:
            response = table.get_item(Key={"user_id": user_id})
        except ClientError as e:
            logger.error(f"[ALARM:DYNAMO_READ_FAILED] table={table_name}, user_id={user_id}, error={e}")
            raise
        return response.get("Item")

def calc_age_month(birth_date):
    today= date.today()
    birth_date = date.fromisoformat(birth_date)
    date_difference = relativedelta(today, birth_date)
    years_plus_month = round(date_difference.years + date_difference.months / 12, 1)
    return years_plus_month

def process_category_scores(categoryscore):
    categories = set()
    for key in categoryscore:
        if key.endswith("_sum"):
            categories.add(key[:-len("_sum")])
        elif key.endswith("_count"):
            categories.add(key[:-len("_count")])
    result = {
        cat:float(categoryscore[f"{cat}_sum"]) / float(categoryscore[f"{cat}_count"])
        for cat in categories
    }
    categoryscore = sorted(result.items() , key=lambda x:x[1],reverse=True)[:3]
    return [{"カテゴリー":CATEGORY_NAME_MAP[cat],"スコア":score} for cat,score in categoryscore]

env_path = os.path.join(os.path.dirname(__file__), "../.env")
load_dotenv(dotenv_path=env_path, override=True)
LINE_user_id = os.getenv("LINE_user_id")


table_name_list = [
    "childcare-info-tests-table1-deliverycontent",
    "childcare-info-tests-table2-userprofile",
    "childcare-info-tests-table3-categoryscore",
]

# Table1: delivery_id(PK)とは別に、「あるuser_idの直近N日分」を検索したいので、GSI1(PK: user_id, SK: delivered_at)を作成しました。そのためindex_nameを指定してqueryする必要があります。
logger.info('Getting delivery content from DynamoDB...')
deliverycontent = get_dynamo_data(table_name_list[0], LINE_user_id, index_name="GSI1", days=5)
deliverycontent = [{"サマリー":d["summary"],"カテゴリー":d["category"]} for d in deliverycontent]

# 以下の二つは、user_idで一意に取得できるので、index_nameは不要でOKです。
logger.info('Getting user profile from DynamoDB...')
userprofile = get_dynamo_data(table_name_list[1], LINE_user_id)
userprofile = {
    "価値観": userprofile["values"],
    "子供の情報":[
        {"子供の名前":c["child_name"],"月齢": calc_age_month(c["birth_date"])} for c in userprofile["children"]
    ]}

CATEGORY_NAME_MAP = {
    "sleep": "睡眠",
    "food": "食事・栄養",
    "growth": "発達・成長",
    "health": "健康・体調管理",
    "safety": "安全",
    "play": "遊び・おでかけ",
    "daycare": "保育園・制度",
    "parent_care": "親のケア",
}

logger.info('Getting category scores from DynamoDB...')
categoryscore = get_dynamo_data(table_name_list[2], LINE_user_id)
categoryscore = process_category_scores(categoryscore)

logger.info('Creating childhood content...')
answer = create_childhood_content(deliverycontent, userprofile, categoryscore)
print(repr(answer))
parsed = json.loads(answer)
print(json.dumps(parsed, indent=2, ensure_ascii=False))

output_path = os.path.join(os.path.dirname(__file__), "output.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(parsed, f, indent=2, ensure_ascii=False)
