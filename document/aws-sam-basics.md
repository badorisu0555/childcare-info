# AWS SAMの基本と、このリポジトリでの使い方

## この記事について

このリポジトリの`Infra/CloudFormation.json`は、ファイル名こそ「CloudFormation」ですが、実は**AWS SAM(Serverless Application Model)**のテンプレートです。冒頭に次の1行があるかどうかで見分けられます。

```json
"Transform": "AWS::Serverless-2016-10-31"
```

この記事では、AWS初心者向けに、

- SAMとは何か、使うとどんなメリットがあるのか
- CloudFormationとの違いは何か
- このリポジトリでは実際にSAMを使って何を構築しているのか

を順番に説明します。

## SAMとは何か

SAM(Serverless Application Model)は、AWSが提供している、**Lambdaを中心としたサーバーレス構成を、CloudFormationより少ない記述量で書けるようにする仕組み**です。

CloudFormationは「AWSの各種リソースをコードで定義して、まとめてデプロイできるようにするサービス」ですが、Lambda関数1つを普通にCloudFormationで書こうとすると、

- Lambda関数本体(`AWS::Lambda::Function`)
- 実行時に使うIAMロール(`AWS::IAM::Role`)
- コードをどこからデプロイするか(S3へのアップロード)

などを、それぞれ自分で細かく定義する必要があります。SAMは、これらのよくあるパターンを`AWS::Serverless::Function`のような**専用リソースタイプ**にまとめ、短く書けるようにしたものです。

冒頭の`Transform`行がポイントで、これは「このテンプレートはSAMの書き方で書かれているので、デプロイ前に通常のCloudFormationの書き方に変換してください」という指示です。つまりSAMは、独立した別サービスではなく、**CloudFormationの拡張機能**という位置づけになります。

## SAMを使うメリット

### 1. 記述量が減る

このリポジトリの`Lambda1Function`を例にすると、SAMではこれだけの記述でLambda関数を定義できます。

```json
"Lambda1Function": {
  "Type": "AWS::Serverless::Function",
  "Properties": {
    "FunctionName": { "Fn::Sub": "${ProjectName}-deliver-contents" },
    "CodeUri": "../app/deliver_contents/",
    "Handler": "main.lambda_handler",
    "Runtime": "python3.12",
    "Timeout": 120,
    "MemorySize": 512,
    "Role": { "Fn::GetAtt": ["Lambda1ExecutionRole", "Arn"] }
  }
}
```

特に`CodeUri`が便利な点です。ここにはローカルのソースコードのフォルダパス(`../app/deliver_contents/`)を指定するだけでよく、「このコードをZIPにしてS3にアップロードし、そのS3のパスをLambdaに紐付ける」という作業を、SAMのCLIツールが自動でやってくれます。通常のCloudFormationの`AWS::Lambda::Function`では、このS3のパスを自分で用意する必要があります。

### 2. サーバーレス用のCLIツール(SAM CLI)が使える

SAMには`sam`コマンドという専用のCLIツールがあり、次のようなコマンドが使えます。

- `sam build`: Lambdaのコードと依存ライブラリをまとめる
- `sam deploy`: ビルドした内容をAWSにデプロイする
- `sam local invoke`: Lambda関数を**手元のPCで**実行して動作確認する

特に`sam local invoke`は、「AWSに実際デプロイしなくても、Dockerコンテナ上でLambdaと近い環境を再現してテストできる」という点で、開発中に何度も試行錯誤する場面で助かります。

### 3. サーバーレスによくある構成が短く書ける

Lambda関数以外にも、`AWS::Serverless::Api`(API Gateway)や`AWS::Serverless::LayerVersion`(Lambda Layer)など、サーバーレス構成でよく使うリソースがSAM独自の書き方で用意されています。このリポジトリでは、後述する`LineBotSdkLayer`がその例です。

## CloudFormationとの違い

SAMは「別物」ではなく「CloudFormationの上に乗っている拡張」なので、違いは次のように整理できます。

| 観点 | CloudFormation | SAM |
| --- | --- | --- |
| 立ち位置 | AWSのリソースをコードで管理する基盤サービス | CloudFormationの拡張(`Transform`で変換される) |
| 書き方 | 全リソースをAWS本来のリソースタイプで細かく書く | Lambda・API Gateway・DynamoDBなどサーバーレス定番構成を専用リソースタイプで短く書ける |
| CLIツール | AWS CLI(`aws cloudformation ...`) | SAM CLI(`sam build` / `sam deploy` / `sam local invoke`など) |
| ローカル実行 | 標準機能では無い | `sam local invoke`でLambdaをローカル実行できる |
| 使える場面 | あらゆるAWSリソース | Lambda中心のサーバーレス構成 |

