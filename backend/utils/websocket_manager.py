"""
WebSocket Manager
Handles real-time bidirectional communication with clients
Supports rooms, broadcasting, and connection management
"""

import asyncio
import json
import uuid
from typing import Dict, Set, Any, Optional, Callable
from datetime import datetime
from collections import defaultdict
import weakref

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..utils.logger import get_logger
from ..utils.auth import verify_token
from ..config import settings

logger = get_logger(__name__)


class WebSocketMessage(BaseModel):
    """WebSocket message format"""
    type: str
    data: Any
    timestamp: datetime = datetime.utcnow()
    message_id: str = None


class ConnectionInfo:
    """Information about a WebSocket connection"""
    
    def __init__(self, websocket: WebSocket, client_id: str, user_id: Optional[str] = None):
        self.websocket = websocket
        self.client_id = client_id
        self.user_id = user_id
        self.connected_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.rooms = set()
        self.subscriptions = set()
        self.metadata = {}
    
    async def send(self, message: dict):
        """Send message to this connection"""
        try:
            await self.websocket.send_json(message)
            self.last_activity = datetime.utcnow()
        except Exception as e:
            logger.error(f"Error sending message to {self.client_id}: {e}")
    
    async def close(self, code: int = 1000, reason: str = ""):
        """Close the connection"""
        try:
            await self.websocket.close(code=code, reason=reason)
        except:
            pass


