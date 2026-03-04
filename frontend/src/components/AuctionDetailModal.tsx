import { useState } from 'react'
import { X, ExternalLink, Scale, TrendingUp, Clock, Users, AlertTriangle } from 'lucide-react'
import { clsx } from 'clsx'
import { useAuctionDetail, useOverrideWeight } from '../api/hooks'

interface Props {
  ebayItemId: string
  onClose: () => void
}

const PLATFORM_COLORS: Record<string, string> = {
  mymarket: 'bg-blue-900/40 border-blue-800',
  veli: 'bg-purple-900/40 border-purple-800',
  zoomer: 'bg-green-900/40 border-green-800',
}

function ScoreBar({ label, score, icon: Icon, color }: { label: string; score: number; icon: React.ElementType; color: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className={clsx('p-1.5 rounded', color)}>
        <Icon size={14} />
      </div>
      <div className="flex-1">
        <div className="flex justify-between mb-1">
          <span className="text-xs text-gray-400">{label}</span>
          <span className="text-xs font-mono text-gray-300">{(score * 100).toFixed(0)}%</span>
        </div>
        <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div
            className={clsx('h-full rounded-full transition-all', color.replace('bg-', 'bg-').replace('/20', ''))}
            style={{ width: `${score * 100}%` }}
          />
        </div>
      </div>
    </div>
  )
}

