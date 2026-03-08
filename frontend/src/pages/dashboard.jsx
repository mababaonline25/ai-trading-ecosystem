"""
Main dashboard page
"""

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import { useSession } from 'next-auth/react';
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ComposedChart, Scatter
} from 'recharts';
import {
  TrendingUp, TrendingDown, DollarSign, Activity,
  AlertTriangle, Bell, Settings, LogOut,
  ChevronDown, Search, Filter, Download,
  RefreshCw, Plus, Minus, Star, StarOff,
  Clock, Calendar, BarChart2, PieChart,
  Users, MessageCircle, Share2, Bookmark
} from 'lucide-react';

import Layout from '../components/Layout';
import MarketOverview from '../components/dashboard/MarketOverview';
import PortfolioSummary from '../components/dashboard/PortfolioSummary';
import SignalList from '../components/dashboard/SignalList';
import AlertList from '../components/dashboard/AlertList';
import Charts from '../components/dashboard/Charts';
import NewsFeed from '../components/dashboard/NewsFeed';
import SocialFeed from '../components/dashboard/SocialFeed';
import PerformanceMetrics from '../components/dashboard/PerformanceMetrics';
import Watchlist from '../components/dashboard/Watchlist';
import QuickTrade from '../components/dashboard/QuickTrade';
import TechnicalIndicators from '../components/dashboard/TechnicalIndicators';
import AIPredictions from '../components/dashboard/AIPredictions';
import OnChainAnalysis from '../components/dashboard/OnChainAnalysis';
import SentimentAnalysis from '../components/dashboard/SentimentAnalysis';
import WhaleTracker from '../components/dashboard/WhaleTracker';
import FearGreedIndex from '../components/dashboard/FearGreedIndex';
import EconomicCalendar from '../components/dashboard/EconomicCalendar';
import TopGainersLosers from '../components/dashboard/TopGainersLosers';
import MostActive from '../components/dashboard/MostActive';
import TrendingDiscussions from '../components/dashboard/TrendingDiscussions';
import CopyTrading from '../components/dashboard/CopyTrading';
import Leaderboard from '../components/dashboard/Leaderboard';

import { useMarketData } from '../hooks/useMarketData';
import { useWebSocket } from '../hooks/useWebSocket';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';
import { formatters } from '../utils/formatters';
import { constants } from '../utils/constants';

