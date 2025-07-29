#!/usr/bin/env python
import os
import sys
import json
import asyncio
import subprocess
import threading
import time
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# 存储服务器进程
server_process = None
# 全局MCP客户端会话
mcp_session = None
# 全局LLM客户端
llm_client = None
# 会话历史
chat_history = []

# 创建必要的目录和文件
os.makedirs('templates', exist_ok=True)
os.makedirs('static', exist_ok=True)

# 创建HTML模板
with open('templates/index.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP文件浏览助手</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
        }
        .container {
            display: flex;
            flex-direction: column;
            height: 90vh;
        }
        .chat-container {
            flex-grow: 1;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 10px;
            margin-bottom: 15px;
            background: #f9f9f9;
        }
        .input-container {
            display: flex;
            gap: 10px;
        }
        #user-input {
            flex-grow: 1;
            padding: 10px;
            border-radius: 5px;
            border: 1px solid #ddd;
        }
        button {
            padding: 10px 15px;
            background: #4a69bd;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }
        button:hover {
            background: #1e3799;
        }
        .message {
            margin-bottom: 10px;
            padding: 10px;
            border-radius: 5px;
        }
        .user {
            background: #d6eaff;
            margin-left: 20%;
            margin-right: 0;
        }
        .assistant {
            background: #e6e6e6;
            margin-right: 20%;
            margin-left: 0;
        }
        .system {
            background: #ffeecc;
            margin: 5px 10%;
            font-style: italic;
            text-align: center;
        }
        .tool-call {
            background: #e0f7fa;
            border-left: 3px solid #00acc1;
            padding-left: 10px;
            margin: 5px 0;
        }
        pre {
            background: #f1f1f1;
            padding: 10px;
            border-radius: 5px;
            overflow-x: auto;
        }
        .status-bar {
            margin-top: 10px;
            padding: 5px;
            border-radius: 3px;
            background: #f0f0f0;
            font-size: 0.9em;
            color: #555;
        }
    </style>
</head>
<body>
    <h1>MCP文件浏览助手</h1>
    <div class="status-bar" id="status">
        服务器状态：准备中...
    </div>
    <div class="container">
        <div class="chat-container" id="chat-container">
            <div class="message system">系统已启动，请输入您的问题</div>
        </div>
        <div class="input-container">
            <input type="text" id="user-input" placeholder="输入您的问题，如'查找当前目录下的Python文件'" />
            <button onclick="sendMessage()">发送</button>
        </div>
    </div>

    <script>
        const chatContainer = document.getElementById('chat-container');
        const userInput = document.getElementById('user-input');
        const statusBar = document.getElementById('status');

        function addMessage(text, sender) {
            const messageDiv = document.createElement('div');
            messageDiv.classList.add('message', sender);
            
            // 检查是否包含代码块
            if (text.includes('```')) {
                const parts = text.split(/```([\s\S]*?)```/);
                let content = '';
                
                for (let i = 0; i < parts.length; i++) {
                    if (i % 2 === 0) {
                        // 普通文本
                        content += parts[i];
                    } else {
                        // 代码块
                        content += `<pre><code>${parts[i]}</code></pre>`;
                    }
                }
                messageDiv.innerHTML = content;
            } else {
                messageDiv.textContent = text;
            }
            
            chatContainer.appendChild(messageDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        function addToolCall(toolName, args, result) {
            const toolDiv = document.createElement('div');
            toolDiv.classList.add('tool-call');
            toolDiv.innerHTML = `
                <strong>调用工具:</strong> ${toolName}<br>
                <strong>参数:</strong> <pre>${JSON.stringify(args, null, 2)}</pre>
                <strong>结果:</strong><br>${result.replace(/\\n/g, '<br>')}
            `;
            chatContainer.appendChild(toolDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        function updateStatus(status) {
            statusBar.textContent = `服务器状态：${status}`;
        }

        function sendMessage() {
            const message = userInput.value.trim();
            if (!message) return;

            // 添加用户消息到界面
            addMessage(message, 'user');
            userInput.value = '';
            
            // 显示加载状态
            updateStatus('处理中...');
            
            // 发送到服务器
            fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message }),
            })
            .then(response => response.json())
            .then(data => {
                // 显示工具调用（如果有）
                if (data.tool_calls && data.tool_calls.length > 0) {
                    for (const tool of data.tool_calls) {
                        addToolCall(tool.name, tool.args, tool.result);
                    }
                }
                
                // 添加助手回复
                if (data.response) {
                    addMessage(data.response, 'assistant');
                }
                
                // 更新状态
                updateStatus('就绪');
            })
            .catch(error => {
                console.error('Error:', error);
                addMessage('发生错误: ' + error.message, 'system');
                updateStatus('错误');
            });
        }
        
        // 按Enter发送消息
        userInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });

        // 页面加载时连接服务器
        window.onload = function() {
            fetch('/api/connect')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    updateStatus('已连接');
                    addMessage(`已连接到MCP服务器。可用工具: ${data.tools.join(', ')}`, 'system');
                } else {
                    updateStatus('连接失败');
                    addMessage(`连接服务器失败: ${data.error}`, 'system');
                }
            })
            .catch(error => {
                updateStatus('连接错误');
                addMessage(`连接错误: ${error.message}`, 'system');
            });
        };
    </script>
