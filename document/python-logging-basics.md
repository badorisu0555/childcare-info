# Python `logging`ライブラリの基本と、今回のLambdaでの使い方

## この記事について

このプロジェクトの各Lambda関数(`app/deliver_contents/main.py`など)の先頭には、必ず次のようなコードが書かれています。

```python
logger = getLogger(__name__)
handler = StreamHandler()
handler.setLevel(DEBUG)
formatter = Formatter('[%(levelname)s%(asctime)s%(message)s%(name)s]')
handler.setFormatter(formatter)
logger.setLevel(DEBUG)
logger.addHandler(handler)

logger.info('Creating childhood content is starting...')
```

`print()`で済みそうなところを、なぜこんなに何行も書いているのか。この記事では、Python標準の`logging`ライブラリの基本的な仕組みと、このコードが1行ずつ何をしているかを、初心者向けに整理します。

## そもそも`print()`ではなく`logging`を使うのはなぜか

`print()`は「画面に文字を出す」だけの機能ですが、`logging`には次のような`print()`には無い機能があります。

- **重要度(レベル)を分けられる**: 「デバッグ用の細かい情報」と「本当に困ったときのエラー」を区別できる
- **出力先を後から変更・追加できる**: 画面だけでなく、ファイルやAWS CloudWatch Logsなど、複数の場所に同時に出力できる
- **本番環境で出力量を調整できる**: 「本番ではINFO以上だけ出す」「開発中はDEBUGまで全部出す」のように、コードを変えずに出力量を制御できる

AWS Lambdaのように「実行結果を直接目で見れない(CloudWatch Logsを見に行くしかない)」環境では、この「後から出力先やレベルを制御できる」という特性がとても重要になります。

## `logging`を構成する4つの登場人物

`logging`ライブラリを理解する上で、まず次の4つの役割を覚えると全体像がつかみやすくなります。

| 登場人物 | 役割 | たとえるなら |
| --- | --- | --- |
| **Logger(記録係)** | ログを受け取り、記録するかどうかを判断する窓口 | 「報告を受け付ける担当者」 |
| **Handler(配達係)** | ログの出力先(画面・ファイル・CloudWatchなど)を決める | 「報告書をどこに届けるかの配達員」 |
| **Formatter(整形係)** | ログの見た目(どんな形式の文字列にするか)を決める | 「報告書のフォーマット(様式)を決める人」 |
| **Level(重要度)** | ログの重要度。これより低い重要度のログは無視される | 「この重要度以上だけ報告して、というフィルター」 |

この4つが「Logger → Handler → Formatter」という順番で連携して、最終的に1行のログが出力される、という流れになっています。

```
ログを出す(logger.info(...))
  → Loggerが「このレベルなら扱ってよいか」を判定
  → Handlerに引き渡す
  → Handlerが「このレベルなら出力してよいか」を判定
  → Formatterで見た目を整形
  → 出力先(画面・ファイル・CloudWatchなど)に書き出す
```

## 冒頭のコードを1行ずつ解説

```python
logger = getLogger(__name__)
```
**Logger(記録係)を作る**行です。`__name__`はそのファイル(モジュール)の名前が自動的に入る特殊な変数で、これをLoggerの名前にすることで「どのファイルから出たログか」を後から区別しやすくします。

```python
handler = StreamHandler()
```
**Handler(配達係)を作る**行です。`StreamHandler`は「標準出力(コンソール画面)に出力する」タイプのHandlerです。AWS Lambdaでは、標準出力に出したものが自動的にCloudWatch Logsに送られる仕組みになっているため、Lambda上でログを残すには基本的にこの`StreamHandler`で十分です。

```python
handler.setLevel(DEBUG)
```
**このHandlerが扱う最低レベルをDEBUGに設定する**行です。「DEBUG以上(=ほぼ全部)のログはこのHandlerに出力させる」という意味になります。

```python
formatter = Formatter('[%(levelname)s%(asctime)s%(message)s%(name)s]')
```
**Formatter(整形係)を作る**行です。`%(levelname)s`(レベル名)、`%(asctime)s`(時刻)、`%(message)s`(ログ本文)、`%(name)s`(Logger名)といった、あらかじめ決まったプレースホルダーを組み合わせて、ログの見た目のテンプレートを決めています。

