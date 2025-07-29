import asyncio
from typing import List, Dict, Any, Optional
import json
import sys
import os
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import mcp.types as types

class FileExplorerClient:
    """MCP客户端实现，用于连接文件浏览服务器"""
    
    def __init__(self):
        """初始化客户端"""
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.tools = []
        self.resources = []
        
    async def connect(self, server_path: str):
        """连接到MCP服务器"""
        try:
            # 设置服务器参数
            server_params = StdioServerParameters(
                command="python",  # 使用Python解释器
                args=[server_path],  # 服务器脚本路径
                env=None  # 使用当前环境变量
            )
            
            try:
                # 创建stdio传输
                stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
                self.stdio, self.write = stdio_transport
                
                # 创建客户端会话并添加超时
                self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
                
                # 添加超时
                try:
                    await asyncio.wait_for(self.session.initialize(), timeout=10.0)
                    print("已连接到文件浏览MCP服务器")
                    
                    # 获取可用工具列表
                    tools_response = await self.session.list_tools()
                    self.tools = tools_response.tools
                    print(f"可用工具: {[tool.name for tool in self.tools]}")
                    
                    # 获取可用资源列表
                    resources_response = await self.session.list_resources()
                    self.resources = resources_response.resources
                    print(f"可用资源: {[res.name for res in self.resources]}")
                    
                    return True
                except asyncio.TimeoutError:
                    print("连接超时：服务器初始化响应时间过长")
                    return False
            except Exception as e:
                print(f"创建传输或会话失败: {str(e)}")
                return False
        except Exception as e:
            print(f"连接到MCP服务器失败: {str(e)}")
            return False
            
    async def search_files(self, pattern: str, directory: str):
        """使用search-files工具搜索文件"""
        if not self.session:
            print("客户端未连接到服务器")
            return None
        
        try:
            # 调用工具
            result = await self.session.call_tool(
                "search-files", 
                {"pattern": pattern, "directory": directory}
            )
            
            # 处理结果
            if result.content and len(result.content) > 0:
                for content in result.content:
                    if content.type == "text":
                        return content.text
            return "搜索没有返回结果"
        except Exception as e:
            return f"搜索文件时发生错误: {str(e)}"
            
    async def get_file_info(self, path: str):
        """使用file-info工具获取文件信息"""
        if not self.session:
            print("客户端未连接到服务器")
            return None
        
        try:
            # 调用工具
            result = await self.session.call_tool(
                "file-info", 
                {"path": path}
            )
            
            # 处理结果
            response = {}
            response["text"] = ""
            response["resources"] = []
            
            if result.content:
                for content in result.content:
                    if content.type == "text":
                        response["text"] = content.text
                    elif content.type == "resource":
                        response["resources"].append({
                            "uri": content.resource.uri,
                            "name": content.resource.name
                        })
            
            return response
        except Exception as e:
            return f"获取文件信息时发生错误: {str(e)}"
            
    async def read_file_resource(self, file_path: str):
        """读取文件资源"""
        if not self.session:
            print("客户端未连接到服务器")
            return None
        
        try:
            # 构造URI
            uri = f"file://{file_path}"
            
            # 读取资源
            result = await self.session.read_resource(uri)
            
            # 处理结果
            if result.contents and len(result.contents) > 0:
                return result.contents[0].text
            return "无法读取文件内容"
        except Exception as e:
            return f"读取资源时发生错误: {str(e)}"
            
    async def close(self):
        """关闭客户端连接"""
        await self.exit_stack.aclose()
        print("已关闭客户端连接")

async def interactive_mode(client):
    """交互式命令行界面"""
    print("\n=== 文件浏览器交互界面 ===")
    print("命令:")
    print("  explore [路径] - 探查并显示路径信息")
    print("  ls [路径] - 列出目录内容")
    print("  search <模式> <目录> - 搜索文件")
    print("  info <路径> - 获取文件信息")
    print("  read <路径> - 读取文件内容")
    print("  pwd - 显示当前可访问的路径")
    print("  exit - 退出程序")
    print("===========================\n")
    
    current_path = os.getcwd()  # 跟踪当前路径，用于相对路径导航
    
    while True:
        cmd = input(f"{current_path}> ").strip()
        
        if cmd == "exit":
            break
            
        parts = cmd.split()
        if len(parts) == 0:
            continue
            
        command = parts[0].lower()
        
        # 添加自动探查路径功能
        if command == "explore" or command == "e":
            path = " ".join(parts[1:]) if len(parts) > 1 else "."
            
            # 处理相对路径
            if not os.path.isabs(path):
                path = os.path.join(current_path, path)
                
            print("探查路径中...")
            result = await client.explore_paths(path)
            
            if isinstance(result, dict):
                print(result["text"])
                if result["resources"]:
                    print("\n可用资源:")
                    for res in result["resources"]:
                        print(f"- {res['name']}: {res['uri']}")
            else:
                print(result)
                
        # 添加列表目录内容功能（类似ls命令）
        elif command == "ls":
            path = " ".join(parts[1:]) if len(parts) > 1 else current_path
            
            # 处理相对路径
            if not os.path.isabs(path):
                path = os.path.join(current_path, path)
                
            print(f"列出 {path} 的内容...")
            result = await client.list_directory(path)
            print(result)
            
        # 显示当前可访问路径
        elif command == "pwd":
            print(f"当前路径: {current_path}")
            print("探查可访问路径...")
            result = await client.explore_paths()
            if isinstance(result, dict):
                print(result["text"])
            else:
                print(result)
                
        # 现有命令处理保持不变...
        elif command == "search" and len(parts) >= 3:
            pattern = parts[1]
            directory = " ".join(parts[2:])
            print("搜索中...")
            result = await client.search_files(pattern, directory)
            print(result)
            
        # 处理文件信息获取
        elif command == "info" and len(parts) >= 2:
            path = " ".join(parts[1:])
            # 处理相对路径
            if not os.path.isabs(path):
                path = os.path.join(current_path, path)
            
            print("获取信息中...")
            result = await client.get_file_info(path)
            if isinstance(result, dict):
                print(result["text"])
                if result["resources"]:
                    print("\n可用资源:")
                    for res in result["resources"]:
                        print(f"- {res['name']}: {res['uri']}")
            else:
                print(result)
                
        # 处理文件读取
        elif command == "read" and len(parts) >= 2:
            path = " ".join(parts[1:])
            # 处理相对路径
            if not os.path.isabs(path):
                path = os.path.join(current_path, path)
            
            print("读取中...")
            content = await client.read_file_resource(path)
            print("\n--- 文件内容 ---")
            print(content)
            print("--- 内容结束 ---")
            
        # 更新当前路径
        elif command == "cd" and len(parts) >= 2:
            new_path = " ".join(parts[1:])
            
            # 处理相对路径
            if not os.path.isabs(new_path):
                new_path = os.path.join(current_path, new_path)
                
            # 验证路径是否可访问
            result = await client.list_directory(new_path)
            if not result.startswith("错误") and not result.startswith("访问被拒绝"):
                current_path = new_path
                print(f"当前目录已更改为: {current_path}")
            else:
                print(result)
            
        else:
            print("未知命令或参数不足")

async def main():
    """主函数"""
    if len(sys.argv) < 2:
        print(f"用法: python {sys.argv[0]} <服务器脚本路径>")
        return
        
    server_path = sys.argv[1]
    
    # 创建客户端实例
    client = FileExplorerClient()
    
    try:
        # 连接到服务器
        connected = await client.connect(server_path)
        if not connected:
            return
            
        # 进入交互模式
        await interactive_mode(client)
            
    finally:
        # 清理资源
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())