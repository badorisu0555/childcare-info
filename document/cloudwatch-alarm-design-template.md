---
title: CloudWatchアラーム設計の型(再利用用まとめ)
tags:
  - AWS
  - CloudWatch
  - Lambda
  - SNS
  - 監視
private: false
updated_at: ''
id: null
organization_url_name: null
slide: false
ignorePublish: false
---

## この記事について

Lambdaで動くバッチ処理に対して、「特定の失敗パターンだけをピンポイントでメール通知したい」というCloudWatchアラームを設計したときの型をまとめます。次に別プロジェクトで同じことをやるときに、そのまま流用できることを目指しています。

ポイントは次の4つです。

1. ログ側: `[ALARM:xxx]`タグ運用ルール
2. インフラ側: メトリクスフィルタ → アラーム → SNS の3点セット
3. ログ設計は「検索できる形」にしておく
4. 「Lambdaが異常終了した」の検知には、コード側の実装(re-raiseするか否か)が効いてくる

## 1. ログ側: `[ALARM:xxx]`タグ運用ルール

**ルール**: 「アラームを鳴らしたい失敗」が起きた箇所で、決まったプレフィックスを付けてログ出力する。

```python
logger.error(f"[ALARM:<検知したい事象の名前>] <調査に必要な情報>")
```

### 命名の指針

- `<検知したい事象の名前>` は英大文字+アンダースコア(例: `DYNAMO_READ_FAILED`)で統一する
- 名前は「何のシステムの・何の処理が・どう失敗したか」が分かるように付ける
- 同じログの中に、原因調査に使う変数(テーブル名、ステータスコード、例外内容など)を`key=value`形式で添える

### 処理を止める/続けるは別問題として考える

```python
# 検知だけして処理は止めない(握りつぶす)
logger.error(f"[ALARM:XXX_FAILED] ...")

# 検知した上で処理も止める(再送出 or 明示的にraise)
logger.error(f"[ALARM:XXX_FAILED] ...")
raise
```

「ログを出す」ことと「例外を伝播させるか」は独立した判断です。ここを最初に決めておくと設計がぶれません。

## 2. インフラ側: メトリクスフィルタ → アラーム → SNS の3点セット

### 構成図

```
[ALARM:xxx]ログ → メトリクスフィルタ(検知) → カスタムメトリクス → アラーム(閾値判定) → SNSトピック → メール
```

### CloudFormation/SAMテンプレートの型

1つの`[ALARM:xxx]`につき、この3リソースが1セットになります。

```json
"XxxFailedMetricFilter": {
  "Type": "AWS::Logs::MetricFilter",
  "Properties": {
    "LogGroupName": { "Ref": "対象のLogGroup論理ID" },
    "FilterPattern": "\"[ALARM:XXX_FAILED]\"",
    "MetricTransformations": [{
      "MetricValue": "1",
      "DefaultValue": 0,
      "MetricNamespace": "任意のNamespace",
      "MetricName": "XxxFailed"
    }]
  }
},
"XxxFailedAlarm": {
  "Type": "AWS::CloudWatch::Alarm",
  "DependsOn": ["XxxFailedMetricFilter"],
  "Properties": {
    "AlarmName": "わかりやすいアラーム名",
    "Namespace": "任意のNamespace",
    "MetricName": "XxxFailed",
    "Statistic": "Sum",
    "Period": 3600,
    "EvaluationPeriods": 1,
    "Threshold": 1,
    "ComparisonOperator": "GreaterThanOrEqualToThreshold",
    "TreatMissingData": "notBreaching",
    "AlarmActions": [{ "Ref": "SNSトピック論理ID" }]
  }
}
```

SNSは検知パターンが何個あっても共通の1つでよいです。

```json
"AlertTopic": { "Type": "AWS::SNS::Topic", "Properties": { "TopicName": "..." } },
"AlertSubscription": {
  "Type": "AWS::SNS::Subscription",
  "Properties": { "TopicArn": { "Ref": "AlertTopic" }, "Protocol": "email", "Endpoint": { "Ref": "AlertEmail" } }
}
```

### チェックポイント(忘れがちな3点)

| 項目 | 忘れると起きること |
| --- | --- |
| `DefaultValue: 0` | エラーが無い間アラームが「データ不足(灰色)」のままになる |
| `TreatMissingData: notBreaching` | 同上の保険。無いとアラームが不安定に見える |
| フィルタパターンをダブルクォートで囲む(`"\"[ALARM:XXX]\""`) | `[`や`:`が構文エラーになる(角括弧はCloudWatch Logs側の予約記法のため) |

## 3. ログ設計の原則:「検索できる形」にしておく

- 固定文字列のプレフィックスを先に決める(`[ALARM:xxx]`)。エラーメッセージの自然文だけで判定しようとすると、文言修正のたびにアラームが壊れる
- 1つの失敗パターン = 1つのタグ = 1つのメトリクス、を徹底する。複数の失敗を1つのタグにまとめると、後で「どのエラーだったか」の切り分けができなくなる
- タグは実装より先に「何を検知したいか」から逆算して決める(先にログを書いてから後付けでタグを考えない)

## 4. なぜ`AWS/Lambda:Errors`メトリクスだけに頼らないのか

ここまで「独自のログタグ→メトリクスフィルタ」という少し遠回りな方式を紹介してきましたが、そもそもLambdaには`AWS/Lambda:Errors`という組み込みメトリクスがあり、これをそのままアラームにすれば済むように見えるかもしれません。あえてこの方式を採らなかった理由が、今回のいちばん大きな学びでした。

`AWS/Lambda:Errors`は、**関数が未処理の例外(unhandled exception)で終了した場合にだけ**自動的にカウントされます。つまり、1の「処理を止める/続けるは別問題として考える」で挙げた

```python
# 検知だけして処理は止めない(握りつぶす)
logger.error(f"[ALARM:XXX_FAILED] ...")
```

のパターンのように、例外をキャッチしてログを出したあと正常にreturnしてしまうコードは、AWS側からは**「成功」として扱われ、`Errors`メトリクスは一切増えません**。今回のように「一部の失敗は検知だけして処理は継続したい」という要件がある時点で、`Errors`メトリクス単体では検知漏れが確定してしまいます。

```python
try:
    do_something()
except SomeError as e:
    logger.error(f"[ALARM:XXX_FAILED] {e}")
    # raiseしなければLambdaとしては「正常終了」扱いになり、
    # AWS/Lambda:Errorsメトリクスには一切反映されない
```

これが、1〜3で説明した「ログにタグを仕込み、`Errors`メトリクスを経由せずに直接メトリクスフィルタで拾う」という方式を選んだ理由です。裏を返すと、`raise`し直して関数自体を異常終了させたい失敗については`Errors`メトリクスでも検知できるので、必ずしも常にこの方式が必須というわけではありません。ただし「一部の失敗だけ握りつぶしたい」要件が少しでもあるなら、`Errors`メトリクスに頼らずログタグ方式に統一しておいた方が、検知の抜け漏れを気にせずに済みます。

## まとめ

この4点をセットで覚えておけば、「新しい失敗パターンを検知したい」となったときに、①その失敗はraiseして止めるか・握りつぶして継続するかを決める → ②決めた方針にかかわらず検知できるようログにタグを1行追加する → ③メトリクスフィルタ・アラームを1セット追加する、という同じ手順で機械的に増やせます。
