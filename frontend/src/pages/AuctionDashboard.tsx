import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { RefreshCw, LayoutDashboard, Download, WifiOff, CheckCircle, XCircle, Flame } from 'lucide-react'
import OpportunityTable from '../components/OpportunityTable'
import FilterBar, { type Filters } from '../components/FilterBar'
import UpcomingEndingsSection from '../components/UpcomingEndingsSection'
import AuctionDetailModal from '../components/AuctionDetailModal'
import { useCategories, useStartRefresh, fetchRefreshStatus, useOpportunities, useCurrencyRate, downloadCsv } from '../api/hooks'
import { clsx } from 'clsx'

export default function AuctionDashboard() {
  const [searchParams] = useSearchParams()
  const initialCategory = searchParams.get('category') ?? ''

  const [filters, setFilters] = useState<Filters>({
    categoryId: initialCategory,
    minProfitPct: '',
    minProfitUsd: '',
    maxBidUsd: '',
    minBudgetUsd: '',
    maxBudgetUsd: '',
    sortBy: 'opportunity_score',
    order: 'desc',
    hasGeorgianData: null,
  })
  const [activeTab, setActiveTab] = useState<'all' | 'ending-soon'>('all')
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<{
    status: string
    progress: number
    message: string
    scraper_status: Record<string, boolean>
  } | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const { data: categories } = useCategories()
  const { data: rateData } = useCurrencyRate()
  const { data: oppsData, isLoading, refetch } = useOpportunities({
    sort_by: filters.sortBy,
    order: filters.order,
    ...(filters.categoryId ? { category_id: filters.categoryId } : {}),
    ...(filters.minProfitPct ? { min_profit_pct: Number(filters.minProfitPct) } : {}),
    ...(filters.minProfitUsd ? { min_profit_usd: Number(filters.minProfitUsd) } : {}),
    ...(filters.maxBidUsd ? { max_bid_usd: Number(filters.maxBidUsd) } : {}),
    ...(filters.minBudgetUsd ? { min_budget_usd: Number(filters.minBudgetUsd) } : {}),
    ...(filters.maxBudgetUsd ? { max_budget_usd: Number(filters.maxBudgetUsd) } : {}),
    ...(filters.hasGeorgianData !== null ? { has_georgian_data: filters.hasGeorgianData } : {}),
  })

  const startRefresh = useStartRefresh()
  const usage = oppsData?.api_usage

  const startPolling = (id: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const s = await fetchRefreshStatus(id)
        setJobStatus({
          status: s.status,
          progress: s.progress,
          message: s.message,
          scraper_status: s.scraper_status ?? {},
        })
        if (s.status === 'done' || s.status === 'error') {
          clearInterval(pollRef.current!)
          pollRef.current = null
          if (s.status === 'done') refetch()
        }
      } catch {
        clearInterval(pollRef.current!)
        pollRef.current = null
      }
    }, 2000)
  }

  const handleRefresh = async () => {
    setJobStatus(null)
    const result = await startRefresh.mutateAsync(filters.categoryId || undefined)
    setJobId(result.job_id)
    setJobStatus({ status: 'running', progress: 0, message: 'Starting refresh...', scraper_status: {} })
    startPolling(result.job_id)
  }

  const handleExportCsv = () => {
    downloadCsv({
      sort_by: filters.sortBy,
      order: filters.order,
      ...(filters.categoryId ? { category_id: filters.categoryId } : {}),
      ...(filters.minProfitPct ? { min_profit_pct: Number(filters.minProfitPct) } : {}),
    })
  }

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const isRunning = jobStatus?.status === 'running'
  const items = oppsData?.items ?? []

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold text-gray-100 flex items-center gap-2">
          <LayoutDashboard size={22} className="text-blue-400" />
          Auction Dashboard
        </h1>
        <div className="flex items-center gap-2 flex-wrap">
          {usage?.warn && (
            <span className="text-xs bg-yellow-900/60 text-yellow-300 px-3 py-1 rounded-full border border-yellow-700">
              ⚠ {usage.remaining} API calls left
            </span>
          )}
          <button
            onClick={handleExportCsv}
            className="flex items-center gap-1.5 px-3 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-xl text-sm text-gray-300 transition-colors"
            title="Export to CSV"
          >
            <Download size={14} />
            Export CSV
          </button>
          <button
            onClick={handleRefresh}
            disabled={isRunning || startRefresh.isPending}
            className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-medium disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={16} className={isRunning ? 'animate-spin' : ''} />
            {isRunning ? 'Refreshing...' : filters.categoryId ? 'Refresh Category' : 'Refresh All'}
          </button>
        </div>
      </div>

      {/* Currency staleness warning */}
      {rateData?.is_fallback && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-orange-950/60 border border-orange-800 rounded-xl text-sm text-orange-300">
          <WifiOff size={15} />
          <span>
            Exchange rate is stale{rateData.age_minutes ? ` (${rateData.age_minutes} min old)` : ''} — NBG API unreachable.
            Profit calculations may be slightly off.
          </span>
        </div>
      )}

      {/* Progress bar */}
      {jobStatus && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-3 space-y-2">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs text-gray-400 truncate">{jobStatus.message}</span>
            <span className="text-xs font-mono text-gray-300 shrink-0 ml-2">{jobStatus.progress}%</span>
          </div>
          <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={clsx(
                'h-full rounded-full transition-all duration-500',
                jobStatus.status === 'error' ? 'bg-red-600'
                  : jobStatus.status === 'done' ? 'bg-green-600'
                  : 'bg-blue-600',
              )}
              style={{ width: `${jobStatus.progress}%` }}
            />
          </div>
          {/* Scraper status indicators */}
          {Object.keys(jobStatus.scraper_status).length > 0 && (
            <div className="flex items-center gap-3 pt-1">
              <span className="text-xs text-gray-500">Scrapers:</span>
              {Object.entries(jobStatus.scraper_status).map(([platform, ok]) => (
                <span key={platform} className={clsx('flex items-center gap-1 text-xs', ok ? 'text-green-400' : 'text-red-400')}>
                  {ok ? <CheckCircle size={12} /> : <XCircle size={12} />}
                  {platform}
                </span>
              ))}
            </div>
          )}
          {jobStatus.status === 'done' && <p className="text-xs text-green-400">Refresh complete!</p>}
          {jobStatus.status === 'error' && <p className="text-xs text-red-400">Error: {jobStatus.message}</p>}
        </div>
      )}

      {/* Tab bar */}
      <div className="flex items-center gap-1 border-b border-gray-800 pb-0">
        <button
          onClick={() => setActiveTab('all')}
          className={clsx(
            'flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-lg transition-colors border-b-2',
            activeTab === 'all'
              ? 'border-blue-500 text-blue-400 bg-blue-950/20'
              : 'border-transparent text-gray-500 hover:text-gray-300',
          )}
        >
          <LayoutDashboard size={14} />
          All Opportunities
          <span className="ml-1 text-xs bg-gray-800 text-gray-400 px-1.5 rounded-full">{oppsData?.total ?? 0}</span>
        </button>
        <button
          onClick={() => setActiveTab('ending-soon')}
          className={clsx(
            'flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-lg transition-colors border-b-2',
            activeTab === 'ending-soon'
              ? 'border-red-500 text-red-400 bg-red-950/20'
              : 'border-transparent text-gray-500 hover:text-gray-300',
          )}
        >
          <Flame size={14} />
          Ending Soon
          {(() => {
            const urgentCount = items.filter(i => i.seconds_remaining > 0 && i.seconds_remaining <= 21600).length
            return urgentCount > 0 ? (
              <span className="ml-1 text-xs bg-red-900/60 text-red-300 border border-red-700 px-1.5 rounded-full">{urgentCount}</span>
            ) : null
          })()}
        </button>
      </div>

      {activeTab === 'all' ? (
        <>
          {/* Filter bar */}
          <FilterBar
            filters={filters}
            onFilterChange={patch => setFilters(f => ({ ...f, ...patch }))}
            categories={categories ?? []}
            totalCount={oppsData?.total ?? 0}
          />

          {/* Table */}
          <OpportunityTable items={items} isLoading={isLoading} />

          {/* Legend */}
          <div className="flex items-center gap-4 text-xs text-gray-500 pt-1 flex-wrap">
            <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-green-600" />Profit ≥ 30%</div>
            <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-yellow-600" />15–30%</div>
            <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-red-700" />&lt; 15%</div>
            <div className="flex items-center gap-1.5 ml-2">
              <span className="bg-orange-900/60 text-orange-300 border border-orange-700 px-1.5 rounded-full text-[10px]">2h 30m</span>
              Ends &lt; 6h
            </div>
            <div className="flex items-center gap-1.5">
              <span className="bg-red-900/80 text-red-300 border border-red-700 px-1.5 rounded-full text-[10px] animate-pulse">45m</span>
              Ends &lt; 2h
            </div>
          </div>
        </>
      ) : (
        /* G4: Upcoming Endings view */
        <>
          <UpcomingEndingsSection
            items={items}
            onItemClick={id => setSelectedItemId(id)}
          />
          {selectedItemId && (
            <AuctionDetailModal
              ebayItemId={selectedItemId}
              onClose={() => setSelectedItemId(null)}
            />
          )}
        </>
      )}
    </div>
  )
}