</body>
</html>
''')

# 创建CSS文件
with open('static/style.css', 'w') as f:
    f.write('''
/* 可以添加额外的样式 */
''')

# 导入客户端模块
class SimpleMcpClient:
    """简化的MCP客户端，直接与服务器进程通信"""
    def __init__(self, server_script):
        self.server_script = server_script
        self.connected = False
        self.tools = []
    
    async def connect(self):
        """连接到MCP服务器"""
        # 这里应该实际连接到MCP服务器
        # 简化实现
        return True
    
    async def list_tools(self):
        """获取可用工具列表"""
        # 实际实现应该从服务器获取工具列表
        return ['search-files', 'file-info', 'explore-paths', 'list-directory']
    
    async def call_tool(self, tool_name, args):
        """调用MCP工具"""
        # 实际实现应该直接调用服务器工具
        # 使用subprocess执行server的direct_tool调用
        result = ""
        
        # 这里是简化的工具实现
        if tool_name == 'list-directory':
            path = args.get('path', '.')
            try:
                items = os.listdir(path)
                result = f"目录 {path} 包含 {len(items)} 项:\n\n"
                for item in items:
                    full_path = os.path.join(path, item)
                    if os.path.isdir(full_path):
                        result += f"📁 {item}/\n"
                    else:
                        size = os.path.getsize(full_path)
                        result += f"📄 {item} ({size} 字节)\n"
            except Exception as e:
                result = f"列出目录错误: {str(e)}"
        
        elif tool_name == 'search-files':
            pattern = args.get('pattern', '*')
            directory = args.get('directory', '.')
            import glob
            
            try:
                files = glob.glob(os.path.join(directory, pattern))
                result = f"找到 {len(files)} 个匹配项:\n\n"
                for file in files[:20]:
                    size = os.path.getsize(file)
                    mtime = os.path.getmtime(file)
                    result += f"- {os.path.basename(file)} ({size} 字节, 修改时间: {mtime})\n"
            except Exception as e:
                result = f"搜索文件错误: {str(e)}"
        
        elif tool_name == 'file-info':
            path = args.get('path', '')
            try:
                if not os.path.exists(path):
                    result = f"文件不存在: {path}"
                else:
                    stats = os.stat(path)
                    result = f"文件: {path}\n"
                    result += f"大小: {stats.st_size} 字节\n"
                    result += f"修改时间: {stats.st_mtime}\n"
                    result += f"创建时间: {stats.st_ctime}\n"
                    
                    # 如果是文本文件，添加预览
                    if path.endswith(('.txt', '.py', '.md', '.json', '.html', '.css', '.js')):
                        try:
                            with open(path, 'r', encoding='utf-8') as f:
                                content = f.read(1000)
                                if len(content) >= 1000:
                                    content += "...(内容已截断)"
                                result += f"\n内容预览:\n{content}"
                        except:
                            result += "\n无法读取文件内容"
            except Exception as e:
                result = f"获取文件信息错误: {str(e)}"
        
        elif tool_name == 'explore-paths':
            base_path = args.get('base_path', '.')
            try:
                if os.path.isdir(base_path):
                    items = os.listdir(base_path)
                    result = f"路径 {base_path} 包含 {len(items)} 项"
                else:
                    result = f"路径 {base_path} 不是目录"
            except Exception as e:
                result = f"探索路径错误: {str(e)}"
        
        else:
            result = f"未知工具: {tool_name}"
            
        return result

# 初始化LLM客户端
def init_llm_client():
    """初始化LLM客户端"""
    global llm_client
    
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        print("错误: 未设置ARK_API_KEY环境变量")
        return None
        
    llm_client = OpenAI(
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key=api_key
    )
    
    return llm_client

# 启动MCP服务器
def start_mcp_server():
    """启动MCP服务器进程"""
    global server_process
    
    # 获取服务器脚本路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    server_script = os.path.join(current_dir, "server", "server.py")
    
    if not os.path.exists(server_script):
        print(f"错误: 找不到服务器脚本 {server_script}")
        return None
        
    # 启动服务器进程
    server_process = subprocess.Popen(
        [sys.executable, server_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    print(f"MCP服务器已启动 (PID: {server_process.pid})")
    
    # 等待服务器启动
    time.sleep(3)
    
    return server_script

# API路由
@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/api/connect', methods=['GET'])
def connect():
    """连接到MCP服务器"""
    global mcp_session
    
    try:
        # 启动服务器
        server_script = start_mcp_server()
        if not server_script:
            return jsonify({
                'status': 'error',
                'error': '无法启动MCP服务器'
            })
            
        # 初始化MCP客户端
        mcp_session = SimpleMcpClient(server_script)
        
        # 获取工具列表
        tools = asyncio.run(mcp_session.list_tools())
        
        # 初始化LLM客户端
        if not init_llm_client():
            return jsonify({
                'status': 'error',
                'error': '无法初始化LLM客户端'
            })
            
        # 初始化会话历史
        global chat_history
        chat_history = [{
            "role": "system", 
            "content": """你是一个文件系统AI助手，可以通过工具帮助用户处理文件操作。
            当用户询问文件相关问题时，你应该使用可用工具来完成操作。
            请分析用户的意图，选择正确的工具，并以易于理解的方式呈现结果。"""
        }]
        
        return jsonify({
            'status': 'success',
            'tools': tools
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'status': 'error',
            'error': str(e)
        })

@app.route('/api/chat', methods=['POST'])
def chat():
    """处理聊天请求"""
    global mcp_session, llm_client, chat_history
    
    # 获取消息
    data = request.json
    message = data.get('message', '')
    
    if not message:
        return jsonify({
            'status': 'error',
            'error': '消息不能为空'
        })
        
    if not mcp_session:
        return jsonify({
            'status': 'error',
            'error': 'MCP会话未初始化'
        })
        
    if not llm_client:
        return jsonify({
            'status': 'error',
            'error': 'LLM客户端未初始化'
        })
        
    # 添加用户消息到历史
    chat_history.append({
        "role": "user",
        "content": message
    })
    
    # 获取工具定义
    tools = []
    for tool_name in asyncio.run(mcp_session.list_tools()):
        tool_schema = {
            "name": tool_name,
            "description": "操作文件系统的工具"
        }
        
        # 为每个工具添加特定的描述和参数
        if tool_name == 'search-files':
            tool_schema["description"] = "搜索指定目录下的文件"
            tool_schema["parameters"] = {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式，支持通配符（如*.txt）"
                    },
                    "directory": {
                        "type": "string", 
                        "description": "要搜索的目录"
                    }
                },
                "required": ["pattern", "directory"]
            }
        elif tool_name == 'file-info':
            tool_schema["description"] = "获取文件的详细信息和内容"
            tool_schema["parameters"] = {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    }
                },
                "required": ["path"]
            }
        elif tool_name == 'explore-paths':
            tool_schema["description"] = "探查并列出可访问的路径"
            tool_schema["parameters"] = {
                "type": "object",
                "properties": {
                    "base_path": {
                        "type": "string",
                        "description": "基础路径（默认为当前目录）"
                    }
                }
            }
        elif tool_name == 'list-directory':
            tool_schema["description"] = "列出指定目录下的内容"
            tool_schema["parameters"] = {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出内容的目录路径"
                    }
                },
                "required": ["path"]
            }
        
        tools.append({
            "type": "function",
            "function": tool_schema
        })
    
    try:
        # 调用LLM
        response = llm_client.chat.completions.create(
            model="doubao-1-5-lite-32k-250115",  # 可以从环境变量获取
            messages=chat_history,
            tools=tools,
            tool_choice="auto"
        )
        
        # 获取助手消息
        assistant_message = response.choices[0].message
        assistant_content = assistant_message.content or ""
        
        # 保存助手消息到历史
        chat_history.append({
            "role": "assistant",
            "content": assistant_content
        })
        
        # 处理工具调用
        tool_results = []
        if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                
                # 调用工具
                tool_result = asyncio.run(mcp_session.call_tool(tool_name, tool_args))
                
                # 保存工具结果
                tool_results.append({
                    "name": tool_name,
                    "args": tool_args,
                    "result": tool_result
                })
                
                # 添加工具结果到历史
                chat_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result
                })
            
            # 获取最终回复
            final_response = llm_client.chat.completions.create(
                model="doubao-1-5-lite-32k-250115",
                messages=chat_history
            )
            
            final_content = final_response.choices[0].message.content
            
            # 添加最终回复到历史
            chat_history.append({
                "role": "assistant",
                "content": final_content
            })
            
            # 使用最终回复作为响应
            assistant_content = final_content
        
        return jsonify({
            'status': 'success',
            'tool_calls': tool_results,
            'response': assistant_content
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'status': 'error',
            'error': str(e)
        })

@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    """关闭服务器"""
    global server_process
    
    if server_process:
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        
        server_process = None
        
    return jsonify({
        'status': 'success',
        'message': 'MCP服务器已关闭'
    })

# 确保在应用退出时关闭服务器
def cleanup():
    """清理资源"""
    global server_process
    
    if server_process:
        print("关闭MCP服务器...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()

# 注册退出处理器
import atexit
atexit.register(cleanup)

if __name__ == '__main__':
    try:
        # 确保安装了所需的依赖
        try:
            import flask
            import openai
        except ImportError:
            print("正在安装所需依赖...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "openai", "python-dotenv"])
            print("依赖安装完成")
        
        print("启动Web服务器...")
        app.run(debug=True, host='0.0.0.0', port=5001)  # 或任何其他可用端口，如8080
    except KeyboardInterrupt:
        print("服务器被用户中断")
    finally:
        cleanup()