export default function AuctionDetailModal({ ebayItemId, onClose }: Props) {
  const { data, isLoading } = useAuctionDetail(ebayItemId)
  const overrideWeight = useOverrideWeight()
  const [weightInput, setWeightInput] = useState('')
  const [weightSaved, setWeightSaved] = useState(false)

  const handleWeightSave = async () => {
    const w = parseFloat(weightInput)
    if (!isNaN(w) && w > 0) {
      await overrideWeight.mutateAsync({ ebayItemId, weightKg: w })
      setWeightSaved(true)
      setTimeout(() => setWeightSaved(false), 2000)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div className="relative bg-gray-900 border border-gray-800 rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 bg-gray-900 border-b border-gray-800 px-6 py-4 flex items-center gap-4 z-10">
          {data?.item.image_url && (
            <img src={data.item.image_url} alt="" className="w-14 h-14 rounded-lg object-cover bg-gray-800 shrink-0" />
          )}
          <div className="flex-1 min-w-0">
            <h2 className="font-semibold text-gray-100 line-clamp-2 text-sm leading-snug">
              {data?.item.title ?? '...'}
            </h2>
            {data?.item.item_url && (
              <a href={data.item.item_url} target="_blank" rel="noopener noreferrer"
                className="text-xs text-blue-400 hover:underline inline-flex items-center gap-1 mt-0.5">
                View on eBay <ExternalLink size={10} />
              </a>
            )}
          </div>
          <button onClick={onClose} className="p-1 hover:bg-gray-800 rounded shrink-0">
            <X size={20} />
          </button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center h-48">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
          </div>
        ) : data ? (
          <div className="p-6 space-y-6">
            {/* Data quality warning */}
            {data.opportunity?.data_quality_warning && (
              <div className="flex items-start gap-2 px-3 py-2.5 bg-yellow-950/50 border border-yellow-800 rounded-xl text-xs text-yellow-300">
                <AlertTriangle size={13} className="shrink-0 mt-0.5" />
                <span>{data.opportunity.data_quality_warning}</span>
              </div>
            )}

            {/* Cost Breakdown */}
            {data.opportunity && (
              <section>
                <h3 className="text-sm font-semibold text-gray-300 mb-3">Cost Breakdown</h3>
                <div className="bg-gray-800/50 rounded-xl p-4 space-y-2 text-sm">
                  <Row label="Current Bid" value={`$${data.item.current_bid_usd.toFixed(2)}`} />
                  {data.price_estimate && (
                    <Row label="Estimated Final" value={`$${data.price_estimate.estimated_final_usd.toFixed(2)}`} sub={`via ${data.price_estimate.estimation_method}`} />
                  )}
                  <Row label="Shipping Cost" value={`$${data.opportunity.shipping_cost_usd.toFixed(2)}`} sub={`${data.item.weight_kg?.toFixed(2) ?? '?'}kg`} />
                  {data.opportunity.vat_usd > 0 && (
                    <Row label="VAT" value={`$${data.opportunity.vat_usd.toFixed(2)}`} />
                  )}
                  <div className="border-t border-gray-700 pt-2 mt-2">
                    <Row
                      label="Total Landed Cost"
                      value={`$${data.opportunity.total_landed_cost_usd.toFixed(2)}`}
                      sub={`${data.opportunity.total_landed_cost_gel.toFixed(0)} ₾ @ ${data.opportunity.gel_rate_used.toFixed(4)}`}
                      bold
                    />
                  </div>
                  {data.opportunity.profit_margin_pct != null && (
                    <div className="border-t border-gray-700 pt-2 mt-2">
                      <Row
                        label="Profit Margin"
                        value={`${data.opportunity.profit_margin_pct >= 0 ? '+' : ''}${data.opportunity.profit_margin_pct.toFixed(1)}%`}
                        sub={data.opportunity.profit_gel != null ? `${data.opportunity.profit_gel.toFixed(0)} ₾` : undefined}
                        bold
                        valueColor={data.opportunity.profit_margin_pct >= 30 ? 'text-green-400' : data.opportunity.profit_margin_pct >= 15 ? 'text-yellow-400' : 'text-red-400'}
                      />
                    </div>
                  )}
                </div>
              </section>
            )}

            {/* Price Estimate */}
            {data.price_estimate && (
              <section>
                <h3 className="text-sm font-semibold text-gray-300 mb-3">Price Estimation</h3>
                <div className="bg-gray-800/50 rounded-xl p-4 text-sm space-y-2">
                  <Row label="Method" value={data.price_estimate.estimation_method} />
                  <Row label="Confidence" value={`${(data.price_estimate.confidence_score * 100).toFixed(0)}%`} />
                  {data.price_estimate.bin_sample_count > 0 && (
                    <>
                      <Row label="BIN samples" value={String(data.price_estimate.bin_sample_count)} />
                      <Row label="BIN range" value={`$${data.price_estimate.bin_price_min_usd?.toFixed(2)} – $${data.price_estimate.bin_price_max_usd?.toFixed(2)}`} />
                      <Row label="BIN median" value={`$${data.price_estimate.bin_price_median_usd?.toFixed(2)}`} />
                    </>
                  )}
                </div>
              </section>
            )}

            {/* Score breakdown */}
            {data.opportunity && (
              <section>
                <h3 className="text-sm font-semibold text-gray-300 mb-3">
                  Opportunity Score: <span className="text-blue-400 font-mono">{data.opportunity.opportunity_score.toFixed(1)}/100</span>
                </h3>
                <div className="bg-gray-800/50 rounded-xl p-4 space-y-3">
                  <ScoreBar label="Margin (45%)" score={data.opportunity.margin_score} icon={TrendingUp} color="bg-green-700/20 text-green-400" />
                  <ScoreBar label="Urgency (25%)" score={data.opportunity.urgency_score} icon={Clock} color="bg-orange-700/20 text-orange-400" />
                  <ScoreBar label="Confidence (20%)" score={data.opportunity.confidence_score} icon={Scale} color="bg-blue-700/20 text-blue-400" />
                  <ScoreBar label="Low Competition (10%)" score={data.opportunity.competition_score} icon={Users} color="bg-purple-700/20 text-purple-400" />
                </div>
              </section>
            )}

            {/* Georgian Listings */}
            <section>
              <h3 className="text-sm font-semibold text-gray-300 mb-3">
                Georgian Listings ({data.georgian_listings.length})
              </h3>
              {data.georgian_listings.length === 0 ? (
                <p className="text-sm text-gray-500 bg-gray-800/50 rounded-xl p-4">No Georgian listings found for this item.</p>
              ) : (
                <div className="space-y-2">
                  {data.georgian_listings.map((l, i) => (
                    <a
                      key={i}
                      href={l.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={clsx(
                        'flex items-center gap-3 p-3 rounded-xl border transition-colors hover:border-gray-600',
                        PLATFORM_COLORS[l.platform] ?? 'bg-gray-800/40 border-gray-700',
                      )}
                    >
                      {l.image_url && (
                        <img src={l.image_url} alt="" className="w-10 h-10 rounded object-cover bg-gray-800 shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-gray-200 line-clamp-1">{l.title}</p>
                        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                          <span className="text-xs capitalize text-gray-500">{l.platform}</span>
                          {l.similarity_score < 0.3 && (
                            <span className="text-xs text-yellow-500 flex items-center gap-0.5">
                              <AlertTriangle size={10} />Low match
                            </span>
                          )}
                          {l.price_mismatch && (
                            <span className="text-xs text-orange-400 flex items-center gap-0.5">
                              <AlertTriangle size={10} />Price mismatch (&gt;5× eBay)
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="font-mono text-sm font-semibold text-gray-100">{l.price_gel.toFixed(0)} ₾</p>
                        <p className="text-xs text-gray-500">${l.price_usd.toFixed(2)}</p>
                      </div>
                      <ExternalLink size={12} className="text-gray-600" />
                    </a>
                  ))}
                </div>
              )}
            </section>

            {/* Weight Override */}
            <section>
              <h3 className="text-sm font-semibold text-gray-300 mb-3">Weight Override</h3>
              <div className="bg-gray-800/50 rounded-xl p-4">
                <p className="text-xs text-gray-500 mb-3">
                  Current: <span className="font-mono text-gray-300">{data.item.weight_kg?.toFixed(2) ?? '?'} kg</span>
                  {' '}({data.item.weight_source ?? 'unknown'})
                </p>
                <div className="flex gap-2">
                  <input
                    type="number"
                    value={weightInput}
                    onChange={e => setWeightInput(e.target.value)}
                    placeholder="Enter kg"
                    step="0.1"
                    min="0.1"
                    className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono"
                  />
                  <button
                    onClick={handleWeightSave}
                    disabled={overrideWeight.isPending || !weightInput}
                    className="px-4 py-2 bg-blue-700 hover:bg-blue-600 rounded-lg text-sm disabled:opacity-50"
                  >
                    {weightSaved ? '✓ Saved' : overrideWeight.isPending ? '...' : 'Override'}
                  </button>
                </div>
              </div>
            </section>
          </div>
        ) : (
          <div className="p-6 text-gray-500 text-center">Failed to load item details</div>
        )}
      </div>
    </div>
  )
}

function Row({
  label,
  value,
  sub,
  bold,
  valueColor,
}: {
  label: string
  value: string
  sub?: string
  bold?: boolean
  valueColor?: string
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className={clsx('text-gray-500', bold && 'text-gray-300 font-medium')}>{label}</span>
      <div className="text-right">
        <span className={clsx('font-mono', bold ? 'font-semibold' : '', valueColor ?? 'text-gray-200')}>{value}</span>
        {sub && <p className="text-xs text-gray-500">{sub}</p>}
      </div>
    </div>
  )
}
