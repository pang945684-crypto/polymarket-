### Polymarket 跟单电报通知机器人

这是一个简单的 Python 机器人，用来**监听某个 Polymarket 地址的成交记录，并通过 Telegram 发送跟单通知**（信号），方便你手动跟单。

#### 一、准备工作

- **Python 环境**: 建议 Python 3.9+  
- **安装依赖**:

```bash
pip install -r requirements.txt
```

- **创建 Telegram 机器人并拿到 Token**
  - 在 Telegram 搜索 `@BotFather`
  - 发送 `/start` 然后 `/newbot`
  - 按提示设置名称和用户名
  - BotFather 会返回一个形如 `123456789:AAAA-BBBB...` 的 **`token`**

- **获取你的 chat_id**
  - 最简单方式：在 Telegram 搜索 `@userinfobot` 或 `@getmyid_bot`，点击开始，它会返回你的 `chat_id`
  - 或者把刚创建的机器人拉进一个群，并用类似 `@RawDataBot` 等机器人查看群的 chat_id

#### 二、配置文件

1. 复制示例配置：

```bash
copy config.example.json config.json
```

2. 打开 `config.json`，按实际情况修改：

- **`polymarket_leader_address`**: 你要跟单的 Polymarket 地址（0x 开头的钱包地址）  
- **`telegram_bot_token`**: 上面从 BotFather 拿到的 token  
- **`telegram_chat_id`**: 你的 Telegram 用户或群的 chat_id  
- **`poll_interval_seconds`**: 轮询间隔（秒），例如 15  
- **`taker_only`**: 是否只看吃单成交（通常保持 false 即可）  
- **`min_trade_size`**: 最小成交数量过滤，低于这个数量的不通知

#### 三、运行机器人

在项目根目录（有 `polymarket_copy_bot.py` 的地方）执行：

```bash
python polymarket_copy_bot.py
```

首次运行时，机器人会**读取该地址的历史成交，只记录但不推送**，避免历史消息刷屏。之后每隔 `poll_interval_seconds` 秒轮询一次，只对新出现的成交发 Telegram 通知。

#### 四、注意事项

- 目前机器人只是**发出跟单信号**，并不会自动帮你在 Polymarket 上下单；你需要自己根据信号去跟随交易。  
- 如果 Polymarket 的 API 或返回字段有更新，可能需要根据最新文档稍作调整。  
- 如果需要支持多地址、多策略、Web 控制面板等，可以在此脚本基础上进一步扩展。