class WebSocketManager:
    """
    Manages all WebSocket connections
    Supports rooms, broadcasting, and authentication
    """
    
    def __init__(self):
        self.connections: Dict[str, ConnectionInfo] = {}
        self.user_connections: Dict[str, Set[str]] = defaultdict(set)
        self.rooms: Dict[str, Set[str]] = defaultdict(set)
        self.handlers: Dict[str, Callable] = {}
        self.ping_interval = 30  # seconds
        self.ping_timeout = 10   # seconds
        self._cleanup_task = None
        self._ping_task = None
        
        logger.info("WebSocket Manager initialized")
    
    async def start(self):
        """Start background tasks"""
        self._cleanup_task = asyncio.create_task(self._cleanup_stale_connections())
        self._ping_task = asyncio.create_task(self._ping_all())
        logger.info("WebSocket Manager started")
    
    async def stop(self):
        """Stop background tasks and close all connections"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._ping_task:
            self._ping_task.cancel()
        
        # Close all connections
        for client_id in list(self.connections.keys()):
            await self.disconnect(client_id)
        
        logger.info("WebSocket Manager stopped")
    
    async def connect(self, websocket: WebSocket, client_id: Optional[str] = None) -> str:
        """
        Accept a new WebSocket connection
        Returns client_id
        """
        await websocket.accept()
        
        if client_id is None:
            client_id = str(uuid.uuid4())
        
        # Try to authenticate
        user_id = await self._authenticate(websocket)
        
        # Store connection
        conn_info = ConnectionInfo(websocket, client_id, user_id)
        self.connections[client_id] = conn_info
        
        if user_id:
            self.user_connections[user_id].add(client_id)
        
        logger.info(f"WebSocket connected: {client_id} (user: {user_id})")
        
        # Send connection confirmation
        await self.send_to_client(client_id, {
            "type": "connection_established",
            "data": {
                "client_id": client_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
        
        return client_id
    
    async def disconnect(self, client_id: str, code: int = 1000, reason: str = ""):
        """Disconnect a client"""
        if client_id in self.connections:
            conn_info = self.connections[client_id]
            
            # Remove from rooms
            for room in list(conn_info.rooms):
                await self.leave_room(client_id, room)
            
            # Remove from user connections
            if conn_info.user_id:
                if conn_info.user_id in self.user_connections:
                    self.user_connections[conn_info.user_id].discard(client_id)
                    if not self.user_connections[conn_info.user_id]:
                        del self.user_connections[conn_info.user_id]
            
            # Close connection
            await conn_info.close(code=code, reason=reason)
            
            # Remove from connections
            del self.connections[client_id]
            
            logger.info(f"WebSocket disconnected: {client_id} (reason: {reason})")
    
    async def handle_messages(self, client_id: str):
        """
        Handle incoming messages from a client
        To be run as a task for each connection
        """
        conn_info = self.connections.get(client_id)
        if not conn_info:
            return
        
        try:
            while True:
                # Receive message
                message = await conn_info.websocket.receive_json()
                
                # Update last activity
                conn_info.last_activity = datetime.utcnow()
                
                # Process message
                await self._process_message(client_id, message)
                
        except WebSocketDisconnect:
            await self.disconnect(client_id, code=1000, reason="Client disconnected")
        except Exception as e:
            logger.error(f"Error handling messages for {client_id}: {e}")
            await self.disconnect(client_id, code=1011, reason=str(e))
    
    async def _process_message(self, client_id: str, message: dict):
        """Process an incoming message"""
        message_type = message.get("type")
        data = message.get("data", {})
        message_id = message.get("message_id", str(uuid.uuid4()))
        
        logger.debug(f"Message from {client_id}: {message_type}")
        
        # Handle system messages
        if message_type == "ping":
            await self.send_to_client(client_id, {
                "type": "pong",
                "data": {"timestamp": datetime.utcnow().isoformat()},
                "message_id": message_id
            })
            return
        
        elif message_type == "subscribe":
            await self._handle_subscribe(client_id, data)
            return
        
        elif message_type == "unsubscribe":
            await self._handle_unsubscribe(client_id, data)
            return
        
        elif message_type == "join_room":
            await self.join_room(client_id, data.get("room"))
            return
        
        elif message_type == "leave_room":
            await self.leave_room(client_id, data.get("room"))
            return
        
        elif message_type == "broadcast":
            await self.broadcast_to_room(
                data.get("room"),
                data.get("message"),
                exclude=[client_id]
            )
            return
        
        # Handle custom messages
        handler = self.handlers.get(message_type)
        if handler:
            try:
                response = await handler(client_id, data)
                if response:
                    await self.send_to_client(client_id, {
                        "type": f"{message_type}_response",
                        "data": response,
                        "message_id": message_id
                    })
            except Exception as e:
                logger.error(f"Error in handler for {message_type}: {e}")
                await self.send_to_client(client_id, {
                    "type": "error",
                    "data": {"message": str(e)},
                    "message_id": message_id
                })
        else:
            logger.warning(f"Unknown message type: {message_type}")
    
    async def _handle_subscribe(self, client_id: str, data: dict):
        """Handle subscription request"""
        channels = data.get("channels", [])
        
        conn_info = self.connections.get(client_id)
        if conn_info:
            for channel in channels:
                conn_info.subscriptions.add(channel)
            
            await self.send_to_client(client_id, {
                "type": "subscribed",
                "data": {"channels": list(conn_info.subscriptions)}
            })
    
    async def _handle_unsubscribe(self, client_id: str, data: dict):
        """Handle unsubscription request"""
        channels = data.get("channels", [])
        
        conn_info = self.connections.get(client_id)
        if conn_info:
            for channel in channels:
                conn_info.subscriptions.discard(channel)
            
            await self.send_to_client(client_id, {
                "type": "unsubscribed",
                "data": {"channels": list(conn_info.subscriptions)}
            })
    
    async def join_room(self, client_id: str, room: str):
        """Add client to a room"""
        if client_id not in self.connections:
            return False
        
        self.rooms[room].add(client_id)
        self.connections[client_id].rooms.add(room)
        
        logger.debug(f"Client {client_id} joined room: {room}")
        
        # Notify client
        await self.send_to_client(client_id, {
            "type": "joined_room",
            "data": {"room": room}
        })
        
        return True
    
    async def leave_room(self, client_id: str, room: str):
        """Remove client from a room"""
        if room in self.rooms:
            self.rooms[room].discard(client_id)
            if not self.rooms[room]:
                del self.rooms[room]
        
        if client_id in self.connections:
            self.connections[client_id].rooms.discard(room)
        
        logger.debug(f"Client {client_id} left room: {room}")
        
        return True
    
    async def send_to_client(self, client_id: str, message: dict):
        """Send a message to a specific client"""
        if client_id in self.connections:
            await self.connections[client_id].send(message)
            return True
        return False
    
    async def send_to_user(self, user_id: str, message: dict):
        """Send a message to all connections of a user"""
        sent = False
        if user_id in self.user_connections:
            for client_id in self.user_connections[user_id]:
                if await self.send_to_client(client_id, message):
                    sent = True
        return sent
    
    async def broadcast_to_room(self, room: str, message: dict, exclude: list = None):
        """Broadcast a message to all clients in a room"""
        if room not in self.rooms:
            return 0
        
        exclude = exclude or []
        count = 0
        
        for client_id in self.rooms[room]:
            if client_id in exclude:
                continue
            if await self.send_to_client(client_id, message):
                count += 1
        
        return count
    
    async def broadcast_to_all(self, message: dict, exclude: list = None):
        """Broadcast a message to all connected clients"""
        exclude = exclude or []
        count = 0
        
        for client_id in list(self.connections.keys()):
            if client_id in exclude:
                continue
            if await self.send_to_client(client_id, message):
                count += 1
        
        return count
    
    async def broadcast_to_subscribers(self, channel: str, message: dict):
        """Broadcast to clients subscribed to a channel"""
        count = 0
        
        for client_id, conn_info in self.connections.items():
            if channel in conn_info.subscriptions:
                if await self.send_to_client(client_id, message):
                    count += 1
        
        return count
    
    def register_handler(self, message_type: str, handler: Callable):
        """Register a handler for a custom message type"""
        self.handlers[message_type] = handler
        logger.debug(f"Registered handler for: {message_type}")
    
    def unregister_handler(self, message_type: str):
        """Unregister a handler"""
        if message_type in self.handlers:
            del self.handlers[message_type]
            logger.debug(f"Unregistered handler for: {message_type}")
    
    def get_connection_info(self, client_id: str) -> Optional[ConnectionInfo]:
        """Get connection information"""
        return self.connections.get(client_id)
    
    def get_room_members(self, room: str) -> list:
        """Get list of client IDs in a room"""
        return list(self.rooms.get(room, set()))
    
    def get_user_connections(self, user_id: str) -> list:
        """Get all connections for a user"""
        return list(self.user_connections.get(user_id, set()))
    
    def get_stats(self) -> dict:
        """Get connection statistics"""
        return {
            "total_connections": len(self.connections),
            "total_users": len(self.user_connections),
            "total_rooms": len(self.rooms),
            "connections_by_user": {
                user_id: len(conns)
                for user_id, conns in self.user_connections.items()
            },
            "rooms": {
                room: len(members)
                for room, members in self.rooms.items()
            }
        }
    
    async def _authenticate(self, websocket: WebSocket) -> Optional[str]:
        """Authenticate the connection using token"""
        # Try to get token from query parameters
        query_params = websocket.query_params
        token = query_params.get("token")
        
        if token:
            payload = verify_token(token)
            if payload:
                return payload.get("sub")
        
        return None
    
    async def _ping_all(self):
        """Send periodic pings to all connections"""
        while True:
            try:
                await asyncio.sleep(self.ping_interval)
                
                for client_id, conn_info in list(self.connections.items()):
                    try:
                        await conn_info.websocket.send_json({"type": "ping"})
                    except:
                        # Connection might be dead, will be cleaned up
                        pass
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in ping task: {e}")
    
    async def _cleanup_stale_connections(self):
        """Remove stale connections"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                now = datetime.utcnow()
                stale_timeout = 60  # seconds
                
                for client_id, conn_info in list(self.connections.items()):
                    time_since_activity = (now - conn_info.last_activity).total_seconds()
                    
                    if time_since_activity > stale_timeout:
                        logger.info(f"Cleaning up stale connection: {client_id}")
                        await self.disconnect(client_id, code=1000, reason="Connection timeout")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")


