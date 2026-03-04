/**
 * G4: Upcoming Endings view — auctions ending in the next 6h, grouped into
 * time buckets with opportunity scores so the user knows which to bid on first.
 */
import { ExternalLink, Flame } from 'lucide-react'
import { clsx } from 'clsx'
import type { AuctionOpportunity } from '../api/hooks'

interface Props {
  items: AuctionOpportunity[]
  onItemClick: (id: string) => void
}

interface Bucket {
  label: string
  maxSeconds: number
  colorClass: string
  badgeClass: string
  pulse: boolean
}

const BUCKETS: Bucket[] = [
  { label: 'Ending < 30 min', maxSeconds: 1800,  colorClass: 'border-red-700 bg-red-950/40',    badgeClass: 'bg-red-900/80 text-red-200 border-red-700',    pulse: true  },
  { label: 'Ending 30 min – 1 h', maxSeconds: 3600,  colorClass: 'border-orange-700 bg-orange-950/30', badgeClass: 'bg-orange-900/60 text-orange-200 border-orange-700', pulse: false },
  { label: 'Ending 1 h – 2 h', maxSeconds: 7200,  colorClass: 'border-yellow-700 bg-yellow-950/20', badgeClass: 'bg-yellow-900/40 text-yellow-200 border-yellow-700', pulse: false },
  { label: 'Ending 2 h – 6 h', maxSeconds: 21600, colorClass: 'border-gray-700 bg-gray-800/30',    badgeClass: 'bg-gray-800 text-gray-300 border-gray-600',       pulse: false },
]

function formatCountdown(seconds: number): string {
  if (seconds <= 0) return 'Ended'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function ScoreDot({ score }: { score: number }) {
  const color =
    score >= 60 ? 'bg-green-500' :
    score >= 40 ? 'bg-yellow-500' :
    'bg-red-500'
  return (
    <span className={clsx('inline-block w-2 h-2 rounded-full shrink-0', color)} title={`Score: ${score.toFixed(1)}`} />
  )
}

function ItemCard({ item, onItemClick, bucket }: { item: AuctionOpportunity; onItemClick: (id: string) => void; bucket: Bucket }) {
  return (
    <button
      onClick={() => onItemClick(item.ebay_item_id)}
      className={clsx(
        'w-full flex items-center gap-3 p-2.5 rounded-lg border transition-colors hover:bg-white/5 text-left',
        bucket.colorClass,
      )}
    >
      {item.image_url && (
        <img src={item.image_url} alt="" className="w-9 h-9 rounded object-cover bg-gray-800 shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-gray-200 line-clamp-1">{item.title}</p>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          <span className="text-xs text-gray-500">${item.current_bid_usd.toFixed(0)}</span>
          {item.profit_margin_pct != null && (
            <span className={clsx(
              'text-xs font-mono',
              item.profit_margin_pct >= 30 ? 'text-green-400' :
              item.profit_margin_pct >= 15 ? 'text-yellow-400' :
              'text-red-400'
            )}>
              {item.profit_margin_pct >= 0 ? '+' : ''}{item.profit_margin_pct.toFixed(0)}%
            </span>
          )}
        </div>
      </div>
      <div className="shrink-0 flex flex-col items-end gap-1">
        <span className={clsx(
          'text-[10px] font-mono px-1.5 py-0.5 rounded-full border',
          bucket.badgeClass,
          bucket.pulse && 'animate-pulse',
        )}>
          {formatCountdown(item.seconds_remaining)}
        </span>
        <div className="flex items-center gap-1">
          <ScoreDot score={item.opportunity_score} />
          <span className="text-[10px] text-gray-500 font-mono">{item.opportunity_score.toFixed(0)}</span>
        </div>
      </div>
      <ExternalLink size={11} className="text-gray-600 shrink-0" />
    </button>
  )
}

export default function UpcomingEndingsSection({ items, onItemClick }: Props) {
  // Filter to items ending within 6h, sorted by ends_at ASC (most urgent first)
  const urgent = items
    .filter(i => i.seconds_remaining > 0 && i.seconds_remaining <= 21600)
    .sort((a, b) => a.seconds_remaining - b.seconds_remaining)

  if (urgent.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-center text-sm text-gray-500">
        No auctions ending in the next 6 hours. Run a refresh to get the latest data.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {BUCKETS.map(bucket => {
        const prevMax = bucket === BUCKETS[0] ? 0 : BUCKETS[BUCKETS.indexOf(bucket) - 1].maxSeconds
        const bucketItems = urgent
          .filter(i => i.seconds_remaining > prevMax && i.seconds_remaining <= bucket.maxSeconds)
          .sort((a, b) => b.opportunity_score - a.opportunity_score)  // highest score first within bucket

        if (bucketItems.length === 0) return null

        return (
          <div key={bucket.label}>
            <div className="flex items-center gap-2 mb-2">
              <Flame size={13} className={
                bucket.maxSeconds <= 1800 ? 'text-red-400' :
                bucket.maxSeconds <= 3600 ? 'text-orange-400' :
                bucket.maxSeconds <= 7200 ? 'text-yellow-400' :
                'text-gray-400'
              } />
              <span className="text-xs font-semibold text-gray-400">{bucket.label}</span>
              <span className="text-xs text-gray-600">({bucketItems.length} item{bucketItems.length !== 1 ? 's' : ''})</span>
            </div>
            <div className="space-y-1.5">
              {bucketItems.map(item => (
                <ItemCard key={item.ebay_item_id} item={item} onItemClick={onItemClick} bucket={bucket} />
              ))}
            </div>
          </div>
        )
      })}
      <p className="text-xs text-gray-600 text-center pt-1">
        Showing {urgent.length} auction{urgent.length !== 1 ? 's' : ''} ending in the next 6 hours · sorted by opportunity score within each bucket
      </p>
    </div>
  )
}
