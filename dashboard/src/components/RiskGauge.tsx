'use client';

interface Props {
  score: number;
  severity: string;
}

export function RiskGauge({ score = 0, severity = 'low' }: Props) {
  // Vibrant theme colors mapping
  const color = severity === 'critical' ? '#ef4444' // Red
    : severity === 'high' ? '#f97316' // Orange
    : severity === 'medium' ? '#eab308' // Yellow
    : '#10b981'; // Emerald Green

  const textGlowClass = severity === 'critical' ? 'text-glow-red'
    : severity === 'high' ? 'text-glow-orange'
    : severity === 'medium' ? 'text-glow-yellow'
    : 'text-glow-green';

  const pct = Math.min(Math.max(score, 0), 100) / 100;
  const circumference = Math.PI * 80; // semicircle radius 80
  const dash = pct * circumference;

  return (
    <div className="glass-panel p-6 flex flex-col items-center justify-center relative overflow-hidden">
      {/* Visual Background Glow */}
      <div 
        className="absolute w-36 h-36 rounded-full blur-[80px] opacity-10 pointer-events-none -top-10"
        style={{ backgroundColor: color }}
      />

      <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase mb-4">Risk Evaluation Meter</h3>
      
      <div className="relative">
        <svg width="200" height="110" viewBox="0 0 200 110" className="drop-shadow-lg">
          <defs>
            <filter id="neon-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Background Arc */}
          <path 
            d="M 20 100 A 80 80 0 0 1 180 100" 
            fill="none" 
            stroke="#1b2438" 
            strokeWidth="14" 
            strokeLinecap="round"
          />

          {/* Colored Active Arc */}
          <path 
            d="M 20 100 A 80 80 0 0 1 180 100" 
            fill="none" 
            stroke={color}
            strokeWidth="14" 
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circumference}`}
            filter="url(#neon-glow)"
            style={{ transition: 'stroke-dasharray 1.2s cubic-bezier(0.4, 0, 0.2, 1)' }}
          />

          {/* Core Score Text */}
          <text 
            x="100" 
            y="90" 
            textAnchor="middle" 
            fontSize="38" 
            fontWeight="900" 
            fill={color}
            className={`font-mono transition-all ${textGlowClass}`}
          >
            {score}
          </text>
          
          <text 
            x="100" 
            y="108" 
            textAnchor="middle" 
            fontSize="10" 
            fontWeight="700" 
            fill="#94a3b8" 
            className="tracking-widest"
          >
            STRESS SCORE
          </text>
        </svg>
      </div>

      <div 
        className="mt-3 px-4 py-1.5 rounded-full text-xs font-black tracking-widest transition-all duration-300 shadow-md border"
        style={{ 
          backgroundColor: color + '15', 
          borderColor: color + '40', 
          color 
        }}
      >
        {severity.toUpperCase()}
      </div>
    </div>
  );
}