# ==================== WebSocket Router ====================

class WebSocketRouter:
    """
    Routes WebSocket connections to different handlers
    based on path
    """
    
    def __init__(self, manager: WebSocketManager):
        self.manager = manager
        self.routes = {}
    
    def route(self, path: str):
        """Decorator to register a route handler"""
        def decorator(handler):
            self.routes[path] = handler
            return handler
        return decorator
    
    async def handle_connection(self, path: str, websocket: WebSocket):
        """Handle a WebSocket connection"""
        if path in self.routes:
            await self.routes[path](websocket, self.manager)
        else:
            await websocket.close(code=1003, reason="Invalid path")


# ==================== Market Data WebSocket ====================

class MarketDataWebSocket:
    """WebSocket handler for real-time market data"""
    
    def __init__(self, exchange_manager):
        self.exchange_manager = exchange_manager
        self.subscribers = defaultdict(set)  # symbol -> set of client_ids
        self.tasks = {}
    
    async def handle(self, websocket: WebSocket, manager: WebSocketManager):
        """Handle market data WebSocket connection"""
        client_id = await manager.connect(websocket)
        
        try:
            # Register handlers
            manager.register_handler("subscribe_market", self.handle_subscribe)
            manager.register_handler("unsubscribe_market", self.handle_unsubscribe)
            
            # Handle messages
            await manager.handle_messages(client_id)
            
        finally:
            # Cleanup subscriptions
            for symbol in list(self.subscribers.keys()):
                self.subscribers[symbol].discard(client_id)
                if not self.subscribers[symbol]:
                    await self.stop_symbol_stream(symbol)
            
            manager.unregister_handler("subscribe_market")
            manager.unregister_handler("unsubscribe_market")
    
    async def handle_subscribe(self, client_id: str, data: dict):
        """Handle market data subscription"""
        symbol = data.get("symbol")
        interval = data.get("interval", "1s")
        
        if not symbol:
            return {"error": "Symbol required"}
        
        self.subscribers[symbol].add(client_id)
        
        # Start streaming if not already
        if symbol not in self.tasks:
            self.tasks[symbol] = asyncio.create_task(
                self.stream_market_data(symbol, interval)
            )
        
        return {
            "symbol": symbol,
            "interval": interval,
            "subscribed": True
        }
    
    async def handle_unsubscribe(self, client_id: str, data: dict):
        """Handle market data unsubscription"""
        symbol = data.get("symbol")
        
        if symbol:
            self.subscribers[symbol].discard(client_id)
            if not self.subscribers[symbol]:
                await self.stop_symbol_stream(symbol)
        
        return {"unsubscribed": True}
    
    async def stream_market_data(self, symbol: str, interval: str):
        """Stream market data for a symbol"""
        try:
            interval_seconds = float(interval.replace('s', ''))
            
            while symbol in self.subscribers and self.subscribers[symbol]:
                try:
                    # Get latest ticker
                    ticker = await self.exchange_manager.get_ticker(symbol)
                    
                    if ticker and self.subscribers[symbol]:
                        # Broadcast to subscribers
                        message = {
                            "type": "market_update",
                            "data": {
                                "symbol": symbol,
                                "ticker": ticker,
                                "timestamp": datetime.utcnow().isoformat()
                            }
                        }
                        
                        for client_id in self.subscribers[symbol]:
                            await manager.send_to_client(client_id, message)
                    
                    await asyncio.sleep(interval_seconds)
                    
                except Exception as e:
                    logger.error(f"Error streaming {symbol}: {e}")
                    await asyncio.sleep(1)
                    
        except asyncio.CancelledError:
            pass
        finally:
            if symbol in self.tasks:
                del self.tasks[symbol]
    
    async def stop_symbol_stream(self, symbol: str):
        """Stop streaming for a symbol"""
        if symbol in self.tasks:
            self.tasks[symbol].cancel()
            del self.tasks[symbol]


