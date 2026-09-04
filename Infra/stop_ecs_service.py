import boto3

CLUSTER_NAME = "ai_news"
SERVICE_NAME = "ai_news-service"
REGION = "ap-northeast-1"


def stop_ecs_service():
    """必要タスク数を0にしてコストを止める(サービス定義自体は削除しない)"""
    client = boto3.client("ecs", region_name=REGION)

    print(f"Stopping service {SERVICE_NAME} in cluster {CLUSTER_NAME} (desiredCount -> 0)...")

    try:
        response = client.update_service(
            cluster=CLUSTER_NAME,
            service=SERVICE_NAME,
            desiredCount=0,
        )
        service = response["service"]
        print(f"Success. status={service['status']} desiredCount={service['desiredCount']}")
        print("Note: This is a manual change outside CloudFormation stack 'ai-news-001'.")
        print("It will drift from the template (DesiredCount: 1) until restored or the stack is redeployed.")
    except Exception as e:
        print(f"Error stopping service: {e}")


if __name__ == "__main__":
    stop_ecs_service()
