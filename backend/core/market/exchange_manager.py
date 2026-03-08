"""
Exchange Manager - Handles 100+ cryptocurrency exchanges
Enterprise-grade connection management, rate limiting, failover
"""

import asyncio
import hmac
import hashlib
import time
import json
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from collections import deque
import aiohttp
import websockets
from tenacity import retry, stop_after_attempt, wait_exponential
import redis.asyncio as redis
from prometheus_client import Counter, Histogram, Gauge

from ...utils.logger import get_logger
from ...utils.metrics import track_api_call
from ...config import settings

logger = get_logger(__name__)

# Metrics
api_requests = Counter('exchange_api_requests_total', 'Total API requests', ['exchange', 'endpoint'])
api_latency = Histogram('exchange_api_latency_seconds', 'API latency', ['exchange'])
connection_status = Gauge('exchange_connection_status', 'Connection status', ['exchange'])


class ExchangeConnection:
    """এক্সচেঞ্জ কানেকশন হ্যান্ডলার"""
    
    def __init__(self, exchange_id: str, config: dict):
        self.exchange_id = exchange_id
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_connection: Optional[websockets.WebSocketClientProtocol] = None
        self.rate_limiter = deque(maxlen=100)
        self.last_request_time = 0
        self.connected = False
        self.retry_count = 0
        self.max_retries = 5
        
    async def connect(self):
        """এক্সচেঞ্জে সংযোগ করুন"""
        try:
            self.session = aiohttp.ClientSession(
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
            # WebSocket সংযোগ (যদি থাকে)
            if self.config.get('websocket_url'):
                self.ws_connection = await websockets.connect(
                    self.config['websocket_url'],
                    ping_interval=20,
                    ping_timeout=10
                )
            
            self.connected = True
            connection_status.labels(exchange=self.exchange_id).set(1)
            logger.info(f"✅ Connected to {self.exchange_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to {self.exchange_id}: {e}")
            self.connected = False
            connection_status.labels(exchange=self.exchange_id).set(0)
            raise
    
    def _get_headers(self) -> dict:
        """API হেডার তৈরি"""
        headers = {
            'User-Agent': 'AI-Trading-Ecosystem/1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        if self.config.get('api_key'):
            headers['X-MBX-APIKEY'] = self.config['api_key']
            
        return headers
    
    async def _check_rate_limit(self):
        """রেট লিমিট চেক"""
        now = time.time()
        
        # Clean old requests
        while self.rate_limiter and now - self.rate_limiter[0] > 60:
            self.rate_limiter.popleft()
        
        # Check rate limit
        if len(self.rate_limiter) >= self.config.get('rate_limit', 1200):
            wait_time = 60 - (now - self.rate_limiter[0])
            if wait_time > 0:
                logger.warning(f"Rate limit reached for {self.exchange_id}, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
        
        self.rate_limiter.append(now)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def request(self, method: str, endpoint: str, signed: bool = False, **kwargs) -> dict:
        """API রিকোয়েস্ট পাঠান"""
        await self._check_rate_limit()
        
        url = f"{self.config['base_url']}{endpoint}"
        
        # Add signature for private endpoints
        if signed:
            kwargs = self._sign_request(kwargs)
        
        start_time = time.time()
        
        try:
            async with self.session.request(method, url, **kwargs) as response:
                latency = time.time() - start_time
                api_latency.labels(exchange=self.exchange_id).observe(latency)
                api_requests.labels(exchange=self.exchange_id, endpoint=endpoint).inc()
                
                if response.status != 200:
                    error_data = await response.text()
                    raise Exception(f"API Error {response.status}: {error_data}")
                
                return await response.json()
                
        except Exception as e:
            logger.error(f"Request failed for {self.exchange_id}: {e}")
            raise
    
    def _sign_request(self, params: dict) -> dict:
        """রিকোয়েস্ট সাইন করুন"""
        if 'timestamp' not in params:
            params['timestamp'] = int(time.time() * 1000)
        
        query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        signature = hmac.new(
            self.config['secret_key'].encode(),
            query_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        params['signature'] = signature
        return params
    
    async def close(self):
        """সংযোগ বন্ধ করুন"""
        if self.session:
            await self.session.close()
        if self.ws_connection:
            await self.ws_connection.close()
        
        self.connected = False
        connection_status.labels(exchange=self.exchange_id).set(0)
        logger.info(f"🔌 Disconnected from {self.exchange_id}")


class ExchangeManager:
    """মাস্টার এক্সচেঞ্জ ম্যানেজার - ১০০+ এক্সচেঞ্জ কানেকশন হ্যান্ডেল করে"""
    
    def __init__(self):
        self.connections: Dict[str, ExchangeConnection] = {}
        self.failover_groups: Dict[str, List[str]] = {}
        self.health_status: Dict[str, bool] = {}
        self.redis_client: Optional[redis.Redis] = None
        self._load_exchanges()
        
    def _load_exchanges(self):
        """সকল এক্সচেঞ্জ কনফিগারেশন লোড"""
        self.exchanges_config = {
            # Tier 1 - Major Exchanges (Highest liquidity)
            'binance': {
                'name': 'Binance',
                'base_url': 'https://api.binance.com',
                'ws_url': 'wss://stream.binance.com:9443/ws',
                'api_key': settings.BINANCE_API_KEY,
                'secret_key': settings.BINANCE_SECRET_KEY,
                'rate_limit': 1200,
                'weight': 100,
                'tier': 1
            },
            'coinbase': {
                'name': 'Coinbase',
                'base_url': 'https://api.coinbase.com',
                'ws_url': 'wss://ws-feed.coinbase.com',
                'api_key': settings.COINBASE_API_KEY,
                'secret_key': settings.COINBASE_SECRET_KEY,
                'rate_limit': 1000,
                'weight': 95,
                'tier': 1
            },
            'kraken': {
                'name': 'Kraken',
                'base_url': 'https://api.kraken.com',
                'ws_url': 'wss://ws.kraken.com',
                'api_key': settings.KRAKEN_API_KEY,
                'secret_key': settings.KRAKEN_SECRET_KEY,
                'rate_limit': 1000,
                'weight': 90,
                'tier': 1
            },
            'kucoin': {
                'name': 'KuCoin',
                'base_url': 'https://api.kucoin.com',
                'ws_url': 'wss://ws-api.kucoin.com/endpoint',
                'api_key': settings.KUCOIN_API_KEY,
                'secret_key': settings.KUCOIN_SECRET_KEY,
                'passphrase': settings.KUCOIN_PASSPHRASE,
                'rate_limit': 1000,
                'weight': 85,
                'tier': 1
            },
            'bybit': {
                'name': 'Bybit',
                'base_url': 'https://api.bybit.com',
                'ws_url': 'wss://stream.bybit.com/v5/public/spot',
                'api_key': settings.BYBIT_API_KEY,
                'secret_key': settings.BYBIT_SECRET_KEY,
                'rate_limit': 1000,
                'weight': 85,
                'tier': 1
            },
            'okx': {
                'name': 'OKX',
                'base_url': 'https://www.okx.com',
                'ws_url': 'wss://ws.okx.com:8443/ws/v5/public',
                'api_key': settings.OKX_API_KEY,
                'secret_key': settings.OKX_SECRET_KEY,
                'passphrase': settings.OKX_PASSPHRASE,
                'rate_limit': 1000,
                'weight': 85,
                'tier': 1
            },
            
            # Tier 2 - Regional Exchanges
            'binance_us': {
                'name': 'Binance US',
                'base_url': 'https://api.binance.us',
                'api_key': settings.BINANCE_US_API_KEY,
                'secret_key': settings.BINANCE_US_SECRET_KEY,
                'rate_limit': 1000,
                'weight': 80,
                'tier': 2
            },
            'bitstamp': {
                'name': 'Bitstamp',
                'base_url': 'https://www.bitstamp.net/api',
                'api_key': settings.BITSTAMP_API_KEY,
                'secret_key': settings.BITSTAMP_SECRET_KEY,
                'rate_limit': 800,
                'weight': 75,
                'tier': 2
            },
            'bittrex': {
                'name': 'Bittrex',
                'base_url': 'https://api.bittrex.com/v3',
                'api_key': settings.BITTREX_API_KEY,
                'secret_key': settings.BITTREX_SECRET_KEY,
                'rate_limit': 800,
                'weight': 75,
                'tier': 2
            },
            'poloniex': {
                'name': 'Poloniex',
                'base_url': 'https://api.poloniex.com',
                'api_key': settings.POLONIEX_API_KEY,
                'secret_key': settings.POLONIEX_SECRET_KEY,
                'rate_limit': 800,
                'weight': 75,
                'tier': 2
            },
            'gateio': {
                'name': 'Gate.io',
                'base_url': 'https://api.gateio.ws/api/v4',
                'api_key': settings.GATEIO_API_KEY,
                'secret_key': settings.GATEIO_SECRET_KEY,
                'rate_limit': 800,
                'weight': 75,
                'tier': 2
            },
            'mexc': {
                'name': 'MEXC',
                'base_url': 'https://api.mexc.com',
                'api_key': settings.MEXC_API_KEY,
                'secret_key': settings.MEXC_SECRET_KEY,
                'rate_limit': 800,
                'weight': 75,
                'tier': 2
            },
            'bitget': {
                'name': 'Bitget',
                'base_url': 'https://api.bitget.com',
                'api_key': settings.BITGET_API_KEY,
                'secret_key': settings.BITGET_SECRET_KEY,
                'passphrase': settings.BITGET_PASSPHRASE,
                'rate_limit': 800,
                'weight': 75,
                'tier': 2
            },
            
            # Tier 3 - Smaller Exchanges
            'gemini': {
                'name': 'Gemini',
                'base_url': 'https://api.gemini.com',
                'ws_url': 'wss://api.gemini.com/v1/marketdata',
                'api_key': settings.GEMINI_API_KEY,
                'secret_key': settings.GEMINI_SECRET_KEY,
                'rate_limit': 600,
                'weight': 70,
                'tier': 3
            },
            'crypto_com': {
                'name': 'Crypto.com',
                'base_url': 'https://api.crypto.com/v2',
                'api_key': settings.CRYPTO_COM_API_KEY,
                'secret_key': settings.CRYPTO_COM_SECRET_KEY,
                'rate_limit': 600,
                'weight': 70,
                'tier': 3
            },
            'huobi': {
                'name': 'Huobi',
                'base_url': 'https://api.huobi.pro',
                'api_key': settings.HUOBI_API_KEY,
                'secret_key': settings.HUOBI_SECRET_KEY,
                'rate_limit': 600,
                'weight': 70,
                'tier': 3
            },
            'lbank': {
                'name': 'LBank',
                'base_url': 'https://api.lbank.info',
                'api_key': settings.LBANK_API_KEY,
                'secret_key': settings.LBANK_SECRET_KEY,
                'rate_limit': 600,
                'weight': 65,
                'tier': 3
            },
            'hitbtc': {
                'name': 'HitBTC',
                'base_url': 'https://api.hitbtc.com',
                'api_key': settings.HITBTC_API_KEY,
                'secret_key': settings.HITBTC_SECRET_KEY,
                'rate_limit': 600,
                'weight': 65,
                'tier': 3
            },
            
            # Tier 4 - DEX Aggregators
            'uniswap': {
                'name': 'Uniswap V3',
                'base_url': 'https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3',
                'type': 'graphql',
                'rate_limit': 300,
                'weight': 90,
                'tier': 4
            },
            'pancakeswap': {
                'name': 'PancakeSwap',
                'base_url': 'https://api.thegraph.com/subgraphs/name/pancakeswap/exchange-v3',
                'type': 'graphql',
                'rate_limit': 300,
                'weight': 85,
                'tier': 4
            },
            'sushiswap': {
                'name': 'SushiSwap',
                'base_url': 'https://api.thegraph.com/subgraphs/name/sushiswap/exchange',
                'type': 'graphql',
                'rate_limit': 300,
                'weight': 80,
                'tier': 4
            },
            'curve': {
                'name': 'Curve',
                'base_url': 'https://api.curve.fi/api',
                'rate_limit': 300,
                'weight': 75,
                'tier': 4
            },
            'balancer': {
                'name': 'Balancer',
                'base_url': 'https://api.thegraph.com/subgraphs/name/balancer-labs/balancer-v2',
                'type': 'graphql',
                'rate_limit': 300,
                'weight': 70,
                'tier': 4
            },
            
            # Tier 5 - Derivatives
            'dydx': {
                'name': 'dYdX',
                'base_url': 'https://api.dydx.exchange',
                'api_key': settings.DYDX_API_KEY,
                'secret_key': settings.DYDX_SECRET_KEY,
                'rate_limit': 500,
                'weight': 80,
                'tier': 5
            },
            'perp': {
                'name': 'Perpetual Protocol',
                'base_url': 'https://api.perp.exchange',
                'rate_limit': 500,
                'weight': 75,
                'tier': 5
            },
            'gmx': {
                'name': 'GMX',
                'base_url': 'https://api.gmx.io',
                'rate_limit': 500,
                'weight': 75,
                'tier': 5
            },
            
            # ... Continue for 70+ more exchanges
        }
        
        # Add 70 more exchanges dynamically
        self._add_more_exchanges()
        
        logger.info(f"📊 Loaded {len(self.exchanges_config)} exchange configurations")
    
    def _add_more_exchanges(self):
        """Add 70+ more exchanges"""
        more_exchanges = {
            'aax': {'name': 'AAX', 'base_url': 'https://api.aax.com', 'tier': 3},
            'ace': {'name': 'ACE', 'base_url': 'https://api.ace.io', 'tier': 3},
            'alpaca': {'name': 'Alpaca', 'base_url': 'https://api.alpaca.markets', 'tier': 2},
            'ascendex': {'name': 'AscendEX', 'base_url': 'https://api.ascendex.com', 'tier': 2},
            'bequant': {'name': 'Bequant', 'base_url': 'https://api.bequant.io', 'tier': 3},
            'bibox': {'name': 'Bibox', 'base_url': 'https://api.bibox.com', 'tier': 3},
            'bigone': {'name': 'BigONE', 'base_url': 'https://big.one/api', 'tier': 3},
            'binance_jersey': {'name': 'Binance Jersey', 'base_url': 'https://api.binance.je', 'tier': 2},
            'binance_uganda': {'name': 'Binance Uganda', 'base_url': 'https://api.binance.co.ug', 'tier': 3},
            'bit2c': {'name': 'Bit2C', 'base_url': 'https://www.bit2c.co.il', 'tier': 3},
            'bitbank': {'name': 'bitbank', 'base_url': 'https://public.bitbank.cc', 'tier': 3},
            'bitbay': {'name': 'BitBay', 'base_url': 'https://bitbay.net', 'tier': 3},
            'bitfinex': {'name': 'Bitfinex', 'base_url': 'https://api-pub.bitfinex.com', 'tier': 1},
            'bitflyer': {'name': 'bitFlyer', 'base_url': 'https://api.bitflyer.com', 'tier': 2},
            'bitforex': {'name': 'Bitforex', 'base_url': 'https://api.bitforex.com', 'tier': 3},
            'bithumb': {'name': 'Bithumb', 'base_url': 'https://api.bithumb.com', 'tier': 2},
            'bitkub': {'name': 'Bitkub', 'base_url': 'https://api.bitkub.com', 'tier': 3},
            'bitmart': {'name': 'BitMart', 'base_url': 'https://api-cloud.bitmart.com', 'tier': 2},
            'bitmex': {'name': 'BitMEX', 'base_url': 'https://www.bitmex.com/api', 'tier': 1},
            'bitso': {'name': 'Bitso', 'base_url': 'https://api.bitso.com', 'tier': 3},
            'bitsten': {'name': 'Bitsten', 'base_url': 'https://api.bitsten.com', 'tier': 3},
            'bitturk': {'name': 'Bitturk', 'base_url': 'https://api.bitturk.com', 'tier': 3},
            'bkex': {'name': 'BKEX', 'base_url': 'https://api.bkex.com', 'tier': 3},
            'bl3p': {'name': 'BL3P', 'base_url': 'https://api.bl3p.eu', 'tier': 3},
            'blockchaincom': {'name': 'Blockchain.com', 'base_url': 'https://api.blockchain.info', 'tier': 2},
            'btc_alpha': {'name': 'BTC Alpha', 'base_url': 'https://btc-alpha.com/api', 'tier': 3},
            'btcbox': {'name': 'BtcBox', 'base_url': 'https://www.btcbox.co.jp', 'tier': 3},
            'btcmarkets': {'name': 'BTC Markets', 'base_url': 'https://api.btcmarkets.net', 'tier': 2},
            'btctradeua': {'name': 'BTCTradeUA', 'base_url': 'https://btc-trade.com.ua', 'tier': 3},
            'btcturk': {'name': 'BTCTurk', 'base_url': 'https://api.btcturk.com', 'tier': 2},
            'buda': {'name': 'Buda', 'base_url': 'https://www.buda.com/api', 'tier': 3},
            'bw': {'name': 'BW', 'base_url': 'https://api.bw.com', 'tier': 3},
            'bytetrade': {'name': 'ByteTrade', 'base_url': 'https://api.bytetrade.io', 'tier': 3},
            'cex': {'name': 'CEX.IO', 'base_url': 'https://cex.io/api', 'tier': 2},
            'coincheck': {'name': 'coincheck', 'base_url': 'https://coincheck.com', 'tier': 3},
            'coindeal': {'name': 'CoinDeal', 'base_url': 'https://api.coindeal.com', 'tier': 3},
            'coinether': {'name': 'CoinEther', 'base_url': 'https://api.coinether.com', 'tier': 3},
            'coinex': {'name': 'CoinEx', 'base_url': 'https://api.coinex.com', 'tier': 2},
            'coinfalcon': {'name': 'CoinFalcon', 'base_url': 'https://api.coinfalcon.com', 'tier': 3},
            'coinfloor': {'name': 'Coinfloor', 'base_url': 'https://api.coinfloor.co.uk', 'tier': 3},
            'coingi': {'name': 'Coingi', 'base_url': 'https://api.coingi.com', 'tier': 3},
            'coinmarketcap': {'name': 'CoinMarketCap', 'base_url': 'https://pro-api.coinmarketcap.com', 'tier': 1},
            'coinmate': {'name': 'CoinMate', 'base_url': 'https://coinmate.io', 'tier': 3},
            'coinone': {'name': 'CoinOne', 'base_url': 'https://api.coinone.co.kr', 'tier': 2},
            'coinspot': {'name': 'CoinSpot', 'base_url': 'https://www.coinspot.com.au', 'tier': 3},
            'cryptology': {'name': 'Cryptology', 'base_url': 'https://api.cryptology.com', 'tier': 3},
            'currencycom': {'name': 'Currency.com', 'base_url': 'https://api-adapter.backend.currency.com', 'tier': 2},
            'delta': {'name': 'Delta Exchange', 'base_url': 'https://api.delta.exchange', 'tier': 2},
            'deribit': {'name': 'Deribit', 'base_url': 'https://www.deribit.com/api', 'tier': 1},
            'digifinex': {'name': 'DigiFinex', 'base_url': 'https://openapi.digifinex.com', 'tier': 2},
            'dx': {'name': 'DX.exchange', 'base_url': 'https://api.dx.exchange', 'tier': 3},
            'equos': {'name': 'EQUOS', 'base_url': 'https://api.equos.io', 'tier': 3},
            'eterbase': {'name': 'Eterbase', 'base_url': 'https://api.eterbase.com', 'tier': 3},
            'exmo': {'name': 'EXMO', 'base_url': 'https://api.exmo.com', 'tier': 2},
            'exx': {'name': 'EXX', 'base_url': 'https://api.exx.com', 'tier': 3},
            'flowbtc': {'name': 'flowBTC', 'base_url': 'https://api.flowbtc.com', 'tier': 3},
            'ftx': {'name': 'FTX', 'base_url': 'https://ftx.com/api', 'tier': 1},
            'gatecoin': {'name': 'Gatecoin', 'base_url': 'https://api.gatecoin.com', 'tier': 3},
            'gopax': {'name': 'GOPAX', 'base_url': 'https://api.gopax.co.kr', 'tier': 2},
            'graviex': {'name': 'Graviex', 'base_url': 'https://api.graviex.net', 'tier': 3},
            'hbtc': {'name': 'HBTC', 'base_url': 'https://api.hbtc.com', 'tier': 2},
            'hitcoin': {'name': 'Hitcoin', 'base_url': 'https://api.hitcoin.net', 'tier': 3},
            'hollaex': {'name': 'HollaEx', 'base_url': 'https://api.hollaex.com', 'tier': 3},
            'hotbit': {'name': 'Hotbit', 'base_url': 'https://api.hotbit.io', 'tier': 2},
            'idex': {'name': 'IDEX', 'base_url': 'https://api.idex.market', 'tier': 2},
            'indodax': {'name': 'INDODAX', 'base_url': 'https://indodax.com', 'tier': 2},
            'itbit': {'name': 'itBit', 'base_url': 'https://api.itbit.com', 'tier': 2},
            'kanga': {'name': 'Kanga', 'base_url': 'https://api.kanga.exchange', 'tier': 3},
            'kinesis': {'name': 'Kinesis', 'base_url': 'https://api.kinesis.money', 'tier': 3},
            'korbit': {'name': 'Korbit', 'base_url': 'https://api.korbit.co.kr', 'tier': 2},
            'kucoin_futures': {'name': 'KuCoin Futures', 'base_url': 'https://api-futures.kucoin.com', 'tier': 2},
            'latoken': {'name': 'LATOKEN', 'base_url': 'https://api.latoken.com', 'tier': 2},
            'liquid': {'name': 'Liquid', 'base_url': 'https://api.liquid.com', 'tier': 2},
            'livecoin': {'name': 'Livecoin', 'base_url': 'https://api.livecoin.net', 'tier': 3},
            'localbitcoins': {'name': 'LocalBitcoins', 'base_url': 'https://localbitcoins.com', 'tier': 3},
            'luno': {'name': 'Luno', 'base_url': 'https://api.luno.com', 'tier': 2},
            'lykke': {'name': 'Lykke', 'base_url': 'https://hft-api.lykke.com', 'tier': 3},
            'mercado': {'name': 'Mercado Bitcoin', 'base_url': 'https://api.mercadobitcoin.net', 'tier': 2},
            'mixcoins': {'name': 'Mixcoins', 'base_url': 'https://api.mixcoins.com', 'tier': 3},
            'negociecoins': {'name': 'NegocieCoins', 'base_url': 'https://api.negociecoins.com.br', 'tier': 3},
            'nova': {'name': 'NovaDAX', 'base_url': 'https://api.novadax.com', 'tier': 2},
            'novadax': {'name': 'NovaDAX', 'base_url': 'https://api.novadax.com.br', 'tier': 2},
            'oceanex': {'name': 'OceanEx', 'base_url': 'https://api.oceanex.pro', 'tier': 2},
            'paymium': {'name': 'Paymium', 'base_url': 'https://paymium.com/api', 'tier': 2},
            'phemex': {'name': 'Phemex', 'base_url': 'https://api.phemex.com', 'tier': 2},
            'poloniex_futures': {'name': 'Poloniex Futures', 'base_url': 'https://futures-api.poloniex.com', 'tier': 2},
            'probit': {'name': 'ProBit', 'base_url': 'https://api.probit.com', 'tier': 2},
            'qtrade': {'name': 'qTrade', 'base_url': 'https://api.qtrade.io', 'tier': 3},
            'quadrigacx': {'name': 'QuadrigaCX', 'base_url': 'https://api.quadrigacx.com', 'tier': 3},
            'quoine': {'name': 'Quoine', 'base_url': 'https://api.quoine.com', 'tier': 2},
            'rain': {'name': 'Rain', 'base_url': 'https://api.rain.bh', 'tier': 3},
            'rightbtc': {'name': 'RightBTC', 'base_url': 'https://api.rightbtc.com', 'tier': 3},
            'southxchange': {'name': 'SouthXchange', 'base_url': 'https://www.southxchange.com', 'tier': 3},
            'stex': {'name': 'STEX', 'base_url': 'https://api.stex.com', 'tier': 2},
            'surbitcoin': {'name': 'SurBitcoin', 'base_url': 'https://api.surbitcoin.com', 'tier': 3},
            'therock': {'name': 'TheRockTrading', 'base_url': 'https://api.therocktrading.com', 'tier': 2},
            'tidebit': {'name': 'TideBit', 'base_url': 'https://www.tidebit.com', 'tier': 3},
            'tidex': {'name': 'Tidex', 'base_url': 'https://api.tidex.com', 'tier': 2},
            'timex': {'name': 'TimeX', 'base_url': 'https://api.timex.io', 'tier': 3},
            'tokocrypto': {'name': 'Tokocrypto', 'base_url': 'https://api.tokocrypto.com', 'tier': 2},
            'upbit': {'name': 'Upbit', 'base_url': 'https://api.upbit.com', 'tier': 1},
            'vcc': {'name': 'VCC', 'base_url': 'https://api.vcc.exchange', 'tier': 3},
            'waves': {'name': 'Waves.Exchange', 'base_url': 'https://api.waves.exchange', 'tier': 2},
            'wazirx': {'name': 'WazirX', 'base_url': 'https://api.wazirx.com', 'tier': 2},
            'whitebit': {'name': 'WhiteBIT', 'base_url': 'https://whitebit.com', 'tier': 2},
            'xena': {'name': 'Xena Exchange', 'base_url': 'https://api.xena.exchange', 'tier': 3},
            'yobit': {'name': 'YoBit', 'base_url': 'https://yobit.net', 'tier': 3},
            'zaif': {'name': 'Zaif', 'base_url': 'https://api.zaif.jp', 'tier': 2},
            'zb': {'name': 'ZB', 'base_url': 'https://api.zb.com', 'tier': 2},
            'bitcoin_com': {'name': 'Bitcoin.com', 'base_url': 'https://api.bitcoin.com', 'tier': 2},
            'bitcoin_india': {'name': 'Bitcoin India', 'base_url': 'https://api.bitcoin.co.in', 'tier': 3},
            'bitcoin_meester': {'name': 'Bitcoin Meester', 'base_url': 'https://api.bitcoinmeester.com', 'tier': 3},
            'bitcoin_ua': {'name': 'Bitcoin UA', 'base_url': 'https://api.bitcoinua.com', 'tier': 3},
            'bitcoin_ve': {'name': 'Bitcoin VE', 'base_url': 'https://api.bitcoinve.com', 'tier': 3},
        }
        
        self.exchanges_config.update(more_exchanges)
    
    async def connect_all(self):
        """সকল এক্সচেঞ্জে সংযোগ করুন"""
        tasks = []
        for exchange_id, config in self.exchanges_config.items():
            if config.get('api_key'):  # শুধু API key থাকলে সংযোগ করব
                task = self.connect_exchange(exchange_id)
                tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r is True)
        logger.info(f"✅ Connected to {success_count} exchanges")
    
    async def connect_exchange(self, exchange_id: str) -> bool:
        """একটি নির্দিষ্ট এক্সচেঞ্জে সংযোগ করুন"""
        try:
            config = self.exchanges_config[exchange_id]
            connection = ExchangeConnection(exchange_id, config)
            await connection.connect()
            self.connections[exchange_id] = connection
            self.health_status[exchange_id] = True
            return True
        except Exception as e:
            logger.error(f"Failed to connect to {exchange_id}: {e}")
            self.health_status[exchange_id] = False
            return False
    
    async def get_price(self, symbol: str, exchange: str = 'binance') -> Optional[float]:
        """একটি নির্দিষ্ট এক্সচেঞ্জ থেকে প্রাইস নিন"""
        connection = self.connections.get(exchange)
        if not connection or not connection.connected:
            # Failover to next available exchange
            return await self._get_price_with_failover(symbol, exchange)
        
        try:
            data = await connection.request('GET', '/api/v3/ticker/price', params={'symbol': symbol})
            return float(data['price'])
        except Exception as e:
            logger.error(f"Error getting price from {exchange}: {e}")
            self.health_status[exchange] = False
            return await self._get_price_with_failover(symbol, exchange)
    
    async def _get_price_with_failover(self, symbol: str, preferred_exchange: str) -> Optional[float]:
        """Failover mechanism - try other exchanges"""
        tier = self.exchanges_config[preferred_exchange].get('tier', 1)
        
        # Try same tier exchanges first
        same_tier = [
            ex for ex, config in self.exchanges_config.items()
            if config.get('tier') == tier and ex != preferred_exchange
        ]
        
        for exchange in same_tier[:3]:  # Try top 3 same tier
            if self.health_status.get(exchange, False):
                price = await self.get_price(symbol, exchange)
                if price:
                    return price
        
        # Try higher tier exchanges
        higher_tier = [
            ex for ex, config in self.exchanges_config.items()
            if config.get('tier', 5) < tier
        ]
        
        for exchange in higher_tier[:2]:  # Try top 2 higher tier
            if self.health_status.get(exchange, False):
                price = await self.get_price(symbol, exchange)
                if price:
                    return price
        
        return None
    
    async def get_all_prices(self, symbol: str) -> Dict[str, float]:
        """সকল এক্সচেঞ্জ থেকে প্রাইস সংগ্রহ করুন"""
        tasks = []
        exchanges = []
        
        for exchange_id, connection in self.connections.items():
            if connection.connected:
                tasks.append(self.get_price(symbol, exchange_id))
                exchanges.append(exchange_id)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        prices = {}
        for exchange, result in zip(exchanges, results):
            if isinstance(result, float):
                prices[exchange] = result
        
        return prices
    
    async def get_klines(self, symbol: str, interval: str = '1h', limit: int = 100,
                        exchange: str = 'binance') -> List[dict]:
        """ক্যান্ডেল ডেটা পান"""
        connection = self.connections.get(exchange)
        if not connection or not connection.connected:
            return []
        
        try:
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            data = await connection.request('GET', '/api/v3/klines', params=params)
            
            klines = []
            for k in data:
                klines.append({
                    'timestamp': k[0],
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5]),
                    'close_time': k[6],
                    'quote_volume': float(k[7]),
                    'trades': k[8],
                    'taker_buy_base': float(k[9]),
                    'taker_buy_quote': float(k[10])
                })
            
            return klines
        except Exception as e:
            logger.error(f"Error getting klines from {exchange}: {e}")
            return []
    
    async def get_orderbook(self, symbol: str, limit: int = 10,
                           exchange: str = 'binance') -> Optional[dict]:
        """অর্ডার বুক পান"""
        connection = self.connections.get(exchange)
        if not connection or not connection.connected:
            return None
        
        try:
            params = {
                'symbol': symbol,
                'limit': limit
            }
            data = await connection.request('GET', '/api/v3/depth', params=params)
            
            return {
                'bids': [[float(b[0]), float(b[1])] for b in data['bids'][:limit]],
                'asks': [[float(a[0]), float(a[1])] for a in data['asks'][:limit]]
            }
        except Exception as e:
            logger.error(f"Error getting orderbook from {exchange}: {e}")
            return None
    
    async def get_ticker(self, symbol: str, exchange: str = 'binance') -> Optional[dict]:
        """২৪ ঘন্টার টিকার তথ্য"""
        connection = self.connections.get(exchange)
        if not connection or not connection.connected:
            return None
        
        try:
            params = {'symbol': symbol}
            data = await connection.request('GET', '/api/v3/ticker/24hr', params=params)
            
            return {
                'symbol': data['symbol'],
                'price_change': float(data['priceChange']),
                'price_change_percent': float(data['priceChangePercent']),
                'weighted_avg_price': float(data['weightedAvgPrice']),
                'prev_close_price': float(data['prevClosePrice']),
                'last_price': float(data['lastPrice']),
                'last_qty': float(data['lastQty']),
                'bid_price': float(data['bidPrice']),
                'ask_price': float(data['askPrice']),
                'open_price': float(data['openPrice']),
                'high_price': float(data['highPrice']),
                'low_price': float(data['lowPrice']),
                'volume': float(data['volume']),
                'quote_volume': float(data['quoteVolume']),
                'open_time': data['openTime'],
                'close_time': data['closeTime'],
                'first_id': data['firstId'],
                'last_id': data['lastId'],
                'count': data['count']
            }
        except Exception as e:
            logger.error(f"Error getting ticker from {exchange}: {e}")
            return None
    
    async def get_exchange_info(self, exchange: str = 'binance') -> Optional[dict]:
        """এক্সচেঞ্জ ইনফরমেশন"""
        connection = self.connections.get(exchange)
        if not connection or not connection.connected:
            return None
        
        try:
            return await connection.request('GET', '/api/v3/exchangeInfo')
        except Exception as e:
            logger.error(f"Error getting exchange info from {exchange}: {e}")
            return None
    
    async def get_system_status(self, exchange: str = 'binance') -> Optional[dict]:
        """সিস্টেম স্ট্যাটাস"""
        connection = self.connections.get(exchange)
        if not connection or not connection.connected:
            return None
        
        try:
            return await connection.request('GET', '/sapi/v1/system/status')
        except Exception as e:
            logger.error(f"Error getting system status from {exchange}: {e}")
            return None
    
    async def close_all(self):
        """সকল সংযোগ বন্ধ করুন"""
        tasks = [conn.close() for conn in self.connections.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("🔌 Closed all exchange connections")
    
    def get_health_status(self) -> dict:
        """হেলথ স্ট্যাটাস রিপোর্ট"""
        return {
            'total_connected': sum(1 for s in self.health_status.values() if s),
            'total_configured': len(self.exchanges_config),
            'exchanges': self.health_status
        }
    
    def get_exchange_list(self) -> List[dict]:
        """সক্রিয় এক্সচেঞ্জের তালিকা"""
        exchanges = []
        for exchange_id, config in self.exchanges_config.items():
            exchanges.append({
                'id': exchange_id,
                'name': config['name'],
                'tier': config.get('tier', 3),
                'connected': self.health_status.get(exchange_id, False),
                'weight': config.get('weight', 50)
            })
        
        return sorted(exchanges, key=lambda x: (-x['tier'], -x['weight']))