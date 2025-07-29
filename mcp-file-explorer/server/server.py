import os
import glob
import json
import asyncio
from typing import List, Dict, Any, Optional
import mimetypes
from mcp.server import Server, NotificationOptions
import mcp.types as types
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
import pathlib
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mcp_server.log')
    ]
)
logger = logging.getLogger('mcp_server')

# 初始化MCP服务器
server = Server("file-explorer")

# 定义允许访问的根目录（出于安全考虑）
ALLOWED_ROOTS = [
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~"),  # 用户主目录
    os.getcwd(),  # 当前工作目录
]

# 工具列表处理器
@server.list_tools()
async def list_tools() -> List[types.Tool]:
    """列出可用工具"""
    return [
        types.Tool(
            name="search-files",
            description="搜索指定目录下的文件",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式，支持通配符（如*.txt）"
                    },
                    "directory": {
                        "type": "string",
                        "description": "要搜索的目录（必须在允许的根目录下）"
                    }
                },
                "required": ["pattern", "directory"]
            }
        ),
        types.Tool(
            name="file-info",
            description="获取文件的详细信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    }
                },
                "required": ["path"]
            }
        ),
        # 新增的路径探查工具
        types.Tool(
            name="explore-paths",
            description="探查并列出可访问的路径",
            inputSchema={
                "type": "object",
                "properties": {
                    "base_path": {
                        "type": "string",
                        "description": "基础路径（可选，默认为当前工作目录）"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "探查深度（可选，默认为1）"
                    }
                }
            }
        ),
        # 添加目录列表工具
        types.Tool(
            name="list-directory",
            description="列出指定目录下的内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出内容的目录路径"
                    }
                },
                "required": ["path"]
            }
        )
    ]

# 资源列表处理器
@server.list_resources()
async def list_resources() -> List[types.Resource]:
    """列出可用资源"""
    resources = []
    
    # 修复：正确创建资源模板
    # 旧代码：
    # resources.append(
    #     types.Resource(
    #         uriTemplate="file://{path}",
    #         name="文件内容",
    #         description="访问指定路径的文件内容"
    #     )
    # )
    
    # 新代码：
    resources.append(
        types.Resource(
            uri="file://template",  # 提供一个基础URI作为模板标识符
            name="文件内容",
            description="访问指定路径的文件内容",
            # 使用uriTemplate作为额外属性
            uriTemplate="file://{path}"
        )
    )
    
    return resources

# 读取资源处理器
@server.read_resource()
async def read_resource(uri: str) -> List[Dict[str, Any]]:
    """读取资源内容"""
    # 确保uri是字符串
    uri_str = str(uri)  # 转换AnyUrl对象为字符串
    
    if uri_str.startswith("file://"):
        path = uri_str[7:]
        
        # 安全检查：确保路径在允许的目录下
        if not is_path_allowed(path):
            return [{"uri": uri_str, "text": "访问被拒绝：路径超出允许范围", "mimeType": "text/plain"}]
        
        try:
            if os.path.isdir(path):
                # 如果是目录，列出内容
                files = os.listdir(path)
                content = "\n".join(files)
                return [{"uri": uri_str, "text": f"目录内容:\n{content}", "mimeType": "text/plain"}]
            else:
                # 如果是文件，读取内容
                mime_type, _ = mimetypes.guess_type(path)
                mime_type = mime_type or "application/octet-stream"
                
                # 对于文本文件，读取内容
                if mime_type.startswith("text/") or mime_type in ["application/json", "application/xml"]:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(10000)  # 限制大小
                        if len(content) >= 10000:
                            content += "\n... (文件过大，仅显示部分内容)"
                    return [{"uri": uri_str, "text": content, "mimeType": mime_type}]
                else:
                    # 对于二进制文件，仅返回元信息
                    file_size = os.path.getsize(path)
                    return [{"uri": uri_str, "text": f"二进制文件 ({mime_type}), 大小: {file_size} 字节", "mimeType": "text/plain"}]
                
        except Exception as e:
            return [{"uri": uri_str, "text": f"读取文件错误: {str(e)}", "mimeType": "text/plain"}]
    
    return [{"uri": uri_str, "text": "不支持的URI类型", "mimeType": "text/plain"}]