一番の理解のポイントは、**SAMのテンプレートは最終的にCloudFormationのテンプレートに変換されてからデプロイされる**、という点です。実際、このリポジトリの`Lambda1Function`(`AWS::Serverless::Function`)も、デプロイ時には内部で`AWS::Lambda::Function`と`AWS::Lambda::Function`用のS3コード配置に変換されています。そのため、SAM独自のリソースタイプと、通常のCloudFormationのリソースタイプが**同じテンプレートの中に混在していても問題ありません**。実際このリポジトリの`Infra/CloudFormation.json`でも、`AWS::Serverless::Function`(SAM)と`AWS::DynamoDB::Table`や`AWS::CloudWatch::Alarm`(通常のCloudFormation)が同じファイルの中に共存しています。

## 今回のユースケース

### 何を作っているか

`Infra/CloudFormation.json`は、このリポジトリのアプリケーション全体のAWSインフラをコードで定義しています。役割は大きく2つのLambda関数です。

- **Lambda1(`deliver-contents`)**: 毎朝決まった時刻に自動起動し、コンテンツを生成してLINEに配信する
- **Lambda2(`line-webhook`)**: LINE側からのpostback(ユーザーの操作)を受け取る

これに加えて、データの保存先であるDynamoDBのテーブル、処理が失敗したときにメールで気付けるようにするCloudWatchアラーム一式が、同じテンプレートの中にまとめて定義されています。

```
[EventBridge(毎朝)] → Lambda1(コンテンツ生成・LINE配信) → DynamoDB
                                                         ↑
[LINEユーザー] → Lambda2(postback受信) ─────────────────┘
```

### SAMらしい書き方をしている部分

テンプレート全体を1行ずつ追うのではなく、「これはSAM特有の書き方だ」とわかる代表的な部分だけを抜き出して見ていきます。

**Lambda関数本体(`AWS::Serverless::Function`)**

先ほども挙げた`Lambda1Function`が該当します。`CodeUri`でローカルのコードフォルダを指定するだけで、Lambdaへのコードのアップロードを任せられるのがSAMらしいところです。

**Lambda Layer(`AWS::Serverless::LayerVersion`)**

Lambda2は、LINEの公式SDK(`line-bot-sdk`)をLambda Layerとして読み込んでいます。

```json
"LineBotSdkLayer": {
  "Type": "AWS::Serverless::LayerVersion",
  "Properties": {
    "LayerName": { "Fn::Sub": "${ProjectName}-line-bot-sdk" },
    "ContentUri": "../line-bot-sdk-layer/",
    "CompatibleRuntimes": ["python3.12"],
    "RetentionPolicy": "Delete"
  }
}
```

Lambda Layerは、複数のLambda関数で共通して使うライブラリなどを外部化して、まとめて読み込ませる仕組みです。これも`AWS::Serverless::Function`と同じく、`ContentUri`にローカルフォルダを指定するだけでよく、通常のCloudFormationの`AWS::Lambda::LayerVersion`よりシンプルに書けます。

**その他のリソースは通常のCloudFormationのまま**

一方で、DynamoDBのテーブル(`AWS::DynamoDB::Table`)、毎朝の起動スケジュール(`AWS::Events::Rule`)、失敗を検知するCloudWatchアラーム(`AWS::CloudWatch::Alarm`など)は、SAM専用のリソースタイプが用意されていないため、通常のCloudFormationの書き方のまま定義されています。「サーバーレスの定番構成(Lambda・Layer)だけSAMの恩恵を受けて、それ以外は素のCloudFormationで書く」という、両者が混在した構成になっているのが、このテンプレートの特徴です。

## まとめ

- SAMは、CloudFormationの拡張機能で、Lambda中心のサーバーレス構成を短く書けるようにするもの
- `Transform: AWS::Serverless-2016-10-31`の1行があるテンプレートがSAM
- `sam build` / `sam deploy` / `sam local invoke`など専用CLIが使えるのもメリット
- このリポジトリでは、Lambda関数本体とLambda Layerだけ`AWS::Serverless::*`(SAM)を使い、DynamoDBやCloudWatchアラームなどは通常のCloudFormationのリソースタイプのまま、1つのテンプレートに混在させている
