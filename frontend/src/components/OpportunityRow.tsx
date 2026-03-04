import { useEffect, useState } from 'react'
import { clsx } from 'clsx'
import { ExternalLink, AlertTriangle, AlertCircle } from 'lucide-react'
import type { AuctionOpportunity } from '../api/hooks'

interface Props {
  item: AuctionOpportunity
  onClick: () => void
}

/** Live client-side countdown that ticks every second without server calls */
function useCountdown(endsAt: string, initialSeconds: number) {
  const [seconds, setSeconds] = useState(initialSeconds)

  useEffect(() => {
    const endMs = new Date(endsAt).getTime()
    const tick = () => {
      const remaining = Math.max(0, (endMs - Date.now()) / 1000)
      setSeconds(remaining)
    }
    tick()
    const interval = setInterval(tick, 1000)
    return () => clearInterval(interval)
  }, [endsAt])

  return seconds
}

function formatCountdown(seconds: number): { text: string; urgent: boolean; critical: boolean } {
  if (seconds <= 0) return { text: 'Ended', urgent: false, critical: false }
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const urgent = seconds < 6 * 3600
  const critical = seconds < 2 * 3600
  if (h > 0) return { text: `${h}h ${m}m`, urgent, critical }
  if (m > 0) return { text: `${m}m ${s}s`, urgent, critical }
  return { text: `${s}s`, urgent, critical }
}

function ScoreBar({ score, max = 100 }: { score: number; max?: number }) {
  const pct = Math.min(100, (score / max) * 100)
  const color = score >= 60 ? 'bg-green-500' : score >= 35 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full', color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-gray-300">{score.toFixed(1)}</span>
    </div>
  )
}

export default function OpportunityRow({ item, onClick }: Props) {
  const secondsRemaining = useCountdown(item.ends_at, item.seconds_remaining)
  const { text: countdownText, urgent, critical } = formatCountdown(secondsRemaining)
  const margin = item.profit_margin_pct

  const rowColor = margin == null
    ? ''
    : margin >= 30
    ? 'border-l-2 border-green-600'
    : margin >= 15
    ? 'border-l-2 border-yellow-600'
    : 'border-l-2 border-red-700'

  return (
    <tr
      onClick={onClick}
      className={clsx(
        'hover:bg-gray-800/60 cursor-pointer transition-colors border-b border-gray-800/50',
        rowColor,
      )}
    >
      {/* Item */}
      <td className="px-3 py-3">
        <div className="flex items-center gap-3">
          {item.image_url ? (
            <img src={item.image_url} alt="" className="w-10 h-10 rounded object-cover shrink-0 bg-gray-800" />
          ) : (
            <div className="w-10 h-10 rounded bg-gray-800 shrink-0" />
          )}
          <div className="min-w-0">
            <div className="flex items-start gap-1.5">
              <p className="text-sm font-medium text-gray-100 line-clamp-2 leading-tight">{item.title}</p>
              {item.data_quality_warning && (
                <span title={item.data_quality_warning} className="shrink-0 mt-0.5">
                  <AlertCircle size={13} className="text-yellow-500" />
                </span>
              )}
            </div>
            <a
              href={item.item_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className="text-xs text-blue-400 hover:underline inline-flex items-center gap-0.5 mt-0.5"
            >
              View on eBay <ExternalLink size={10} />
            </a>
          </div>
        </div>
      </td>

      {/* Current bid */}
      <td className="px-3 py-3 text-right">
        <span className="font-mono text-sm text-gray-200">${item.current_bid_usd.toFixed(2)}</span>
        {item.bid_count > 0 && (
          <p className="text-xs text-gray-500">{item.bid_count} bid{item.bid_count !== 1 ? 's' : ''}</p>
        )}
      </td>

      {/* Est. final */}
      <td className="px-3 py-3 text-right">
        <span className="font-mono text-sm text-gray-300">${item.estimated_final_usd.toFixed(2)}</span>
        {item.current_bid_usd > 0 && (
          <p className="text-xs text-gray-600">
            +{((item.estimated_final_usd / item.current_bid_usd - 1) * 100).toFixed(0)}%
          </p>
        )}
      </td>

      {/* Landed cost */}
      <td className="px-3 py-3 text-right">
        <span className="font-mono text-sm text-orange-300">${item.total_landed_cost_usd.toFixed(2)}</span>
        <p className="text-xs text-gray-500">{item.total_landed_cost_gel.toFixed(0)} ₾</p>
      </td>

      {/* Georgian price */}
      <td className="px-3 py-3 text-right">
        {item.georgian_median_price_gel != null ? (
          <>
            <span className="font-mono text-sm text-green-400">{item.georgian_median_price_gel.toFixed(0)} ₾</span>
            <p className="text-xs text-gray-500">{item.georgian_listing_count} listing{item.georgian_listing_count !== 1 ? 's' : ''}</p>
          </>
        ) : (
          <span className="text-xs text-gray-600 flex items-center justify-end gap-1">
            <AlertTriangle size={12} /> No data
          </span>
        )}
      </td>

      {/* Profit % */}
      <td className="px-3 py-3 text-right">
        {margin != null ? (
          <span className={clsx(
            'font-mono text-sm font-semibold',
            margin >= 30 ? 'text-green-400' : margin >= 15 ? 'text-yellow-400' : 'text-red-400',
          )}>
            {margin >= 0 ? '+' : ''}{margin.toFixed(1)}%
          </span>
        ) : (
          <span className="text-gray-600 text-sm">—</span>
        )}
        {item.profit_gel != null && (
          <p className="text-xs text-gray-500">{item.profit_gel >= 0 ? '+' : ''}{item.profit_gel.toFixed(0)} ₾</p>
        )}
      </td>

      {/* Ends in — live ticking */}
      <td className="px-3 py-3 text-center">
        <span className={clsx(
          'text-xs px-2 py-1 rounded-full font-mono tabular-nums',
          critical ? 'bg-red-900/80 text-red-300 animate-pulse border border-red-700'
            : urgent ? 'bg-orange-900/60 text-orange-300 border border-orange-700'
            : 'bg-gray-800 text-gray-400',
        )}>
          {countdownText}
        </span>
      </td>

      {/* Score */}
      <td className="px-3 py-3">
        <ScoreBar score={item.opportunity_score} />
      </td>
    </tr>
  )
}