export default function Dashboard() {
  const router = useRouter();
  const { data: session, status } = useSession();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedSymbol, setSelectedSymbol] = useState('BTCUSDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [marketData, setMarketData] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [signals, setSignals] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showQuickTrade, setShowQuickTrade] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(5000);
  const [theme, setTheme] = useState('dark');
  
  // WebSocket connection
  const { lastMessage, sendMessage } = useWebSocket(
    `wss://api.tradingecosystem.com/ws/market/${selectedSymbol}`
  );
  
  // Market data hook
  const { data: realTimeData, error: wsError } = useMarketData(
    selectedSymbol,
    refreshInterval
  );
  
  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/login');
    }
  }, [status, router]);
  
  useEffect(() => {
    fetchInitialData();
  }, [selectedSymbol, timeframe]);
  
  useEffect(() => {
    if (lastMessage) {
      handleWebSocketMessage(lastMessage);
    }
  }, [lastMessage]);
  
  const fetchInitialData = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const [marketRes, portfolioRes, signalsRes, alertsRes, watchlistRes] = await Promise.all([
        api.getMarketData(selectedSymbol, timeframe),
        api.getPortfolio(),
        api.getRecentSignals(20, selectedSymbol),
        api.getAlerts(),
        api.getWatchlist()
      ]);
      
      setMarketData(marketRes.data);
      setPortfolio(portfolioRes.data);
      setSignals(signalsRes.data.signals);
      setAlerts(alertsRes.data);
      setWatchlist(watchlistRes.data.watchlist);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching initial data:', err);
    } finally {
      setIsLoading(false);
    }
  };
  
  const handleWebSocketMessage = (message) => {
    const data = JSON.parse(message.data);
    
    switch (data.type) {
      case 'price_update':
        updatePrice(data.symbol, data.price);
        break;
      case 'new_signal':
        addNewSignal(data.signal);
        break;
      case 'alert_triggered':
        handleAlert(data.alert);
        break;
      case 'portfolio_update':
        updatePortfolio(data.portfolio);
        break;
      default:
        console.log('Unknown message type:', data.type);
    }
  };
  
  const updatePrice = (symbol, price) => {
    setMarketData(prev => ({
      ...prev,
      current_price: price,
      last_updated: new Date().toISOString()
    }));
  };
  
  const addNewSignal = (signal) => {
    setSignals(prev => [signal, ...prev].slice(0, 50));
  };
  
  const handleAlert = (alert) => {
    // Show notification
    if (Notification.permission === 'granted') {
      new Notification('Alert Triggered!', {
        body: `${alert.symbol}: ${alert.message}`,
        icon: '/alert-icon.png'
      });
    }
    
    setAlerts(prev => [...prev, alert]);
  };
  
  const updatePortfolio = (newPortfolio) => {
    setPortfolio(newPortfolio);
  };
  
  const refreshData = () => {
    fetchInitialData();
  };
  
  const addToWatchlist = async (symbol) => {
    try {
      await api.addToWatchlist(symbol);
      setWatchlist(prev => [...prev, symbol]);
    } catch (err) {
      console.error('Error adding to watchlist:', err);
    }
  };
  
  const removeFromWatchlist = async (symbol) => {
    try {
      await api.removeFromWatchlist(symbol);
      setWatchlist(prev => prev.filter(s => s !== symbol));
    } catch (err) {
      console.error('Error removing from watchlist:', err);
    }
  };
  
  const handleSymbolChange = (symbol) => {
    setSelectedSymbol(symbol);
    setShowQuickTrade(false);
  };
  
  const handleTimeframeChange = (tf) => {
    setTimeframe(tf);
  };
  
  const tabs = [
    { id: 'overview', label: 'Overview', icon: BarChart2 },
    { id: 'portfolio', label: 'Portfolio', icon: DollarSign },
    { id: 'signals', label: 'Signals', icon: Activity },
    { id: 'alerts', label: 'Alerts', icon: Bell },
    { id: 'analysis', label: 'Analysis', icon: TrendingUp },
    { id: 'social', label: 'Social', icon: Users },
    { id: 'ai', label: 'AI Predictions', icon: Activity },
    { id: 'onchain', label: 'On-Chain', icon: Activity },
    { id: 'copytrading', label: 'Copy Trading', icon: Share2 }
  ];
  
  const timeframes = [
    { value: '1m', label: '1m' },
    { value: '5m', label: '5m' },
    { value: '15m', label: '15m' },
    { value: '1h', label: '1h' },
    { value: '4h', label: '4h' },
    { value: '1d', label: '1d' },
    { value: '1w', label: '1w' }
  ];
  
  if (status === 'loading' || isLoading) {
    return (
      <Layout>
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading dashboard...</p>
          </div>
        </div>
      </Layout>
    );
  }
  
  return (
    <Layout>
      <Head>
        <title>Dashboard - AI Trading Ecosystem</title>
        <meta name="description" content="AI-powered cryptocurrency trading platform" />
      </Head>
      
      <div className="min-h-screen bg-gradient-to-br from-gray-900 to-gray-800 text-white">
        {/* Header */}
        <header className="bg-gray-800 shadow-lg border-b border-gray-700">
          <div className="container mx-auto px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                  AI Trading Ecosystem
                </h1>
                
                {/* Symbol Selector */}
                <div className="relative">
                  <select
                    value={selectedSymbol}
                    onChange={(e) => handleSymbolChange(e.target.value)}
                    className="bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {constants.POPULAR_SYMBOLS.map(symbol => (
                      <option key={symbol} value={symbol}>{symbol}</option>
                    ))}
                  </select>
                </div>
                
                {/* Timeframe Selector */}
                <div className="flex space-x-1 bg-gray-700 rounded-lg p-1">
                  {timeframes.map(tf => (
                    <button
                      key={tf.value}
                      onClick={() => handleTimeframeChange(tf.value)}
                      className={`px-3 py-1 rounded text-sm font-medium transition ${
                        timeframe === tf.value
                          ? 'bg-blue-600 text-white'
                          : 'text-gray-400 hover:text-white hover:bg-gray-600'
                      }`}
                    >
                      {tf.label}
                    </button>
                  ))}
                </div>
              </div>
              
              {/* Right side buttons */}
              <div className="flex items-center space-x-4">
                <button
                  onClick={refreshData}
                  className="p-2 hover:bg-gray-700 rounded-lg transition"
                >
                  <RefreshCw className="w-5 h-5" />
                </button>
                
                <button
                  onClick={() => setShowQuickTrade(true)}
                  className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg font-medium transition flex items-center space-x-2"
                >
                  <Plus className="w-4 h-4" />
                  <span>Quick Trade</span>
                </button>
                
                <div className="relative">
                  <Bell className="w-5 h-5 text-gray-400 cursor-pointer hover:text-white" />
                  {alerts.filter(a => !a.read).length > 0 && (
                    <span className="absolute -top-1 -right-1 bg-red-500 text-xs rounded-full w-4 h-4 flex items-center justify-center">
                      {alerts.filter(a => !a.read).length}
                    </span>
                  )}
                </div>
                
                <button className="p-2 hover:bg-gray-700 rounded-lg transition">
                  <Settings className="w-5 h-5" />
                </button>
                
                <div className="relative group">
                  <button className="flex items-center space-x-2 hover:bg-gray-700 rounded-lg px-3 py-2 transition">
                    <img
                      src={user?.avatar || '/default-avatar.png'}
                      alt="Profile"
                      className="w-6 h-6 rounded-full"
                    />
                    <span className="text-sm">{user?.username}</span>
                    <ChevronDown className="w-4 h-4" />
                  </button>
                  
                  {/* Dropdown menu */}
                  <div className="absolute right-0 mt-2 w-48 bg-gray-800 rounded-lg shadow-lg py-1 hidden group-hover:block">
                    <a href="/profile" className="block px-4 py-2 hover:bg-gray-700">Profile</a>
                    <a href="/settings" className="block px-4 py-2 hover:bg-gray-700">Settings</a>
                    <button className="w-full text-left px-4 py-2 hover:bg-gray-700 text-red-400">
                      Logout
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </header>
        
        {/* Main content */}
        <main className="container mx-auto px-6 py-8">
          {/* Tabs */}
          <div className="flex space-x-1 mb-8 border-b border-gray-700">
            {tabs.map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center space-x-2 px-4 py-2 font-medium transition border-b-2 ${
                    activeTab === tab.id
                      ? 'border-blue-500 text-blue-400'
                      : 'border-transparent text-gray-400 hover:text-white hover:border-gray-600'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
          
          {/* Error message */}
          {error && (
            <div className="bg-red-500 bg-opacity-20 border border-red-500 rounded-lg p-4 mb-6">
              <p className="text-red-400">{error}</p>
            </div>
          )}
          
          {/* Tab content */}
          <div className="space-y-6">
            {activeTab === 'overview' && (
              <div className="grid grid-cols-12 gap-6">
                {/* Market Overview - 8 columns */}
                <div className="col-span-8">
                  <MarketOverview
                    symbol={selectedSymbol}
                    data={marketData}
                    timeframe={timeframe}
                  />
                </div>
                
                {/* Portfolio Summary - 4 columns */}
                <div className="col-span-4">
                  <PortfolioSummary
                    portfolio={portfolio}
                    onQuickTrade={() => setShowQuickTrade(true)}
                  />
                </div>
                
                {/* Charts - 12 columns */}
                <div className="col-span-12">
                  <Charts
                    symbol={selectedSymbol}
                    timeframe={timeframe}
                    data={marketData}
                  />
                </div>
                
                {/* Technical Indicators - 6 columns */}
                <div className="col-span-6">
                  <TechnicalIndicators
                    symbol={selectedSymbol}
                    timeframe={timeframe}
                  />
                </div>
                
                {/* Fear & Greed Index - 3 columns */}
                <div className="col-span-3">
                  <FearGreedIndex />
                </div>
                
                {/* Economic Calendar - 3 columns */}
                <div className="col-span-3">
                  <EconomicCalendar />
                </div>
                
                {/* Top Gainers/Losers - 4 columns */}
                <div className="col-span-4">
                  <TopGainersLosers />
                </div>
                
                {/* Most Active - 4 columns */}
                <div className="col-span-4">
                  <MostActive />
                </div>
                
                {/* News Feed - 4 columns */}
                <div className="col-span-4">
                  <NewsFeed />
                </div>
              </div>
            )}
            
            {activeTab === 'portfolio' && (
              <div className="grid grid-cols-12 gap-6">
                {/* Portfolio Chart */}
                <div className="col-span-8">
                  <div className="bg-gray-800 rounded-xl p-6">
                    <h2 className="text-xl font-bold mb-4">Portfolio Performance</h2>
                    <ResponsiveContainer width="100%" height={400}>
                      <AreaChart data={portfolio?.history || []}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis dataKey="date" stroke="#9CA3AF" />
                        <YAxis stroke="#9CA3AF" />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#1F2937', border: 'none' }}
                          labelStyle={{ color: '#9CA3AF' }}
                        />
                        <Area
                          type="monotone"
                          dataKey="value"
                          stroke="#3B82F6"
                          fill="#3B82F6"
                          fillOpacity={0.1}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
                
                {/* Holdings */}
                <div className="col-span-4">
                  <div className="bg-gray-800 rounded-xl p-6">
                    <h2 className="text-xl font-bold mb-4">Holdings</h2>
                    <div className="space-y-4">
                      {portfolio?.holdings?.map(holding => (
                        <div key={holding.symbol} className="flex justify-between items-center">
                          <div>
                            <p className="font-medium">{holding.symbol}</p>
                            <p className="text-sm text-gray-400">{holding.amount} units</p>
                          </div>
                          <div className="text-right">
                            <p className="font-medium">${holding.value.toLocaleString()}</p>
                            <p className={`text-sm ${holding.change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {holding.change >= 0 ? '+' : ''}{holding.change}%
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                
                {/* Performance Metrics */}
                <div className="col-span-12">
                  <PerformanceMetrics data={portfolio?.metrics} />
                </div>
              </div>
            )}
            
            {activeTab === 'signals' && (
              <SignalList
                signals={signals}
                onSymbolClick={handleSymbolChange}
              />
            )}
            
            {activeTab === 'alerts' && (
              <AlertList
                alerts={alerts}
                onAlertClick={handleAlert}
              />
            )}
            
            {activeTab === 'analysis' && (
              <div className="grid grid-cols-12 gap-6">
                {/* Technical Analysis */}
                <div className="col-span-8">
                  <TechnicalIndicators
                    symbol={selectedSymbol}
                    timeframe={timeframe}
                    fullPage
                  />
                </div>
                
                {/* Sentiment Analysis */}
                <div className="col-span-4">
                  <SentimentAnalysis symbol={selectedSymbol} />
                </div>
                
                {/* On-Chain Analysis */}
                <div className="col-span-6">
                  <OnChainAnalysis symbol={selectedSymbol} />
                </div>
                
                {/* Whale Tracker */}
                <div className="col-span-6">
                  <WhaleTracker symbol={selectedSymbol} />
                </div>
              </div>
            )}
            
            {activeTab === 'social' && (
              <div className="grid grid-cols-12 gap-6">
                {/* Social Feed */}
                <div className="col-span-8">
                  <SocialFeed />
                </div>
                
                {/* Trending Discussions */}
                <div className="col-span-4">
                  <TrendingDiscussions />
                </div>
              </div>
            )}
            
            {activeTab === 'ai' && (
              <AIPredictions
                symbol={selectedSymbol}
                timeframe={timeframe}
              />
            )}
            
            {activeTab === 'onchain' && (
              <OnChainAnalysis
                symbol={selectedSymbol}
                fullPage
              />
            )}
            
            {activeTab === 'copytrading' && (
              <div className="grid grid-cols-12 gap-6">
                {/* Leaderboard */}
                <div className="col-span-8">
                  <Leaderboard />
                </div>
                
                {/* Copy Trading Settings */}
                <div className="col-span-4">
                  <CopyTrading />
                </div>
              </div>
            )}
          </div>
        </main>
        
        {/* Quick Trade Modal */}
        {showQuickTrade && (
          <QuickTrade
            symbol={selectedSymbol}
            price={marketData?.current_price}
            onClose={() => setShowQuickTrade(false)}
            onTradeComplete={refreshData}
          />
        )}
        
        {/* Footer */}
        <footer className="bg-gray-800 border-t border-gray-700 mt-12">
          <div className="container mx-auto px-6 py-4">
            <div className="flex justify-between items-center text-sm text-gray-400">
              <p>© 2026 AI Trading Ecosystem. All rights reserved.</p>
              <div className="flex space-x-4">
                <a href="/terms" className="hover:text-white">Terms</a>
                <a href="/privacy" className="hover:text-white">Privacy</a>
                <a href="/contact" className="hover:text-white">Contact</a>
              </div>
            </div>
          </div>
        </footer>
      </div>
    </Layout>
  );
}