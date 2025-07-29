import os
import json
import asyncio
import sys
from typing import Dict, Any, List, Optional
from openai import OpenAI  # 修改为使用OpenAI库
from dotenv import load_dotenv
import threading

# 导入基础客户端类
from .client import FileExplorerClient

# 加载环境变量
load_dotenv()

class FileExplorerClientWithArkLLM(FileExplorerClient):
    """使用火山引擎方舟API集成的MCP客户端"""
    
    def __init__(self, 
                 api_key=None,
                 base_url="https://ark.cn-beijing.volces.com/api/v3",
                 model_id="doubao-1-5-lite-32k-250115"):
        """初始化客户端"""
        super().__init__()
        
        # 初始化方舟API客户端，使用OpenAI库
        self.api_key = api_key or os.environ.get("ARK_API_KEY")
        self.base_url = base_url
        self.model_id = model_id
        
        if self.api_key:
            self.client = OpenAI(  # 修改为使用OpenAI客户端
                base_url=self.base_url,
                api_key=self.api_key
            )
            print(f"已初始化方舟API客户端 (模型: {self.model_id})")
        else:
            self.client = None
            print("警告: 未提供ARK_API_KEY，LLM功能将不可用")
            
        # 保存会话历史
        self.chat_history = [
            {
                "role": "system", 
                "content": """你是一个文件系统AI助手，可以通过工具帮助用户处理文件操作。
                当用户询问文件相关问题时，你应该使用可用工具来完成操作。
                请分析用户的意图，选择正确的工具，并以易于理解的方式呈现结果。
                如果用户提出简短的回复如"需要"、"是"等，请理解为用户想要继续上一个操作。
                工具调用的输出将作为单独的消息提供给你。"""
            }
        ]
        
        # 跟踪上下文状态
        self.last_mentioned_path = None
        
        # 运行标志
        self.running = True
        self.input_queue = asyncio.Queue()
    
    async def process_with_llm(self, query):
        """使用方舟API处理查询并决定调用哪个工具"""
        if not self.client:
            return "无法处理：未配置方舟API密钥"
        
        if not self.session:
            return "客户端未连接到服务器"
            
        # 如果是简短回复，扩展查询内容
        short_responses = {"是", "需要", "好的", "好", "可以", "嗯", "要", "对", "请", "确认"}
        if query.strip().lower() in short_responses:
            if self.last_mentioned_path:
                enhanced_query = f"是的，{query}。请继续执行上一个操作，并展示{self.last_mentioned_path}目录中的内容。"
                print(f"[扩展简短回复] {query} -> {enhanced_query}")
                query = enhanced_query
            else:
                enhanced_query = f"是的，{query}。请继续执行上一个提到的操作。"
                print(f"[扩展简短回复] {query} -> {enhanced_query}")
                query = enhanced_query
            
        try:
            # 获取工具定义
            tools_response = await self.session.list_tools()
            tools = []
            
            for tool in tools_response.tools:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema
                    }
                })
            
            # 添加用户消息到历史
            self.chat_history.append({"role": "user", "content": query})
            
            # 同步调用方舟API
            print("发送请求到方舟API...")
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=self.chat_history,
                tools=tools,
                tool_choice="auto",
                temperature=0.7,
                max_tokens=1024
            )
            
            # 处理响应
            result = ""
            assistant_message = response.choices[0].message
            
            # 保存助手消息到历史
            history_message = {"role": "assistant"}
            if assistant_message.content:
                history_message["content"] = assistant_message.content
            if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                history_message["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function", 
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    } for tc in assistant_message.tool_calls
                ]
            self.chat_history.append(history_message)
            
            # 处理文本响应
            if assistant_message.content:
                result += assistant_message.content + "\n"
                
            # 处理工具调用
            if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        tool_args = json.loads(tool_call.function.arguments)
                        
                        # 更新上下文状态
                        if tool_name in ["explore-paths", "list-directory"]:
                            if "path" in tool_args:
                                self.last_mentioned_path = tool_args["path"]
                            elif "base_path" in tool_args:
                                self.last_mentioned_path = tool_args["base_path"]
                        
                        # 调用工具
                        print(f"调用工具: {tool_name}，参数: {tool_args}")
                        tool_result = await self.session.call_tool(tool_name, tool_args)
                        
                        # 格式化结果
                        tool_content = ""
                        for content in tool_result.content:
                            if hasattr(content, 'text'):
                                tool_content += content.text + "\n"
                        
                        print(f"工具结果:\n{tool_content}")
                        
                        # 添加工具结果到历史
                        self.chat_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_content
                        })
                        
                        # 将工具结果发送给LLM获取最终回复
                        print("处理工具调用结果...")
                        follow_up_response = self.client.chat.completions.create(
                            model=self.model_id,
                            messages=self.chat_history,
                            temperature=0.7,
                            max_tokens=1024
                        )
                        
                        # 添加最终回复到历史
                        final_reply = follow_up_response.choices[0].message.content
                        self.chat_history.append({
                            "role": "assistant",
                            "content": final_reply
                        })
                        
                        result = final_reply
                        
                    except Exception as e:
                        error_msg = f"工具 {tool_name} 调用失败: {str(e)}"
                        print(error_msg)
                        import traceback
                        traceback.print_exc()
                        
                        # 添加错误信息到历史
                        self.chat_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": error_msg
                        })
                        
                        result += f"\n{error_msg}\n"
            
            return result
            
        except Exception as e:
            error_msg = f"处理查询时出错: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            return error_msg
    
    async def input_reader(self):
        """从控制台读取输入的异步函数"""
        while self.running:
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                line = line.strip()
                if line:
                    await self.input_queue.put(line)
            except Exception as e:
                print(f"读取输入时出错: {e}")
                
    async def interactive_llm_loop(self):
        """运行交互式LLM对话循环"""
        print("\n===== 交互模式已启动 =====")
        print("请输入您的问题，系统将等待完整输入后处理。")
        print("输入'quit'或'exit'退出。")
        
        # 简单的输入循环，更可靠的方式
        while True:
            try:
                # 直接使用input()，而不是异步输入队列
                query = input("\n问题> ").strip()
                
                if not query:
                    continue
                    
                if query.lower() in ["quit", "exit"]:
                    break
                
                print("AI思考中...")
                response = await self.process_with_llm(query)
                print("\n" + response)
                
            except KeyboardInterrupt:
                print("\n程序被用户中断")
                break
                
            except Exception as e:
                print(f"处理查询时出错: {e}")
                import traceback
                traceback.print_exc()
