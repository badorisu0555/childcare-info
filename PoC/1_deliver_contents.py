import pandas as pd
import boto3
from botocore.exceptions import ClientError
from langchain_core.prompts import PromptTemplate
import os
from dotenv import load_dotenv
import anthropic
from datetime import datetime, timedelta, timezone
from boto3.dynamodb.conditions import Key

JST = timezone(timedelta(hours=9))

def load_api_key():
    # override=True にすることで、.env のセットアップが既存の環境変数を上書きします
    env_path = os.path.join(os.path.dirname(__file__), "../.env")
    load_dotenv(dotenv_path=env_path, override=True)
    os.environ["ANTHROPIC_API_KEY"] = os.getenv("Anthropic_API_Key")

def create_response(prompt_text,today,deliverycontent,userprofile,categoryscore):
    client = anthropic.Anthropic()
    prompt = PromptTemplate(
        input_variables=["today", "deliverycontent", "userprofile", "categoryscore"],
        template = prompt_text)
    prompt = prompt.format(today=today, deliverycontent=deliverycontent, userprofile=userprofile, categoryscore=categoryscore)

    message = client.messages.create(
    model="claude-opus-5",
    max_tokens=1000,
    messages=[
        {
            "role": "user",
            "content": prompt,
        }
    ],
    tools = [
        {"type":"web_search_20260318","name":"web_search"}
    ]
    ),

    for block in message.content:
        if block.type == "text":
            print(block.text)  

    return block.text

def create_childhood_content(deliverycontent,userprofile,categoryscore):
    load_api_key()

    prompt_path = os.path.join(os.path.dirname(__file__), "../app/api/prompt.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_text = f.read()
    today = datetime.now(JST).strftime("%Y-%m-%d")
    answer = create_response(prompt_text, today, deliverycontent, userprofile, categoryscore)
    return answer

def get_dynamo_data(table_name,user_id,index_name=None,days=None,region_name='ap-northeast-1'):
    dynamodb = boto3.resource('dynamodb', region_name=region_name)
    table = dynamodb.Table(table_name)


    if index_name is not None:
        if days is None:
            raise ValueError("query時はdaysを指定してください。")

        now_jst = datetime.now(JST)
        start_time_str = (now_jst - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S+09:00")
        end_time_str = now_jst.strftime("%Y-%m-%dT%H:%M:%S+09:00")

        response = table.query(
            IndexName = index_name,
            KeyConditionExpression=(
                Key("user_id").eq(user_id) &
                Key("delivered_at").between(start_time_str, end_time_str)
            )
        )

        items = response.get('Items', [])
        return items

    else:
        response = table.get_item(Key={"user_id": user_id})
        return response.get("Item")

env_path = os.path.join(os.path.dirname(__file__), "../.env")
load_dotenv(dotenv_path=env_path, override=True)
LINE_user_id = os.getenv("LINE_user_id")

table_name_list = [
    "childcare-info-tests-table1-deliverycontent",
    "childcare-info-tests-table2-userprofile",
    "childcare-info-tests-table3-categoryscore",
]

# Table1: delivery_id(PK)とは別に、「あるuser_idの直近N日分」を検索したいので、GSI1(PK: user_id, SK: delivered_at)を作成しました。そのためindex_nameを指定してqueryする必要があります。
deliverycontent = get_dynamo_data(table_name_list[0], LINE_user_id, index_name="GSI1", days=5)
# 以下の二つは、user_idで一意に取得できるので、index_nameは不要でOKです。
userprofile = get_dynamo_data(table_name_list[1], LINE_user_id)
categoryscore = get_dynamo_data(table_name_list[2], LINE_user_id)

create_childhood_content(deliverycontent, userprofile, categoryscore)