# 工具调用处理器
@server.call_tool()
async def call_tool(
    name: str, arguments: Dict[str, Any]
) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """处理工具调用"""
    logger.debug(f"工具调用: {name}, 参数: {arguments}")
    
    if name == "search-files":
        pattern = arguments.get("pattern", "")
        directory = arguments.get("directory", "")
        
        # 安全检查
        if not is_path_allowed(directory):
            return [types.TextContent(
                type="text", 
                text="访问被拒绝：指定的目录超出允许范围"
            )]
        
        try:
            search_path = os.path.join(directory, pattern)
            files = glob.glob(search_path)
            
            if not files:
                return [types.TextContent(
                    type="text", 
                    text=f"没有找到匹配 '{pattern}' 的文件"
                )]
            
            result = f"找到 {len(files)} 个匹配项:\n\n"
            for file in files[:20]:  # 限制结果数量
                rel_path = os.path.relpath(file, directory)
                try:
                    size = os.path.getsize(file)
                    mtime = os.path.getmtime(file)
                    result += f"- {rel_path} ({size} 字节, 修改时间: {mtime})\n"
                except:
                    result += f"- {rel_path} (无法获取文件信息)\n"
            
            if len(files) > 20:
                result += f"\n... 共 {len(files)} 个结果，仅显示前20个"
                
            return [types.TextContent(type="text", text=result)]
        except Exception as e:
            # 确保即使发生错误也返回有意义的信息
            return [types.TextContent(
                type="text", 
                text=f"搜索错误: {str(e)}\n路径: {directory}\n模式: {pattern}"
            )]
            
    elif name == "file-info":
        path = arguments.get("path", "")
        
        # 安全检查
        if not is_path_allowed(path):
            return [types.TextContent(
                type="text", 
                text="访问被拒绝：指定的文件路径超出允许范围"
            )]
        
        try:
            if not os.path.exists(path):
                return [types.TextContent(type="text", text=f"文件不存在: {path}")]
                
            stats = os.stat(path)
            mime_type, _ = mimetypes.guess_type(path)
            
            info = {
                "path": path,
                "size": stats.st_size,
                "created": stats.st_ctime,
                "modified": stats.st_mtime,
                "accessed": stats.st_atime,
                "is_directory": os.path.isdir(path),
                "mime_type": mime_type or "未知"
            }
            
            # 对于文本文件，添加预览
            if mime_type and mime_type.startswith("text/"):
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        preview = f.read(500)
                        if len(preview) >= 500:
                            preview += "...(截断)"
                    info["preview"] = preview
                except:
                    info["preview"] = "无法读取预览"
            
            result = f"文件信息 - {path}\n"
            result += f"类型: {'目录' if info['is_directory'] else '文件'}\n"
            result += f"MIME类型: {info['mime_type']}\n"
            result += f"大小: {info['size']} 字节\n"
            result += f"创建时间: {info['created']}\n"
            result += f"修改时间: {info['modified']}\n"
            result += f"访问时间: {info['accessed']}\n"
            
            if "preview" in info:
                result += f"\n预览:\n{info['preview']}\n"
                
            # 为文件内容创建资源引用
            resource_uri = f"file://{path}"
            
            # 返回文本内容和嵌入资源
            return [
                types.TextContent(type="text", text=result),
                types.EmbeddedResource(
                    type="resource",
                    resource={  # 使用字典而不是Resource对象
                        "uri": resource_uri,
                        "name": f"文件内容: {os.path.basename(path)}",
                        "description": "查看文件完整内容"
                    }
                )
            ]
            
        except Exception as e:
            return [types.TextContent(type="text", text=f"获取文件信息错误: {str(e)}")]
            
    # 添加新工具：explore-paths
    elif name == "explore-paths":
        base_path = arguments.get("base_path", os.getcwd())
        depth = arguments.get("depth", 1)
        
        try:
            # 如果基础路径未指定，列出所有允许的根目录
            if not base_path or base_path == ".":
                result = "可访问的根目录:\n\n"
                for root in ALLOWED_ROOTS:
                    if os.path.exists(root):
                        result += f"- {root}\n"
                
                return [types.TextContent(type="text", text=result)]
            
            # 安全检查
            if not is_path_allowed(base_path):
                return [types.TextContent(
                    type="text", 
                    text=f"访问被拒绝：路径 {base_path} 超出允许范围"
                )]
                
            # 探查指定路径
            path_obj = pathlib.Path(base_path)
            if not path_obj.exists():
                return [types.TextContent(
                    type="text", 
                    text=f"路径不存在: {base_path}"
                )]
                
            if path_obj.is_file():
                # 如果是文件，展示文件信息
                stats = path_obj.stat()
                result = f"文件信息: {path_obj}\n"
                result += f"大小: {stats.st_size} 字节\n"
                result += f"修改时间: {stats.st_mtime}\n"
                
                # 添加文件资源引用
                resource_uri = f"file://{path_obj}"
                
                return [
                    types.TextContent(type="text", text=result),
                    types.EmbeddedResource(
                        type="resource",
                        resource=types.Resource(
                            uri=resource_uri,
                            name=f"文件内容: {path_obj.name}",
                            description=f"查看文件完整内容"
                        )
                    )
                ]
            else:
                # 如果是目录，列出内容
                result = f"目录内容: {path_obj}\n\n"
                
                # 列出子目录和文件
                dirs = []
                files = []
                
                try:
                    # 限制列表项数量，避免过多
                    max_items = 50
                    count = 0
                    
                    for item in path_obj.iterdir():
                        if count >= max_items:
                            break
                            
                        # 区分目录和文件
                        try:
                            is_dir = item.is_dir()
                            if is_dir:
                                dirs.append(f"📁 {item.name}")
                            else:
                                size = item.stat().st_size
                                files.append(f"📄 {item.name} ({size} 字节)")
                            count += 1
                        except:
                            continue
                            
                    # 先显示目录，再显示文件
                    if dirs:
                        result += "目录:\n"
                        for d in sorted(dirs):
                            result += f"- {d}\n"
                        result += "\n"
                        
                    if files:
                        result += "文件:\n"
                        for f in sorted(files):
                            result += f"- {f}\n"
                            
                    # 如果内容过多
                    if count >= max_items:
                        result += f"\n(仅显示前{max_items}项，目录可能包含更多内容)"
                        
                    # 显示父目录和导航提示
                    result += f"\n\n导航:\n"
                    
                    if path_obj.parent != path_obj:  # 不是根目录
                        parent_path = path_obj.parent
                        result += f"- 上级目录: {parent_path}\n"
                        
                    result += f"\n提示: 使用 'explore-paths' 工具可以继续浏览目录"
                        
                    return [types.TextContent(type="text", text=result)]
                        
                except Exception as e:
                    return [types.TextContent(type="text", text=f"读取目录内容时出错: {str(e)}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"路径探查错误: {str(e)}")]
            
    # 添加新工具：list-directory
    elif name == "list-directory":
        path = arguments.get("path", os.getcwd())
        
        # 安全检查
        if not is_path_allowed(path):
            return [types.TextContent(
                type="text", 
                text=f"访问被拒绝：指定的目录路径超出允许范围"
            )]
            
        try:
            path_obj = pathlib.Path(path)
            if not path_obj.exists():
                return [types.TextContent(type="text", text=f"路径不存在: {path}")]
                
            if not path_obj.is_dir():
                return [types.TextContent(type="text", text=f"指定路径不是目录: {path}")]
                
            # 列出目录内容
            items = list(path_obj.iterdir())
            
            result = f"目录 {path} 中有 {len(items)} 个项目:\n\n"
            
            # 分类并排序
            dirs = []
            files = []
            
            for item in items:
                try:
                    if item.is_dir():
                        dirs.append(item)
                    else:
                        files.append(item)
                except:
                    continue
                    
            # 显示目录
            if dirs:
                result += "目录:\n"
                for d in sorted(dirs, key=lambda x: x.name.lower()):
                    result += f"- 📁 {d.name}\n"
                result += "\n"
                
            # 显示文件
            if files:
                result += "文件:\n"
                for f in sorted(files, key=lambda x: x.name.lower()):
                    try:
                        size = f.stat().st_size
                        result += f"- 📄 {f.name} ({size} 字节)\n"
                    except:
                        result += f"- 📄 {f.name}\n"
                        
            return [types.TextContent(type="text", text=result)]
            
        except Exception as e:
            return [types.TextContent(type="text", text=f"列出目录内容时出错: {str(e)}")]
            
    # 如果是未知工具，返回错误
    return [types.TextContent(type="text", text=f"未知工具: {name}")]

def is_path_allowed(path: str) -> bool:
    """安全检查：验证路径是否在允许的目录范围内"""
    try:
        # 规范化路径
        real_path = os.path.realpath(path)
        
        # 检查路径是否在任意允许的根目录下
        for allowed_root in ALLOWED_ROOTS:
            real_allowed = os.path.realpath(allowed_root)
            if real_path.startswith(real_allowed):
                return True
                
        return False
    except:
        return False

async def main():
    """主函数：启动MCP服务器"""
    print("启动文件浏览MCP服务器...")
    
    try:
        # 运行服务器
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="file-explorer",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    except Exception as e:
        print(f"服务器错误: {str(e)}")
        # 在开发阶段，可以打印完整的堆栈跟踪
        import traceback
        traceback.print_exc()

async def test_tools():
    """测试工具功能"""
    print("测试工具功能...")
    
    # 测试search-files
    print("\n测试search-files:")
    result = await call_tool("search-files", {"pattern": "*.py", "directory": "."})
    for item in result:
        if hasattr(item, 'text'):
            print(item.text)
    
    # 测试file-info
    print("\n测试file-info:")
    result = await call_tool("file-info", {"path": "server.py"})
    for item in result:
        if hasattr(item, 'text'):
            print(item.text)
    
    # 测试explore-paths
    print("\n测试explore-paths:")
    result = await call_tool("explore-paths", {"base_path": "."})
    for item in result:
        if hasattr(item, 'text'):
            print(item.text)
    
    # 测试list-directory
    print("\n测试list-directory:")
    result = await call_tool("list-directory", {"path": "."})
    for item in result:
        if hasattr(item, 'text'):
            print(item.text)

# 添加命令行测试选项
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        asyncio.run(test_tools())
    else:
        # 正常启动服务器
        asyncio.run(main())