```python
handler.setFormatter(formatter)
```
**HandlerにFormatterを取り付ける**行です。これで「このHandlerから出るログは、このテンプレートの形式にする」という設定が完了します。

```python
logger.setLevel(DEBUG)
```
**Logger自身が扱う最低レベルをDEBUGに設定する**行です。ここが重要なポイントで、**LoggerとHandler、両方にレベル設定がある**ことに注意してください(詳しくは次の章で説明します)。

```python
logger.addHandler(handler)
```
**LoggerにHandlerを取り付ける**行です。これで「このLoggerに来たログは、このHandler経由で出力する」という配線が完成します。

```python
logger.info('Creating childhood content is starting...')
```
ここでようやく**実際にログを1行出力**しています。`.info(...)`は「INFOレベルでこのメッセージを記録して」という意味です。

## なぜLoggerとHandler、両方にレベル設定が必要なのか

初心者がつまずきやすいポイントです。ログは次の**2段階のフィルター**を通過して初めて出力されます。

1. `logger.setLevel(...)` ← 1段階目の関所(Logger側)
2. `handler.setLevel(...)` ← 2段階目の関所(Handler側)

どちらか一方でも「このログのレベルでは通さない」と判断されると、そのログは出力されません。**両方とも「これ以上の重要度なら通す」という設定なので、両方をDEBUGにしておくと、実質「全部通す」という意味になります**。

レベルは重要度の低い順に、`DEBUG < INFO < WARNING < ERROR < CRITICAL`という並びです。例えば`logger.setLevel(INFO)`にすると、`logger.debug(...)`で書いたログはLoggerの時点でブロックされ、Handlerまで届きません。

## 今回のユースケースでの使い方

このプロジェクトでは、下記のような使い分けをしています。

| メソッド | 用途 | 例 |
| --- | --- | --- |
| `logger.debug(...)` | 開発中の細かい確認用ログ | `[DEBUG] Processing child: ...` |
| `logger.info(...)` | 「今どの処理をしているか」の進捗ログ | `Getting delivery content from DynamoDB...` |
| `logger.error(...)` | 失敗を記録するログ。CloudWatchアラームの検知対象にもなる | `[ALARM:DYNAMO_READ_FAILED] table=..., error=...` |

特に`logger.error`に`[ALARM:xxx]`という決まった文字列を含めているのは、[別記事(CloudWatchアラーム設計の型)](./cloudwatch-alarm-design-template.md)で解説した、**CloudWatch Logsのメトリクスフィルタでこの文字列を検索してアラームを発火させるため**です。「ログに何を書くか」は、単なるデバッグ用のメモではなく、監視の仕組みと直結している、という点がこのプロジェクトでの重要な使い方になっています。

また、AWS Lambda環境では標準出力がそのままCloudWatch Logsに送られるため、`StreamHandler`(画面に出すHandler)だけで、追加のライブラリや設定をしなくてもクラウド上でログが確認できる、という点もLambdaならではのポイントです。

## つまずきやすい注意点

### 同じLoggerに`addHandler`を複数回呼ぶと、ログが重複する

`getLogger(__name__)`は、**同じ名前で呼び出すと同じLoggerオブジェクトが返ってくる**という仕様があります。そのため、もし同じモジュールの初期化コード(冒頭の8行)が誤って2回実行されると、同じLoggerに`Handler`が2つ登録され、**1回の`logger.info(...)`でログが2行出力される**というバグになります。

このプロジェクトでも、複数のスクリプトを1つのLambda関数にまとめる過程で、この初期化コードが重複してしまい、同じ問題が実際に発生しかけました。「ログの初期化コードは、1つのモジュールにつき1回だけ実行されるようにする」というのは、地味ですが気をつけるべきポイントです。

## まとめ

- `logging`は「Logger(記録係)」「Handler(配達係)」「Formatter(整形係)」「Level(重要度)」の4つの役割が連携して動く仕組み
- ログは「Logger→Handler」の2段階のレベルチェックを通過して初めて出力される
- AWS Lambdaでは`StreamHandler`で標準出力に出すだけで、自動的にCloudWatch Logsに記録される
- このプロジェクトでは、`logger.error`のログ本文が単なるメモではなく、CloudWatchアラームの検知条件そのものになっている
