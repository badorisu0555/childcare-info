import sys
import time

import boto3

CLUSTER_NAME = "ai_news"
SERVICE_NAME = "ai_news-service"
REGION = "ap-northeast-1"
DESIRED_COUNT = 1

# サービスが手違いで削除されていた場合の再作成用フォールバック設定
# (2026-08-21時点でdescribe-servicesから採取した実際の設定値)
TASK_DEFINITION = "ai_news-api:18"
SUBNETS = ["subnet-06d53c601feefd572"]
SECURITY_GROUPS = ["sg-09fe8f56738a4e625"]
ASSIGN_PUBLIC_IP = "ENABLED"


def service_exists(client) -> bool:
    resp = client.describe_services(cluster=CLUSTER_NAME, services=[SERVICE_NAME])
    services = [s for s in resp.get("services", []) if s["status"] != "INACTIVE"]
    return len(services) > 0


def restore_by_scaling_up(client):
    """通常ケース: サービスは残っていて desiredCount=0 になっているだけ"""
    print(f"Restoring service {SERVICE_NAME} (desiredCount -> {DESIRED_COUNT})...")
    response = client.update_service(
        cluster=CLUSTER_NAME,
        service=SERVICE_NAME,
        desiredCount=DESIRED_COUNT,
    )
    service = response["service"]
    print(f"Requested. status={service['status']} desiredCount={service['desiredCount']}")

    print("Waiting for service to reach steady state (this can take a minute)...")
    waiter = client.get_waiter("services_stable")
    waiter.wait(cluster=CLUSTER_NAME, services=[SERVICE_NAME])
    print("Service is stable and running again.")


def restore_by_recreating(client):
    """異常ケース: サービス自体が削除されていた場合の再作成フォールバック"""
    print(f"Service {SERVICE_NAME} not found. Recreating from saved config...")
    response = client.create_service(
        cluster=CLUSTER_NAME,
        serviceName=SERVICE_NAME,
        taskDefinition=TASK_DEFINITION,
        desiredCount=DESIRED_COUNT,
        launchType="FARGATE",
        platformVersion="LATEST",
        schedulingStrategy="REPLICA",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": SUBNETS,
                "securityGroups": SECURITY_GROUPS,
                "assignPublicIp": ASSIGN_PUBLIC_IP,
            }
        },
    )
    print(f"Created service: {response['service']['serviceArn']}")

    print("Waiting for service to reach steady state (this can take a minute)...")
    waiter = client.get_waiter("services_stable")
    waiter.wait(cluster=CLUSTER_NAME, services=[SERVICE_NAME])
    print("Service is stable and running again.")


def restore_ecs_service():
    client = boto3.client("ecs", region_name=REGION)
    try:
        if service_exists(client):
            restore_by_scaling_up(client)
        else:
            restore_by_recreating(client)
    except Exception as e:
        print(f"Error restoring service: {e}")
        sys.exit(1)


if __name__ == "__main__":
    restore_ecs_service()
