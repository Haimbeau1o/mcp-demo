#!/usr/bin/env python
import os
import sys
import argparse
import subprocess
import time
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MCP演示启动器")
    parser.add_argument("--mode", choices=["llm", "cli", "gui"], default="llm",
                        help="客户端模式：llm(默认AI助手)、cli(命令行)或gui(图形界面)")
    parser.add_argument("--model", type=str, default="doubao-1-5-lite-32k-250115",
                        help="方舟API模型ID (默认: doubao-1-5-lite-32k-250115)")
    args = parser.parse_args()
    
    # 脚本路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    server_script = os.path.join(current_dir, "server", "server.py")
    client_script = os.path.join(current_dir, "client", "client.py")
    gui_client_script = os.path.join(current_dir, "client", "ui_interface.py")
    
    # 检查环境变量
    if args.mode == "llm" and not os.environ.get("ARK_API_KEY"):
        print("错误: 未找到ARK_API_KEY环境变量。请在.env文件中设置或使用--mode cli运行命令行模式。")
        return
    
    # 启动服务器进程
    server_process = subprocess.Popen([sys.executable, server_script])
    
    try:
        # 等待服务器启动
        print("等待服务器启动...")
        time.sleep(3)
        
        # 根据参数选择启动的客户端
        client_process = None
        try:
            if args.mode == "llm":
                print("启动AI助手模式 - 使用方舟API与MCP工具...")
                llm_starter_path = os.path.join(current_dir, "start_llm.py")
                
                # 如果启动脚本不存在，创建它
                if not os.path.exists(llm_starter_path):
                    with open(llm_starter_path, "w") as f:
                        f.write(f"""#!/usr/bin/env python
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
    client = FileExplorerClientWithArkLLM(model_id="{args.model}")
    try:
        print("连接到MCP服务器...")
        connected = await client.connect("{server_script}")
        if not connected:
            return
        
        print("\\n=== AI文件助手已准备就绪 ===")
        print("您可以用自然语言提问，例如:")
        print('- "查找当前目录下的所有Python文件"')
        print('- "告诉我server目录下最大的文件是什么"')
        print('- "读取run_demo.py的内容"')
        print("输入'quit'或'exit'退出。\\n")
        
        await client.interactive_llm_loop()
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
""")
                
                # 直接运行启动脚本
                client_process = subprocess.Popen([sys.executable, llm_starter_path])
                client_process.wait()
            elif args.mode == "cli":
                # 启动普通命令行客户端
                client_process = subprocess.Popen([sys.executable, client_script, server_script])
                client_process.wait()
            else:
                # 启动GUI客户端
                client_process = subprocess.Popen([sys.executable, gui_client_script, server_script])
                client_process.wait()
        except KeyboardInterrupt:
            print("\n用户中断，正在关闭...")
            if client_process and client_process.poll() is None:
                client_process.terminate()
        
    finally:
        # 确保总是终止服务器
        print("正在关闭服务器...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()

if __name__ == "__main__":
    main()
