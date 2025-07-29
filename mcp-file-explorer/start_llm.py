#!/usr/bin/env python
import asyncio
import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加当前目录到sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from client.llm_client import FileExplorerClientWithArkLLM

async def main():
    # 检查API密钥
    if not os.environ.get("ARK_API_KEY"):
        print("错误: 未找到ARK_API_KEY环境变量")
        return
        
    print("初始化AI助手...")
    client = FileExplorerClientWithArkLLM(model_id="doubao-1-5-lite-32k-250115")
    try:
        print("连接到MCP服务器...")
        connected = await client.connect("/Volumes/passport/jiuzhi/mcp-file-explorer/server/server.py")
        if not connected:
            return
        
        print("\n=== AI文件助手已准备就绪 ===")
        print("您可以用自然语言提问，例如:")
        print('- "查找当前目录下的所有Python文件"')
        print('- "告诉我server目录下最大的文件是什么"')
        print('- "读取run_demo.py的内容"')
        print("输入'quit'或'exit'退出。\n")
        
        await client.interactive_llm_loop()
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
