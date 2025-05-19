import asyncio
import json
import base64
import time
from typing import List, Optional
from dataclasses import dataclass

import aiohttp
import requests

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.types import Resource, Tool, TextContent
import mcp.types as types

# Configuration
ROBOT_HOST = "192.168.0.157"  # Change to your robot's IP
ROBOT_PORT = 5000
MAX_CACHED_FRAMES = 5
FRAME_CACHE_TTL = 2.0  # seconds

@dataclass
class CachedFrame:
    data: bytes
    timestamp: float
    frame_id: int

class SimplifiedRobotMCPServer:
    def __init__(self):
        self.server = Server("robot-controller")
        
        # Frame caching
        self.frame_cache = []
        self.frame_counter = 0
        self.frame_lock = asyncio.Lock()
        
        # HTTP session for reuse
        self.http_session: Optional[aiohttp.ClientSession] = None
        
        self.setup_handlers()
    
    async def start_services(self):
        """Start background services for optimization."""
        # Start HTTP session
        self.http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5),
            connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
        )
        
        # Start frame caching task
        asyncio.create_task(self.frame_caching_loop())
    
    async def stop_services(self):
        """Clean up resources."""
        if self.http_session:
            await self.http_session.close()
    
    async def frame_caching_loop(self):
        """Continuously cache latest frames in background."""
        while True:
            try:
                # Fetch frame from robot
                frame_data = await self.fetch_latest_frame()
                if frame_data:
                    async with self.frame_lock:
                        self.frame_counter += 1
                        cached_frame = CachedFrame(
                            data=frame_data,
                            timestamp=time.time(),
                            frame_id=self.frame_counter
                        )
                        
                        # Manage the cache size manually
                        self.frame_cache.append(cached_frame)
                        if len(self.frame_cache) > MAX_CACHED_FRAMES:
                            self.frame_cache.pop(0)
                
                # Cache frames at 10 FPS to match robot's reduced rate
                await asyncio.sleep(0.1)
                
            except Exception as e:
                print(f"Frame caching error: {e}")
                await asyncio.sleep(1)  # Back off on error
    
    async def fetch_latest_frame(self) -> Optional[bytes]:
        """Fetch a single frame from the robot's video feed."""
        try:
            url = f"http://{ROBOT_HOST}:{ROBOT_PORT}/video_feed"
            
            async with self.http_session.get(url) as response:
                if response.status != 200:
                    return None
                
                # Read the multipart response to get one frame
                boundary = b'--frame'
                chunk = await response.content.read(8192)
                
                # Find the start of image data
                start_idx = chunk.find(b'\r\n\r\n')
                if start_idx != -1:
                    start_idx += 4  # Skip the \r\n\r\n
                    
                    # Read more data to get a complete frame
                    image_data = chunk[start_idx:]
                    while len(image_data) < 50000:  # Arbitrary size for a frame
                        more_data = await response.content.read(8192)
                        if not more_data:
                            break
                        image_data += more_data
                    
                    # Find the end of this frame
                    end_idx = image_data.find(boundary)
                    if end_idx != -1:
                        image_data = image_data[:end_idx-2]  # Remove trailing \r\n
                    
                    return image_data
                
        except Exception as e:
            print(f"Error fetching frame: {e}")
        
        return None
    
    async def get_cached_frame(self) -> Optional[CachedFrame]:
        """Get the most recent cached frame."""
        async with self.frame_lock:
            if not self.frame_cache:
                return None
            
            latest_frame = self.frame_cache[-1]
            
            # Check if frame is still fresh
            if time.time() - latest_frame.timestamp > FRAME_CACHE_TTL:
                return None
            
            return latest_frame
    
    async def send_robot_command(self, direction: str) -> str:
        """Send a command to the robot via HTTP."""
        url = f"http://{ROBOT_HOST}:{ROBOT_PORT}/command/{direction}"
        
        async with self.http_session.get(url) as response:
            if response.status == 200:
                text = await response.text()
                return f"Robot moved {direction}: {text}"
            else:
                text = await response.text()
                raise Exception(f"Error {response.status}: {text}")
    
    def setup_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            return [
                Tool(
                    name="move_robot",
                    description="Move the robot in a specific direction",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "direction": {
                                "type": "string",
                                "enum": ["forward", "backward", "left", "right", "stop"],
                                "description": "Direction to move the robot"
                            }
                        },
                        "required": ["direction"]
                    }
                ),
                Tool(
                    name="get_cached_frame",
                    description="Get the most recent cached video frame (fastest)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "include_metadata": {
                                "type": "boolean",
                                "default": False,
                                "description": "Include frame metadata (timestamp, ID)"
                            }
                        }
                    }
                ),
                Tool(
                    name="get_fresh_frame",
                    description="Get a new video frame directly from robot (slower but freshest)",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="get_robot_status",
                    description="Get current robot and optimization status",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="get_performance_stats",
                    description="Get performance statistics for the MCP server",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> List[types.TextContent]:
            if name == "move_robot":
                direction = arguments["direction"]
                
                try:
                    result = await self.send_robot_command(direction)
                    return [TextContent(type="text", text=result)]
                except Exception as e:
                    return [TextContent(type="text", text=f"Movement error: {str(e)}")]
            
            elif name == "get_cached_frame":
                include_metadata = arguments.get("include_metadata", False)
                
                cached_frame = await self.get_cached_frame()
                if not cached_frame:
                    return [TextContent(
                        type="text", 
                        text="No cached frame available. Try get_fresh_frame instead."
                    )]
                
                frame_b64 = base64.b64encode(cached_frame.data).decode('utf-8')
                
                if include_metadata:
                    age = time.time() - cached_frame.timestamp
                    result = (
                        f"Cached frame #{cached_frame.frame_id}\n"
                        f"Age: {age:.2f} seconds\n"
                        f"Size: {len(cached_frame.data)} bytes\n"
                        f"Base64: data:image/jpeg;base64,{frame_b64[:100]}..."
                    )
                else:
                    result = f"data:image/jpeg;base64,{frame_b64}"
                
                return [TextContent(type="text", text=result)]
            
            elif name == "get_fresh_frame":
                try:
                    frame_data = await self.fetch_latest_frame()
                    if frame_data:
                        frame_b64 = base64.b64encode(frame_data).decode('utf-8')
                        return [TextContent(
                            type="text",
                            text=f"Fresh frame captured ({len(frame_data)} bytes)\ndata:image/jpeg;base64,{frame_b64}"
                        )]
                    else:
                        return [TextContent(type="text", text="Could not capture fresh frame")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Fresh frame error: {str(e)}")]
            
            elif name == "get_robot_status":
                try:
                    url = f"http://{ROBOT_HOST}:{ROBOT_PORT}/"
                    async with self.http_session.get(url) as response:
                        robot_online = response.status == 200
                except:
                    robot_online = False
                
                async with self.frame_lock:
                    cached_frames_count = len(self.frame_cache)
                    latest_frame_age = (
                        time.time() - self.frame_cache[-1].timestamp 
                        if self.frame_cache else None
                    )
                
                status = {
                    "robot_connection": "online" if robot_online else "offline",
                    "robot_host": ROBOT_HOST,
                    "robot_port": ROBOT_PORT,
                    "cached_frames": cached_frames_count,
                    "latest_frame_age": f"{latest_frame_age:.2f}s" if latest_frame_age else "N/A",
                    "optimizations": {
                        "frame_caching": "enabled",
                        "http_session_reuse": "enabled"
                    }
                }
                
                return [TextContent(type="text", text=json.dumps(status, indent=2))]
            
            elif name == "get_performance_stats":
                stats = {
                    "frame_cache": {
                        "max_size": MAX_CACHED_FRAMES,
                        "current_size": len(self.frame_cache),
                        "ttl_seconds": FRAME_CACHE_TTL,
                        "total_frames_cached": self.frame_counter
                    },
                    "network": {
                        "http_session_active": self.http_session is not None
                    }
                }
                
                return [TextContent(type="text", text=json.dumps(stats, indent=2))]
            
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        @self.server.list_resources()
        async def handle_list_resources() -> List[Resource]:
            return [
                Resource(
                    uri="robot://video/live_feed_url",
                    name="Live Video Feed URL",
                    description="Direct URL to the robot's video stream",
                    mimeType="text/plain"
                )
            ]

        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> str:
            if uri == "robot://video/live_feed_url":
                return f"http://{ROBOT_HOST}:{ROBOT_PORT}/video_feed"
            else:
                raise ValueError(f"Unknown resource: {uri}")

    async def run(self):
        """Run the MCP server with all optimizations."""
        from mcp.server.stdio import stdio_server
        
        # Start background services
        await self.start_services()
        
        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name="simplified-robot-controller",
                        server_version="2.0.0",
                        capabilities=self.server.get_capabilities(
                            notification_options=NotificationOptions(),
                            experimental_capabilities={},
                        ),
                    ),
                )
        finally:
            await self.stop_services()

async def main():
    print("Starting simplified robot MCP server...")
    print("Optimizations enabled:")
    print("  ✓ Frame caching (up to 5 frames, 2s TTL)")
    print("  ✓ HTTP session reuse")
    print(f"  ✓ Robot connection: http://{ROBOT_HOST}:{ROBOT_PORT}")
    print("  ✓ All commands sent immediately")
    
    server = SimplifiedRobotMCPServer()
    await server.run()

if __name__ == "__main__":
    # Install required packages if not present
    try:
        import aiohttp
    except ImportError:
        print("Missing dependencies. Install with:")
        print("pip install aiohttp")
        exit(1)
    
    asyncio.run(main())