# ==================== Order Book WebSocket ====================

class OrderBookWebSocket:
    """WebSocket handler for real-time order book updates"""
    
    def __init__(self, exchange_manager):
        self.exchange_manager = exchange_manager
        self.subscribers = defaultdict(set)
        self.tasks = {}
    
    async def handle(self, websocket: WebSocket, manager: WebSocketManager):
        """Handle order book WebSocket connection"""
        client_id = await manager.connect(websocket)
        
        try:
            manager.register_handler("subscribe_orderbook", self.handle_subscribe)
            manager.register_handler("unsubscribe_orderbook", self.handle_unsubscribe)
            
            await manager.handle_messages(client_id)
            
        finally:
            # Cleanup
            for symbol in list(self.subscribers.keys()):
                self.subscribers[symbol].discard(client_id)
            
            manager.unregister_handler("subscribe_orderbook")
            manager.unregister_handler("unsubscribe_orderbook")
    
    async def handle_subscribe(self, client_id: str, data: dict):
        """Handle order book subscription"""
        symbol = data.get("symbol")
        depth = data.get("depth", 10)
        
        if not symbol:
            return {"error": "Symbol required"}
        
        self.subscribers[symbol].add(client_id)
        
        return {
            "symbol": symbol,
            "depth": depth,
            "subscribed": True
        }
    
    async def handle_unsubscribe(self, client_id: str, data: dict):
        """Handle order book unsubscription"""
        symbol = data.get("symbol")
        
        if symbol:
            self.subscribers[symbol].discard(client_id)
        
        return {"unsubscribed": True}


