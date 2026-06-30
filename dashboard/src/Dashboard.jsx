import { useState, useEffect, useRef } from 'react';

export default function Dashboard() {
  const icons = {
    newspaper: (
      <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/></svg>
    ),
    brain: (
      <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-2.04Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-2.04Z"/><path d="M12 4.5V9"/><path d="M12 15v4.5"/></svg>
    ),
    activity: (
      <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
    ),
    send: (
      <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6"><path d="m22 2-7 20-4-9-9-4 20-7z"/><path d="M22 2 11 13"/></svg>
    ),
    arrowRight: (
      <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
    )
  };

  // State for real API data
  const [kpis, setKpis] = useState({
    winRate: "--%",
    roi: "--%",
    maxDrawdown: "--%",
    totalTrades: "--"
  });
  
  const [signals, setSignals] = useState([]);
  const [logs, setLogs] = useState([]);
  const [isLive, setIsLive] = useState(false);
  
  const logsContainerRef = useRef(null);

  useEffect(() => {
    const API_BASE_URL = import.meta.env.VITE_API_URL;

    const fetchDashboardData = async () => {
      try {
        // Fetch KPIs from existing backend endpoint
        const metricsRes = await fetch(`${API_BASE_URL}/api/metrics`);
        if (metricsRes.ok) {
          const metricsData = await metricsRes.json();
          if (metricsData.kpis) {
            setKpis({
              winRate: typeof metricsData.kpis.win_rate === 'number' ? `${(metricsData.kpis.win_rate).toFixed(1)}%` : metricsData.kpis.win_rate,
              roi: typeof metricsData.kpis.roi === 'number' ? `${(metricsData.kpis.roi).toFixed(2)}%` : metricsData.kpis.roi,
              maxDrawdown: typeof metricsData.kpis.max_drawdown === 'number' ? `${(metricsData.kpis.max_drawdown).toFixed(2)}%` : metricsData.kpis.max_drawdown,
              totalTrades: metricsData.kpis.total_trades
            });
            setIsLive(true);
          }
        }

        // Fetch Signals (requires adding the endpoint in main.py)
        const signalsRes = await fetch(`${API_BASE_URL}/api/signals`);
        if (signalsRes.ok) {
          const signalsData = await signalsRes.json();
          setSignals(signalsData);
        }

        const logsRes = await fetch(`${API_BASE_URL}/api/logs`);
        if (logsRes.ok) {
          const logsData = await logsRes.json();
          setLogs(logsData);
        }
      } catch (error) {
        console.error("Error fetching live data:", error);
        setIsLive(false);
      }
    };

    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 10000); // Refresh every 10s
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (logsContainerRef.current) {
      // This specifically scrolls ONLY the logs container, not the window
      logsContainerRef.current.scrollTo({
        top: logsContainerRef.current.scrollHeight,
        behavior: "smooth"
      });
    }
  }, [logs]);

  const metrics = [
    { label: "Win Rate", value: kpis.winRate, icon: icons.brain, textClass: "text-emerald-400", gradientClass: "from-emerald-500/50" },
    { label: "Strategy ROI", value: kpis.roi, icon: icons.activity, textClass: "text-cyan-400", gradientClass: "from-cyan-500/50" },
    { label: "Total Trades", value: kpis.totalTrades.toString(), icon: icons.send, textClass: "text-blue-400", gradientClass: "from-blue-500/50" },
    { label: "Max Drawdown", value: kpis.maxDrawdown, icon: icons.newspaper, textClass: "text-red-400", gradientClass: "from-red-500/50" }
  ];

  const pipeline = [
    { title: "Data Ingest", subtitle: "SoSoValue News Stream", icon: icons.newspaper, bgClass: "bg-emerald-500/20", borderClass: "border-emerald-500/30" },
    { title: "AI Analysis", subtitle: "Groq LLM Sentiment Parsing", icon: icons.brain, bgClass: "bg-cyan-500/20", borderClass: "border-cyan-500/30" },
    { title: "Signal Generation", subtitle: "Bullish/Bearish Scoring", icon: icons.activity, bgClass: "bg-blue-500/20", borderClass: "border-blue-500/30" },
    { title: "Execution", subtitle: "Telegram Dispatch & Vault Tx", icon: icons.send, bgClass: "bg-indigo-500/20", borderClass: "border-indigo-500/30" }
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-zinc-100 py-4 px-8 md:py-6 md:px-10 lg:py-8 lg:px-12 relative overflow-hidden font-sans">
      <style>{`
        @keyframes scroll {
          0% { transform: translateY(0); }
          100% { transform: translateY(-50%); }
        }
        @keyframes slide {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(300%); }
        }
        .animate-scroll {
          animation: scroll 25s linear infinite;
        }
        .animate-slide {
          animation: slide 2s ease-in-out infinite;
        }
      `}</style>
      
      {/* Background grid */}
      <div className="fixed inset-0 z-0 pointer-events-none opacity-20" style={{
        backgroundImage: 'linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)',
        backgroundSize: '40px 40px'
      }} />
      
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-emerald-500/5 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl" />
      </div>

      {/* Header */}
      <header className="relative flex flex-col md:flex-row items-center justify-between mb-8 gap-4 z-10">
        <div className="text-2xl md:text-3xl font-bold tracking-tighter">
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 via-cyan-400 to-blue-500">
            SentiTrade AI
          </span>
        </div>
        
        <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-slate-900/50 border border-slate-800/50 backdrop-blur-md shadow-[0_0_15px_rgba(16,185,129,0.1)]">
          <span className="relative flex h-3 w-3">
            <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${isLive ? 'bg-emerald-400 animate-ping' : 'bg-red-400'}`}></span>
            <span className={`relative inline-flex rounded-full h-3 w-3 ${isLive ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
          </span>
          <span className="text-sm font-medium text-zinc-300">
            System Status: {isLive ? 'Live' : 'Connecting...'}
          </span>
        </div>
        
        <div className="flex items-center gap-3">
          <span className="px-3 py-1.5 rounded-full bg-slate-900/50 border border-slate-800/50 text-xs font-mono text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.1)]">
            LLM: Groq
          </span>
        </div>
      </header>

      {/* Top Metrics Row */}
      <div className="relative grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8 z-10">
        {metrics.map((m, i) => (
          <div key={i} className="group relative p-5 rounded-2xl bg-slate-900/40 backdrop-blur-xl border border-slate-800/50 hover:border-slate-700/50 transition-all duration-300 overflow-hidden">
            <div className={`absolute top-0 right-0 p-3 opacity-80 group-hover:scale-110 transition-transform duration-300 ${m.textClass}`}>
              {m.icon}
            </div>
            <p className="text-sm text-zinc-400 mb-1">{m.label}</p>
            <p className="text-2xl font-bold text-white tracking-tight">{m.value}</p>
            <div className={`absolute bottom-0 left-0 h-1 w-full bg-gradient-to-r ${m.gradientClass} to-transparent opacity-50`} />
          </div>
        ))}
      </div>

      {/* Live Signal Pipeline Visualizer */}
      <div className="relative mb-8 p-6 md:p-8 rounded-3xl bg-slate-900/30 backdrop-blur-xl border border-slate-800/50 overflow-hidden z-10">
        <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/[0.05] via-transparent to-cyan-500/[0.05] pointer-events-none" />
        <h2 className="relative text-lg font-semibold mb-8 text-zinc-200 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          Live Signal Pipeline
        </h2>
        
        <div className="relative flex flex-col md:flex-row items-center justify-between gap-2 md:gap-0">
          {pipeline.map((node, i) => (
            <div key={i} className="contents">
              <div className="flex flex-col items-center text-center z-10 w-full md:w-auto px-2">
                <div className={`w-14 h-14 md:w-16 md:h-16 rounded-2xl flex items-center justify-center mb-3 ${node.bgClass} border ${node.borderClass} shadow-[0_0_20px_rgba(0,0,0,0.3)]`}>
                  <div className="text-white">{node.icon}</div>
                </div>
                <h3 className="font-semibold text-zinc-200 text-sm md:text-base">{node.title}</h3>
                <p className="text-xs text-zinc-500 mt-1 max-w-[160px] leading-relaxed">{node.subtitle}</p>
              </div>
              
              {i < pipeline.length - 1 && (
                <div className="hidden md:flex flex-1 items-center justify-center px-2 max-w-[200px]">
                  <div className="h-px w-full bg-gradient-to-r from-emerald-500/40 via-cyan-500/40 to-blue-500/40 relative overflow-hidden">
                    <div className="absolute inset-0 w-1/2 h-full bg-gradient-to-r from-transparent via-white/30 to-transparent animate-slide" />
                  </div>
                  <div className="text-cyan-500/60 -ml-1">{icons.arrowRight}</div>
                </div>
              )}
              
              {i < pipeline.length - 1 && (
                <div className="md:hidden flex flex-col items-center py-1">
                  <div className="w-px h-8 bg-gradient-to-b from-emerald-500/40 via-cyan-500/40 to-blue-500/40" />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Bottom Section */}
      <div className="relative grid grid-cols-1 lg:grid-cols-2 gap-6 z-10">
        {/* Live Activity Feed */}
        <div className="p-5 rounded-2xl bg-slate-900/40 backdrop-blur-xl border border-slate-800/50">
          <h2 className="text-lg font-semibold mb-4 text-zinc-200 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse" />
            Live Activity Feed
          </h2>
          <div className="h-64 overflow-y-auto relative rounded-xl bg-slate-950/50 border border-slate-800/30 p-3 flex flex-col scrollbar-thin scrollbar-thumb-slate-800">
              {logs.length > 0 ? logs.map((log, i) => (
                <div key={i} className="text-xs font-mono text-zinc-400 py-1.5 border-b border-slate-800/30 last:border-0 break-words">
                  <span className={log.includes("ERROR") ? "text-red-500/80" : "text-emerald-500/80"}>➜</span> {log}
                </div>
              )) : (
                <div className="text-xs font-mono text-zinc-500 py-1.5 text-center mt-20">
                  Awaiting agent initialization...
                </div>
              )}
              <div ref={logsContainerRef} />
            </div>
          </div>

        {/* Recent Signals Table */}
        <div className="p-5 rounded-2xl bg-slate-900/40 backdrop-blur-xl border border-slate-800/50">
          <h2 className="text-lg font-semibold mb-4 text-zinc-200 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
            Recent Signals
          </h2>
          <div className="overflow-x-auto rounded-xl border border-slate-800/30">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-zinc-500 uppercase bg-slate-950/50">
                <tr>
                  <th className="px-4 py-3 font-medium">Time</th>
                  <th className="px-4 py-3 font-medium">Asset</th>
                  <th className="px-4 py-3 font-medium">Sentiment</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/30">
                {signals.length > 0 ? signals.map((s, i) => (
                  <tr key={i} className="hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-3 text-zinc-400 font-mono text-xs">{s.time}</td>
                    <td className="px-4 py-3 font-medium text-white">{s.asset}</td>
                    <td className="px-4 py-3">
                      {s.sentiment === "Bullish" && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                          {s.sentiment} ({s.score})
                        </span>
                      )}
                      {s.sentiment === "Bearish" && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border bg-red-500/10 text-red-400 border-red-500/20">
                          {s.sentiment} ({s.score})
                        </span>
                      )}
                      {s.sentiment === "Neutral" && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border bg-amber-500/10 text-amber-400 border-amber-500/20">
                          {s.sentiment} ({s.score})
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {s.action === "BUY" && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                          {s.action}
                        </span>
                      )}
                      {s.action === "SELL" && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border bg-red-500/10 text-red-400 border-red-500/20">
                          {s.action}
                        </span>
                      )}
                      {s.action === "HOLD" && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border bg-amber-500/10 text-amber-400 border-amber-500/20">
                          {s.action}
                        </span>
                      )}
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan="4" className="px-4 py-8 text-center text-zinc-500">No signals found in the database yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}