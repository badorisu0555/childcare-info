import boto3

try :
    TABLE_NAME1 = "childcare-info-tests-table1-deliverycontent"
    TABLE_NAME2 = "childcare-info-tests-table2-userprofile"
    TABLE_NAME3 = "childcare-info-tests-table3-categoryscore"

    dynamodb_resource = boto3.resource("dynamodb")

    dynamodb_resource.create_table(
        TableName=  TABLE_NAME1,
        AttributeDefinitions=[
            {"AttributeName": "delivery_id", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "delivered_at", "AttributeType": "S"}
        ],
        KeySchema=[
            {"AttributeName": "delivery_id", "KeyType": "HASH"}
        ],
        GlobalSecondaryIndexes=[
            {'IndexName': 'GSI1',
            "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},         # 全件を集約するパーティション
                    {"AttributeName": "delivered_at", "KeyType": "RANGE"} # 日付でソート
            ],
            'Projection': {
                'ProjectionType': 'INCLUDE',
                'NonKeyAttributes':['category','summary','score']}
            }
        ],
        BillingMode='PAY_PER_REQUEST'
    )

    dynamodb_resource.create_table(
        TableName=  TABLE_NAME2,
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"}
        ],
        KeySchema=[
            {"AttributeName": "user_id", "KeyType": "HASH"}
        ],
        BillingMode='PAY_PER_REQUEST'
    )

    dynamodb_resource.create_table(
        TableName=  TABLE_NAME3,
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"}
        ],
        KeySchema=[
            {"AttributeName": "user_id", "KeyType": "HASH"}
        ],
        BillingMode='PAY_PER_REQUEST'
    )

    table1 = dynamodb_resource.Table(TABLE_NAME1)
    table2 = dynamodb_resource.Table(TABLE_NAME2)
    table3 = dynamodb_resource.Table(TABLE_NAME3)

    table1.wait_until_exists()
    table2.wait_until_exists()
    table3.wait_until_exists()

    dynamodb_resource.meta.client.update_time_to_live(
        TableName=TABLE_NAME1,
        TimeToLiveSpecification={"Enabled":True,"AttributeName":"ttl"}
    )

    dynamodb_resource.meta.client.update_time_to_live(
        TableName=TABLE_NAME2,
        TimeToLiveSpecification={"Enabled":True,"AttributeName":"ttl"}
    )

    dynamodb_resource.meta.client.update_time_to_live(
        TableName=TABLE_NAME3,
        TimeToLiveSpecification={"Enabled":True,"AttributeName":"ttl"}
    )


except Exception as e:
    print("Error creating tables:", e)