# ==================== User Notifications WebSocket ====================

class NotificationWebSocket:
    """WebSocket handler for user notifications"""
    
    async def handle(self, websocket: WebSocket, manager: WebSocketManager):
        """Handle notification WebSocket connection"""
        # Authenticate first
        client_id = await manager.connect(websocket)
        
        conn_info = manager.get_connection_info(client_id)
        if not conn_info or not conn_info.user_id:
            await manager.disconnect(client_id, code=1008, reason="Authentication required")
            return
        
        try:
            # Join user's notification room
            user_room = f"user:{conn_info.user_id}"
            await manager.join_room(client_id, user_room)
            
            # Send initial unread count
            unread_count = await self.get_unread_count(conn_info.user_id)
            await manager.send_to_client(client_id, {
                "type": "notification_count",
                "data": {"unread": unread_count}
            })
            
            # Handle messages
            await manager.handle_messages(client_id)
            
        finally:
            await manager.leave_room(client_id, user_room)
    
    async def get_unread_count(self, user_id: str) -> int:
        """Get unread notification count"""
        # This would query the database
        return 0


# ==================== Trading WebSocket ====================

class TradingWebSocket:
    """WebSocket handler for real-time trading updates"""
    
    async def handle(self, websocket: WebSocket, manager: WebSocketManager):
        """Handle trading WebSocket connection"""
        client_id = await manager.connect(websocket)
        
        conn_info = manager.get_connection_info(client_id)
        if not conn_info or not conn_info.user_id:
            await manager.disconnect(client_id, code=1008, reason="Authentication required")
            return
        
        try:
            # Join user's trading room
            trading_room = f"trading:{conn_info.user_id}"
            await manager.join_room(client_id, trading_room)
            
            # Register handlers
            manager.register_handler("order_update", self.handle_order_update)
            manager.register_handler("position_update", self.handle_position_update)
            
            await manager.handle_messages(client_id)
            
        finally:
            await manager.leave_room(client_id, trading_room)
            manager.unregister_handler("order_update")
            manager.unregister_handler("position_update")
    
    async def handle_order_update(self, client_id: str, data: dict):
        """Handle order update from client"""
        # This would process order updates
        return {"received": True}
    
    async def handle_position_update(self, client_id: str, data: dict):
        """Handle position update from client"""
        return {"received": True}


# ==================== Signal WebSocket ====================

