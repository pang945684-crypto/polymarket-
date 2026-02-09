import axios from "axios";
import { ethers } from "ethers";
import "dotenv/config";
import fs from "fs";

const config = JSON.parse(fs.readFileSync("./config.json"));

const provider = new ethers.JsonRpcProvider(process.env.POLYGON_RPC);

const USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"; // Polygon USDC

let lastBlock = await provider.getBlockNumber();

async function sendTelegram(text) {
  const url = `https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/sendMessage`;
  await axios.post(url, {
    chat_id: process.env.TELEGRAM_CHAT_ID,
    text,
  });
}

console.log("🚀 Bot started. Listening leader wallet...");
await sendTelegram("🟢 跟单实验 Bot 已启动，开始监听钱包 A");

setInterval(async () => {
  const currentBlock = await provider.getBlockNumber();
  if (currentBlock <= lastBlock) return;

  for (let i = lastBlock + 1; i <= currentBlock; i++) {
    const block = await provider.getBlockWithTransactions(i);
    for (const tx of block.transactions) {
      if (!tx.to) continue;

      if (tx.from.toLowerCase() === config.leaderWallet.toLowerCase()) {
        const msg = `
📡 监听到实验交易信号

钱包 A：
${config.leaderWallet.slice(0, 6)}...

交易 Hash：
${tx.hash}

👉 请前往 Polymarket 手动验证
👉 这是一次实验信号
`;
        console.log("🔥 Signal detected:", tx.hash);
        await sendTelegram(msg);
      }
    }
  }
  lastBlock = currentBlock;
}, 5000);
