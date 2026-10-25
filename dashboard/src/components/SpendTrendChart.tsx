'use client';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer, 
  ReferenceLine, 
  CartesianGrid 
} from 'recharts';

interface Props {
  data: { month: string; amount: number; }[];
  emiAmount: number;
}

export function SpendTrendChart({ data, emiAmount = 0 }: Props) {
  return (
    <div className="glass-panel p-6 overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 mb-6">
        <div>
          <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase">Monthly cash outflow</h3>
          <p className="text-xs text-gray-500">Monthly debits from EWS.TXNSUMM compared with the monthly EMI</p>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-semibold">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded bg-indigo-500"></span>
            <span className="text-gray-300 whitespace-nowrap">Spend outflow</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-1 border-t-2 border-dashed border-red-500"></span>
            <span className="text-gray-300 whitespace-nowrap">EMI ₹{Math.round(emiAmount).toLocaleString('en-IN')}</span>
          </div>
        </div>
      </div>

      <div className="h-[220px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="spendGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4}/>
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0}/>
              </linearGradient>
            </defs>
            
            <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" vertical={false} />
            
            <XAxis 
              dataKey="month" 
              tick={{ fontSize: 11, fill: '#94a3b8' }} 
              axisLine={false}
              tickLine={false}
            />
            
            <YAxis 
              tick={{ fontSize: 11, fill: '#94a3b8' }} 
              tickFormatter={(v) => `₹${(v/1000).toFixed(0)}k`} 
              axisLine={false}
              tickLine={false}
            />
            
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#131926', 
                borderColor: '#1f293d', 
                borderRadius: '12px',
                color: '#f3f4f6'
              }}
              formatter={(v: number) => [`₹${v.toLocaleString('en-IN')}`, 'Amount']}
            />
            
            <ReferenceLine 
              y={emiAmount} 
              stroke="#ef4444" 
              strokeDasharray="4 4" 
              strokeWidth={1.5}
            />
            
            <Area 
              type="monotone" 
              dataKey="amount" 
              stroke="#6366f1" 
              strokeWidth={2.5}
              fillOpacity={1} 
              fill="url(#spendGrad)"
              isAnimationActive={false} 
              dot={{ r: 4, stroke: '#131926', strokeWidth: 1.5, fill: '#6366f1' }}
              activeDot={{ r: 6 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
