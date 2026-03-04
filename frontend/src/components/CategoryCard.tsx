import { useNavigate } from 'react-router-dom'
import { TrendingUp, TrendingDown, Minus, ShoppingBag } from 'lucide-react'
import { clsx } from 'clsx'
import type { Category } from '../api/hooks'

interface Props {
  category: Category
}

function MarginBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-xs text-gray-500 px-2 py-0.5 rounded-full bg-gray-800">—</span>
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

export default function CategoryCard({ category }: Props) {
  const navigate = useNavigate()

  const handleClick = () => {
    navigate(`/dashboard?category=${category.ebay_category_id}`)
  }

  return (
    <button
      onClick={handleClick}
      className="bg-gray-900 border border-gray-800 rounded-xl p-5 text-left hover:border-blue-700 hover:bg-gray-800/60 transition-all group w-full"
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-semibold text-gray-100 group-hover:text-blue-400 transition-colors">
            {category.name}
          </h3>
          {category.total_active_auctions > 0 && (
            <p className="text-xs text-gray-500 mt-0.5 flex items-center gap-1">
              <ShoppingBag size={11} />
              {category.total_active_auctions} active auctions
            </p>
          )}
        </div>
        <MarginBadge pct={category.avg_profit_margin_pct} />
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="text-gray-500 mb-0.5">eBay avg price</p>
          <p className="font-mono text-gray-200">
            {category.avg_ebay_sold_usd != null ? `$${category.avg_ebay_sold_usd.toFixed(2)}` : '—'}
          </p>
        </div>
        <div>
          <p className="text-gray-500 mb-0.5">Georgian avg</p>
          <p className="font-mono text-gray-200">
            {category.avg_georgian_price_usd != null ? `$${category.avg_georgian_price_usd.toFixed(2)}` : '—'}
          </p>
        </div>
        <div>
          <p className="text-gray-500 mb-0.5">Default weight</p>
          <p className="font-mono text-gray-200">
            {category.avg_weight_kg != null ? `${category.avg_weight_kg}kg` : '—'}
          </p>
        </div>
        <div>
          <p className="text-gray-500 mb-0.5">Last analyzed</p>
          <p className="text-gray-400">
            {category.last_analyzed_at
              ? new Date(category.last_analyzed_at).toLocaleDateString()
              : 'Never'}
          </p>
        </div>
      </div>
    </button>
  )
}
