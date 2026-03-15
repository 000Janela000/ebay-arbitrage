import { TrendingUp, TrendingDown, Minus, ShoppingBag, BarChart2, LayoutDashboard, Star, Ban, RotateCcw } from 'lucide-react'
import { clsx } from 'clsx'
import {
  usePinCategory,
  useBlockCategory,
  useClearCategoryOverride,
  type TrackedCategory,
} from '../api/hooks'

interface Props {
  category: TrackedCategory
  onAnalyze: () => void
  onViewDashboard: () => void
}

function MarginBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-xs text-gray-500 px-2 py-0.5 rounded-full bg-gray-800">-</span>
  const cls = pct >= 30 ? 'bg-green-900/60 text-green-400 border-green-800'
    : pct >= 15 ? 'bg-yellow-900/60 text-yellow-400 border-yellow-800'
      : 'bg-red-900/60 text-red-400 border-red-800'
  const Icon = pct >= 30 ? TrendingUp : pct >= 0 ? Minus : TrendingDown
  return (
    <span className={clsx('flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border', cls)}>
      <Icon size={12} />
      {pct >= 0 ? '+' : ''}{pct.toFixed(1)}%
    </span>
  )
}

function SourceBadge({ category }: { category: TrackedCategory }) {
  if (category.manual_pin) {
    return <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-900/40 text-blue-300 border border-blue-700">Manual Pin</span>
  }
  if (category.manual_block) {
    return <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-900/40 text-red-300 border border-red-700">Manual Block</span>
  }
  if (category.track_source === 'auto') {
    return <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-900/40 text-cyan-300 border border-cyan-700">Auto</span>
  }
  return <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 border border-gray-700">None</span>
}

export default function TrackedCategoryCard({ category, onAnalyze, onViewDashboard }: Props) {
  const pin = usePinCategory()
  const block = useBlockCategory()
  const clearOverride = useClearCategoryOverride()

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition-all group">
      <div className="flex items-start justify-between mb-1 gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-gray-100 text-sm truncate">
            {category.name}
          </h3>
          <p className="text-[10px] text-gray-600 truncate mt-0.5" title={category.breadcrumb_path}>
            {category.breadcrumb_path}
          </p>
        </div>
        <MarginBadge pct={category.avg_profit_margin_pct} />
      </div>

      <div className="mb-3 flex items-center gap-2 flex-wrap">
        <SourceBadge category={category} />
        {category.auto_track_score != null && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700">
            Score {(category.auto_track_score * 100).toFixed(0)}
          </span>
        )}
      </div>

      {category.total_active_auctions > 0 && (
        <p className="text-xs text-gray-500 mb-3 flex items-center gap-1">
          <ShoppingBag size={11} />
          {category.total_active_auctions} active auctions
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 text-xs mb-3">
        <div>
          <p className="text-gray-500 mb-0.5">eBay avg</p>
          <p className="font-mono text-gray-200">
            {category.avg_ebay_sold_usd != null ? `$${category.avg_ebay_sold_usd.toFixed(2)}` : '-'}
          </p>
        </div>
        <div>
          <p className="text-gray-500 mb-0.5">Georgian avg</p>
          <p className="font-mono text-gray-200">
            {category.avg_georgian_price_usd != null ? `$${category.avg_georgian_price_usd.toFixed(2)}` : '-'}
          </p>
        </div>
        <div>
          <p className="text-gray-500 mb-0.5">Weight</p>
          <p className="font-mono text-gray-200">
            {category.avg_weight_kg != null ? `${category.avg_weight_kg}kg` : '-'}
          </p>
        </div>
        <div>
          <p className="text-gray-500 mb-0.5">Analyzed</p>
          <p className="text-gray-400">
            {category.last_analyzed_at
              ? new Date(category.last_analyzed_at).toLocaleDateString()
              : 'Never'}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 pt-2 border-t border-gray-800 flex-wrap">
        <button
          onClick={onViewDashboard}
          className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 transition-colors"
        >
          <LayoutDashboard size={12} />
          Dashboard
        </button>
        <button
          onClick={onAnalyze}
          className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-blue-900/40 hover:bg-blue-800/60 rounded-lg text-blue-400 transition-colors"
        >
          <BarChart2 size={12} />
          Analyze
        </button>

        <button
          onClick={() => pin.mutate(category.ebay_category_id)}
          className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-green-900/40 hover:bg-green-800/60 rounded-lg text-green-300 transition-colors"
          title="Manual pin"
        >
          <Star size={12} />
          Pin
        </button>

        <button
          onClick={() => block.mutate(category.ebay_category_id)}
          className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-red-900/40 hover:bg-red-800/60 rounded-lg text-red-300 transition-colors"
          title="Manual block"
        >
          <Ban size={12} />
          Block
        </button>

        {(category.manual_pin || category.manual_block) && (
          <button
            onClick={() => clearOverride.mutate(category.ebay_category_id)}
            className="ml-auto flex items-center gap-1 px-2.5 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 transition-colors"
            title="Clear override"
          >
            <RotateCcw size={12} />
            Clear
          </button>
        )}
      </div>
    </div>
  )
}
