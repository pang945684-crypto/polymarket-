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

## Polymarket 累计入金查询

`polymarket_deposit.py` 用于查询 Polygon 钱包收到的 USDC.e 和原生 USDC，并按本项目的排除地址规则计算累计外部入金。

### 计算口径

```text
累计入金 = 收到的 USDC.e + USDC - 排除来源的转入
```

脚本只统计转入，不扣除提现。因此，结果是“过滤后的累计转入”，不是净入金，也不代表 Polymarket 或 Nansen 官方认证的充值金额。

脚本会：

- 查询 USDC.e 和原生 USDC 的 ERC-20 转入。
- 固定查询截止区块，避免分页期间链上数据变化。
- 读取全部分页，不会在达到金额阈值后提前停止。
- 使用 `Decimal` 计算金额。
- 按 `uniqueId` 去除重复记录。
- 排除 CTF Exchange、Conditional Tokens、Neg Risk、奖励、USDC 兑换池及本地规则中的其他来源。
- 查询不完整时返回失败，不把部分金额或零值当作完整结果。

### 环境要求

- Python 3.9 或更高版本。
- 支持 `alchemy_getAssetTransfers` 的 Polygon Alchemy RPC。
- 脚本只使用 Python 标准库，无需安装额外依赖。

在 PowerShell 中设置 RPC：

```powershell
$env:POLYGON_RPC_URL = 'https://polygon-mainnet.g.alchemy.com/v2/你的KEY'
```

不要把真实 RPC Key 写进代码或提交到 GitHub。

### 运行方法

```powershell
python .\polymarket_deposit.py 0x你的钱包地址
```

也可以指定一个尚不存在的结果目录：

```powershell
python .\polymarket_deposit.py 0x你的钱包地址 --output .\results\wallet-check-001
```

如果不指定 `--output`，脚本会在 `results` 下创建带钱包地址和 UTC 时间的目录。已有目录不会被覆盖。

### 输出文件

- `summary.json`：查询状态、累计入金、排除总额、截止区块、分页数和证据文件哈希。
- `transfers.jsonl`：每笔转入、币种、来源、金额、是否计入、排除原因和交易哈希。
- `pages.jsonl`：各分页的请求参数和 RPC 返回，用于复查。

只有当 `summary.json` 中的 `status` 为 `complete` 时，`gross_deposit` 才是完整结果。状态为 `incomplete` 时，不应使用任何部分金额。

### 已知限制

- 排除名单是本项目规则，不是官方地址分类，可能遗漏或误排来源。
- 只覆盖 Polygon 上的 USDC.e 和原生 USDC。
- 不会自动识别或合并 owner 地址与 proxy 地址。
- 不扣除提现，因此不能直接用于计算净本金、PnL 或 ROI。
- RPC 查询可能消耗 Alchemy 额度。