class SignalWebSocket:
    """WebSocket handler for real-time trading signals"""
    
    async def handle(self, websocket: WebSocket, manager: WebSocketManager):
        """Handle signal WebSocket connection"""
        client_id = await manager.connect(websocket)
        
        try:
            manager.register_handler("subscribe_signal", self.handle_subscribe)
            manager.register_handler("unsubscribe_signal", self.handle_unsubscribe)
            
            await manager.handle_messages(client_id)
            
        finally:
            manager.unregister_handler("subscribe_signal")
            manager.unregister_handler("unsubscribe_signal")
    
    async def handle_subscribe(self, client_id: str, data: dict):
        """Handle signal subscription"""
        signal_type = data.get("type", "all")
        
        conn_info = manager.get_connection_info(client_id)
        if conn_info:
            room = f"signals:{signal_type}"
            await manager.join_room(client_id, room)
        
        return {"subscribed": True}
    
    async def handle_unsubscribe(self, client_id: str, data: dict):
        """Handle signal unsubscription"""
        signal_type = data.get("type", "all")
        
        conn_info = manager.get_connection_info(client_id)
        if conn_info:
            room = f"signals:{signal_type}"
            await manager.leave_room(client_id, room)
        
        return {"unsubscribed": True}


# ==================== Chat WebSocket ====================

class ChatWebSocket:
    """WebSocket handler for chat functionality"""
    
    def __init__(self):
        self.message_history = defaultdict(list)  # room -> list of messages
        self.max_history = 100
    
    async def handle(self, websocket: WebSocket, manager: WebSocketManager):
        """Handle chat WebSocket connection"""
        client_id = await manager.connect(websocket)
        
        try:
            manager.register_handler("join_chat", self.handle_join)
            manager.register_handler("leave_chat", self.handle_leave)
            manager.register_handler("send_message", self.handle_message)
            manager.register_handler("get_history", self.handle_history)
            
            await manager.handle_messages(client_id)
            
        finally:
            manager.unregister_handler("join_chat")
            manager.unregister_handler("leave_chat")
            manager.unregister_handler("send_message")
            manager.unregister_handler("get_history")
    
    async def handle_join(self, client_id: str, data: dict):
        """Handle user joining a chat room"""
        room = data.get("room", "general")
        
        conn_info = manager.get_connection_info(client_id)
        if conn_info:
            await manager.join_room(client_id, f"chat:{room}")
            
            # Notify others
            await manager.broadcast_to_room(
                f"chat:{room}",
                {
                    "type": "user_joined",
                    "data": {
                        "user_id": conn_info.user_id,
                        "client_id": client_id,
                        "room": room,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                },
                exclude=[client_id]
            )
        
        return {"joined": room}
    
    async def handle_leave(self, client_id: str, data: dict):
        """Handle user leaving a chat room"""
        room = data.get("room", "general")
        
        conn_info = manager.get_connection_info(client_id)
        if conn_info:
            await manager.leave_room(client_id, f"chat:{room}")
            
            # Notify others
            await manager.broadcast_to_room(
                f"chat:{room}",
                {
                    "type": "user_left",
                    "data": {
                        "user_id": conn_info.user_id,
                        "client_id": client_id,
                        "room": room,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
            )
        
        return {"left": room}
    
    async def handle_message(self, client_id: str, data: dict):
        """Handle chat message"""
        room = data.get("room", "general")
        message = data.get("message", "")
        
        if not message:
            return {"error": "Message required"}
        
        conn_info = manager.get_connection_info(client_id)
        
        # Create message object
        msg_obj = {
            "type": "chat_message",
            "data": {
                "id": str(uuid.uuid4()),
                "user_id": conn_info.user_id if conn_info else None,
                "client_id": client_id,
                "room": room,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        # Store in history
        self.message_history[room].append(msg_obj)
        if len(self.message_history[room]) > self.max_history:
            self.message_history[room].pop(0)
        
        # Broadcast to room
        await manager.broadcast_to_room(f"chat:{room}", msg_obj)
        
        return {"sent": True, "message_id": msg_obj["data"]["id"]}
    
    async def handle_history(self, client_id: str, data: dict):
        """Get chat history"""
        room = data.get("room", "general")
        limit = data.get("limit", 50)
        
        history = self.message_history.get(room, [])[-limit:]
        
        return {
            "room": room,
            "history": history
        }


# Singleton instance
ws_manager = WebSocketManager()
market_ws = MarketDataWebSocket(exchange_manager)
orderbook_ws = OrderBookWebSocket(exchange_manager)
notification_ws = NotificationWebSocket()
trading_ws = TradingWebSocket()
signal_ws = SignalWebSocket()
chat_ws = ChatWebSocket()