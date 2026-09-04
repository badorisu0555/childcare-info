# ai_news-service コスト削減 / 復旧 手順書

対象: ECS Fargate サービス `ai_news-service` (クラスター `ai_news`, リージョン `ap-northeast-1`, アカウント `992382612474`)

## 前提・方針

- Fargateはロードバランサーなしの実行中タスク分だけ課金される。**サービスを削除しなくても、必要タスク数(desiredCount)を0にするだけで実行中タスクがなくなり課金は止まる。**
- そのため本手順では **サービス自体は削除せず、desiredCountを0にする** 方式を採用する。
- このサービスはCloudFormationスタック `ai-news-001` (テンプレート: [Infra/CloudFormation.json](CloudFormation.json)) で作成されており、`DesiredCount: 1` が定義されている。今回はテンプレートを変更せず **AWS CLI/コンソールで直接** desiredCountを変更する運用を選択した。
  - **注意(ドリフト)**: この変更はCloudFormationの管理外で行われるため、スタックの実体とテンプレートの間に差分(ドリフト)が生じる。今後 `aws cloudformation deploy` 等でこのスタックを再デプロイすると、テンプレート通り `DesiredCount: 1` に上書きされ、停止したはずのサービスが再度起動する可能性がある。停止中はスタック更新を行わないこと。行う場合は事前にこの手順書を確認すること。

## 現在の構成 (2026-08-21 時点で確認済み)

| 項目 | 値 |
|---|---|
| クラスター | `ai_news` |
| サービス名 | `ai_news-service` |
| タスク定義 | `ai_news-api:18` |
| 起動タイプ | FARGATE / プラットフォーム LATEST |
| スケジューリング戦略 | REPLICA |
| desiredCount (通常時) | 1 |
| VPC | `vpc-0e3089799e13f2d8b` |
| サブネット | `subnet-06d53c601feefd572` |
| セキュリティグループ | `sg-09fe8f56738a4e625` |
| パブリックIP自動割り当て | ENABLED |
| ロードバランサー | なし |
| CloudFormationスタック | `ai-news-001` |

## 停止手順(コスト削減)

事前確認: AWS CLIが `992382612474` に対して認証済みであること。

```bash
aws sts get-caller-identity
```

### 方法A: 用意したスクリプトを使う(推奨)

```bash
cd Infra
python stop_ecs_service.py
```

### 方法B: AWS CLIを直接叩く

```bash
aws ecs update-service \
  --cluster ai_news \
  --service ai_news-service \
  --desired-count 0 \
  --region ap-northeast-1
```

### 方法C: マネジメントコンソール

1. ECS > クラスター `ai_news` > サービス `ai_news-service` を開く
2. 右上「サービスを更新」
3. 「必要なタスク数」を `0` に変更 > 更新

### 停止確認

```bash
aws ecs describe-services --cluster ai_news --services ai_news-service \
  --region ap-northeast-1 \
  --query "services[0].{desired:desiredCount,running:runningCount,status:status}"
```

`running: 0` になっていれば課金対象のタスクは無くなっている。サービス定義・タスク定義・ネットワーク設定はすべて残るため、いつでも復旧できる。

## 復旧手順

### 方法A: 用意したスクリプトを使う(推奨)

```bash
cd Infra
python restore_ecs_service.py
```

- サービスが残っている通常ケース: desiredCountを1に戻し、`services_stable` になるまで待機する。
- 万一サービス自体が削除されていた場合: スクリプト内に保存済みの設定(上表と同じ値)から `create_service` で再作成するフォールバックが自動的に動く。

### 方法B: AWS CLIを直接叩く(サービスが残っている場合)

```bash
aws ecs update-service \
  --cluster ai_news \
  --service ai_news-service \
  --desired-count 1 \
  --region ap-northeast-1

aws ecs wait services-stable \
  --cluster ai_news \
  --services ai_news-service \
  --region ap-northeast-1
```

### 方法C: マネジメントコンソール

1. ECS > クラスター `ai_news` > サービス `ai_news-service` を開く
2. 「サービスを更新」> 「必要なタスク数」を `1` に戻す > 更新
3. 「タスク」タブでタスクが `RUNNING` になるのを確認

### 復旧確認

```bash
aws ecs describe-services --cluster ai_news --services ai_news-service \
  --region ap-northeast-1 \
  --query "services[0].{desired:desiredCount,running:runningCount,status:status,taskDef:taskDefinition}"
```

`running: 1` かつタスクが `RUNNING` / ヘルシーであることに加え、アプリケーション自体(APIエンドポイント等)が応答することを確認する。

## トラブルシューティング

- **復旧してもタスクがすぐ止まる**: `aws ecs describe-tasks` でタスクの `stoppedReason` を確認。タスク定義 `ai_news-api:18` が依然有効か(非推奨/削除されていないか)を確認する。
- **停止中にCloudFormationスタックを更新してしまった**: `DesiredCount: 1` がテンプレート通りに適用され、サービスが再起動している可能性が高い。`describe-services` で状態確認のうえ、意図しない起動であれば再度 `stop_ecs_service.py` を実行する。
- **サービスごと削除されてしまっていた**: `restore_ecs_service.py` を実行すれば、保存済み設定から自動的に再作成される(方法Aを参照)。
