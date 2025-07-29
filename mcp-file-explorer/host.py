#!/usr/bin/env python
import os
import sys
import asyncio
import json
import subprocess
import argparse
from pathlib import Path

class MCPHost:
    """MCP主机实现，负责管理服务器和客户端"""
    
    def __init__(self, config_path=None):
        """初始化MCP主机"""
        self.config_path = config_path or os.path.expanduser("~/mcp_config.json")
        self.servers = {}
        self.server_processes = {}
        self.load_config()
        
    def load_config(self):
        """从配置文件加载服务器配置"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.servers = config.get('mcpServers', {})
                    print(f"已从 {self.config_path} 加载 {len(self.servers)} 个服务器配置")
            else:
                print(f"配置文件不存在: {self.config_path}")
                self.servers = {}
        except Exception as e:
            print(f"加载配置文件失败: {str(e)}")
            self.servers = {}
            
    def save_config(self):
        """保存服务器配置到配置文件"""
        try:
            config = {'mcpServers': self.servers}
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            print(f"配置已保存到 {self.config_path}")
        except Exception as e:
            print(f"保存配置文件失败: {str(e)}")
            
    def add_server(self, name, command, args=None, env=None):
        """添加一个新的服务器配置"""
        self.servers[name] = {
            'command': command,
            'args': args or [],
            'env': env or {}
        }
        print(f"已添加服务器 '{name}'")
        self.save_config()
        
    def remove_server(self, name):
        """移除服务器配置"""
        if name in self.servers:
            del self.servers[name]
            print(f"已移除服务器 '{name}'")
            self.save_config()
        else:
            print(f"服务器 '{name}' 不存在")
            
    def list_servers(self):
        """列出所有已配置的服务器"""
        if not self.servers:
            print("没有配置任何MCP服务器")
            return
            
        print("\n已配置的MCP服务器:")
        for name, config in self.servers.items():
            cmd = config['command']
            args = ' '.join(config['args']) if config['args'] else ''
            print(f"- {name}: {cmd} {args}")
        print()
        
    def start_server(self, name):
        """启动指定的服务器"""
        if name not in self.servers:
            print(f"服务器 '{name}' 不存在")
            return False
            
        if name in self.server_processes:
            print(f"服务器 '{name}' 已经在运行")
            return True
            
        config = self.servers[name]
        cmd = [config['command']] + config['args']
        env = os.environ.copy()
        env.update(config['env'])
        
        try:
            print(f"启动服务器 '{name}'...")
            process = subprocess.Popen(
                cmd, 
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.server_processes[name] = process
            print(f"服务器 '{name}' 已启动")
            return True
        except Exception as e:
            print(f"启动服务器 '{name}' 失败: {str(e)}")
            return False
            
    def stop_server(self, name):
        """停止指定的服务器"""
        if name not in self.server_processes:
            print(f"服务器 '{name}' 未运行")
            return
            
        try:
            process = self.server_processes[name]
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                
            del self.server_processes[name]
            print(f"服务器 '{name}' 已停止")
        except Exception as e:
            print(f"停止服务器 '{name}' 失败: {str(e)}")
            
    def stop_all_servers(self):
        """停止所有运行的服务器"""
        server_names = list(self.server_processes.keys())
        for name in server_names:
            self.stop_server(name)
            
    def start_client(self, client_script, server_script):
        """启动MCP客户端"""
        try:
            cmd = [sys.executable, client_script, server_script]
            subprocess.Popen(cmd)
            print(f"已启动客户端: {client_script} 连接到 {server_script}")
        except Exception as e:
            print(f"启动客户端失败: {str(e)}")
            
    def start_gui_client(self, server_name):
        """启动带GUI界面的客户端"""
        if server_name not in self.servers:
            print(f"服务器 '{server_name}' 不存在")
            return
            
        # 假设我们有一个GUI启动脚本
        # 在实际应用中，这里应该导入gui_client模块并直接调用
        server_script = Path(__file__).parent / "server" / "server.py"
        if not server_script.exists():
            print(f"找不到服务器脚本: {server_script}")
            return
            
        try:
            cmd = [
                sys.executable, 
                str(Path(__file__).parent / "client" / "gui_client.py"), 
                str(server_script)
            ]
            subprocess.Popen(cmd)
            print(f"已启动GUI客户端连接到服务器 '{server_name}'")
        except Exception as e:
            print(f"启动GUI客户端失败: {str(e)}")
    
    def run_interactive(self):
        """运行交互式命令行界面"""
        print("\n=== MCP主机管理界面 ===")
        print("命令:")
        print("  list - 列出所有已配置的服务器")
        print("  add <名称> <命令> [参数...] - 添加服务器配置")
        print("  remove <名称> - 移除服务器配置")
        print("  start <名称> - 启动服务器")
        print("  stop <名称> - 停止服务器")
        print("  client <名称> - 启动命令行客户端")
        print("  gui <名称> - 启动GUI客户端")
        print("  exit - 退出程序")
        print("========================\n")
        
        while True:
            cmd = input("> ").strip()
            
            if cmd == "exit":
                self.stop_all_servers()
                break
                
            parts = cmd.split()
            if len(parts) == 0:
                continue
                
            command = parts[0].lower()
            
            if command == "list":
                self.list_servers()
                
            elif command == "add" and len(parts) >= 3:
                name = parts[1]
                cmd_name = parts[2]
                args = parts[3:] if len(parts) > 3 else []
                self.add_server(name, cmd_name, args)
                
            elif command == "remove" and len(parts) >= 2:
                name = parts[1]
                self.remove_server(name)
                
            elif command == "start" and len(parts) >= 2:
                name = parts[1]
                self.start_server(name)
                
            elif command == "stop" and len(parts) >= 2:
                name = parts[1]
                self.stop_server(name)
                
            elif command == "client" and len(parts) >= 2:
                name = parts[1]
                if name in self.servers:
                    # 假设每个服务器对应一个服务器脚本
                    server_script = self.servers[name].get("script", "server/server.py")
                    self.start_client("client/client.py", server_script)
                else:
                    print(f"服务器 '{name}' 不存在")
                    
            elif command == "gui" and len(parts) >= 2:
                name = parts[1]
                self.start_gui_client(name)
                
            else:
                print("未知命令或参数不足")
                
    def __del__(self):
        """析构函数，确保所有服务器都被停止"""
        self.stop_all_servers()

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MCP主机")
    parser.add_argument("--config", help="配置文件路径")
    args = parser.parse_args()
    
    host = MCPHost(args.config)
    try:
        host.run_interactive()
    except KeyboardInterrupt:
        print("\n收到中断信号，正在关闭...")
    finally:
        host.stop_all_servers()

if __name__ == "__main__":
    main()
