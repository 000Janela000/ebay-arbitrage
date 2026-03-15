import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { CheckCircle, Download, RefreshCw, Sparkles, XCircle } from 'lucide-react'
import { clsx } from 'clsx'
import {
  useCategories,
  useModernOpportunities,
  useModernSettings,
  useModernTrackingSettings,
  useStartModernRefresh,
  useUpdateModernSettings,
  fetchModernRefreshStatus,
  downloadModernCsv,
  type ModernSettings,
} from '../api/hooks'

type SortBy = 'final_score' | 'steal_score' | 'winability_score' | 'profit_margin_pct' | 'ends_at'

export default function ModernHunter() {
  const { data: categories } = useCategories()
  const { data: settings } = useModernSettings()
  const { data: trackingSettings } = useModernTrackingSettings()
  const updateSettings = useUpdateModernSettings()
  const startRefresh = useStartModernRefresh()

  const [filters, setFilters] = useState({
    categoryId: '',
    qualifiedOnly: true,
    sortBy: 'final_score' as SortBy,
    order: 'desc' as 'asc' | 'desc',
    minProfitPct: '',
    hasGeorgianData: null as boolean | null,
  })

  const [settingsForm, setSettingsForm] = useState<ModernSettings | null>(null)
  const [jobStatus, setJobStatus] = useState<{
    status: string
    progress: number
    message: string
    metrics: Record<string, number>
    scraper_status: Record<string, boolean>
  } | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (settings) setSettingsForm(settings)
  }, [settings])

  const { data: oppsData, isLoading, refetch } = useModernOpportunities({
    sort_by: filters.sortBy,
    order: filters.order,
    qualified_only: filters.qualifiedOnly,
    ...(filters.categoryId ? { category_id: filters.categoryId } : {}),
    ...(filters.minProfitPct ? { min_profit_pct: Number(filters.minProfitPct) } : {}),
    ...(filters.hasGeorgianData !== null ? { has_georgian_data: filters.hasGeorgianData } : {}),
  })

  const startPolling = (jobId: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const status = await fetchModernRefreshStatus(jobId)
        setJobStatus({
          status: status.status,
          progress: status.progress,
          message: status.message,
          metrics: status.metrics ?? {},
          scraper_status: status.scraper_status ?? {},
        })
        if (status.status === 'done' || status.status === 'error') {
          clearInterval(pollRef.current!)
          pollRef.current = null
          if (status.status === 'done') refetch()
        }
      } catch {
        clearInterval(pollRef.current!)
        pollRef.current = null
      }
    }, 2000)
  }

  const handleRefresh = async () => {
    try {
      setJobStatus(null)
      const result = await startRefresh.mutateAsync({
        strategy_profile: settingsForm?.strategy_profile ?? undefined,
      })
      setJobStatus({ status: 'running', progress: 0, message: 'Starting modern refresh...', metrics: {}, scraper_status: {} })
      startPolling(result.job_id)
    } catch (e) {
      const message = axios.isAxiosError(e)
        ? (e.response?.data?.detail || e.response?.data?.error || e.message)
        : 'Failed to start modern refresh'
      setJobStatus({ status: 'error', progress: 0, message, metrics: {}, scraper_status: {} })
    }
  }

  const handleSaveSettings = async () => {
    if (!settingsForm) return
    await updateSettings.mutateAsync(settingsForm)
  }

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-xl font-bold text-gray-100 flex items-center gap-2">
          <Sparkles size={22} className="text-cyan-400" />
          Modern Hunter
        </h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => downloadModernCsv({
              sort_by: filters.sortBy,
              order: filters.order,
              qualified_only: filters.qualifiedOnly,
              ...(filters.categoryId ? { category_id: filters.categoryId } : {}),
              ...(filters.minProfitPct ? { min_profit_pct: Number(filters.minProfitPct) } : {}),
            })}
            className="flex items-center gap-1.5 px-3 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-xl text-sm text-gray-300 transition-colors"
          >
            <Download size={14} />
            Export Modern CSV
          </button>
          <button
            onClick={handleRefresh}
            disabled={startRefresh.isPending || jobStatus?.status === 'running'}
            className="flex items-center gap-2 px-5 py-2 bg-cyan-700 hover:bg-cyan-600 rounded-xl text-sm font-medium disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={16} className={jobStatus?.status === 'running' ? 'animate-spin' : ''} />
            {jobStatus?.status === 'running' ? 'Refreshing...' : 'Refresh Modern'}
          </button>
        </div>
      </div>

      <div className="bg-cyan-950/30 border border-cyan-800/50 rounded-xl p-3 text-sm text-cyan-100/90 space-y-1">
        <p className="font-medium text-cyan-200">What this does</p>
        <p>
          Modern Hunter is a separate steal-first pipeline: Stage A shortlists winnable auctions ending in the
          configured window, then Stage B validates Georgian demand and margin before ranking.
        </p>
        <p>
          Current auto focus bucket: <span className="font-semibold">{trackingSettings?.focus_bucket ?? 'auto'}</span>
        </p>
        <p>
          By default, only gate-passed rows are shown. If this table is empty, turn off <span className="font-semibold">Qualified only</span> to review near-miss items and gate reasons.
        </p>
        <p className="text-cyan-300/80">Classic mode is preserved and unchanged.</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 bg-gray-900 border border-gray-800 rounded-xl p-3">
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={filters.categoryId}
              onChange={e => setFilters(f => ({ ...f, categoryId: e.target.value }))}
              className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm min-w-40"
            >
              <option value="">All Categories</option>
              {(categories ?? []).map(c => (
                <option key={c.ebay_category_id} value={c.ebay_category_id}>{c.name}</option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={filters.qualifiedOnly}
                onChange={e => setFilters(f => ({ ...f, qualifiedOnly: e.target.checked }))}
              />
              Qualified only
            </label>
            <select
              value={String(filters.hasGeorgianData)}
              onChange={e => setFilters(f => ({
                ...f,
                hasGeorgianData: e.target.value === 'true' ? true : e.target.value === 'false' ? false : null,
              }))}
              className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm"
            >
              <option value="null">All data states</option>
              <option value="true">Has Georgian data</option>
              <option value="false">No Georgian data</option>
            </select>
            <input
              type="number"
              value={filters.minProfitPct}
              onChange={e => setFilters(f => ({ ...f, minProfitPct: e.target.value }))}
              className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm w-28"
              placeholder="Min %"
            />
            <select
              value={filters.sortBy}
              onChange={e => setFilters(f => ({ ...f, sortBy: e.target.value as SortBy }))}
              className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm"
            >
              <option value="final_score">Final Score</option>
              <option value="steal_score">Steal Score</option>
              <option value="winability_score">Winability</option>
              <option value="profit_margin_pct">Margin %</option>
              <option value="ends_at">Ends At</option>
            </select>
            <button
              onClick={() => setFilters(f => ({ ...f, order: f.order === 'desc' ? 'asc' : 'desc' }))}
              className="px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-sm hover:bg-gray-700"
            >
              {filters.order === 'desc' ? 'DESC' : 'ASC'}
            </button>
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-3 space-y-2">
          <h3 className="text-sm font-semibold text-gray-300">Modern Settings</h3>
          {settingsForm && (
            <>
              <select
                value={settingsForm.strategy_profile}
                onChange={e => setSettingsForm(s => s ? { ...s, strategy_profile: e.target.value as ModernSettings['strategy_profile'] } : s)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm"
              >
                <option value="balanced">Balanced</option>
                <option value="aggressive">Aggressive</option>
                <option value="conservative">Conservative</option>
              </select>
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="number"
                  step="0.01"
                  value={settingsForm.target_margin_floor_pct}
                  onChange={e => setSettingsForm(s => s ? { ...s, target_margin_floor_pct: Number(e.target.value) } : s)}
                  className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm"
                  placeholder="Margin floor"
                />
                <input
                  type="number"
                  step="0.01"
                  value={settingsForm.demand_gate_min_score}
                  onChange={e => setSettingsForm(s => s ? { ...s, demand_gate_min_score: Number(e.target.value) } : s)}
                  className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm"
                  placeholder="Demand floor"
                />
              </div>
              <button
                onClick={handleSaveSettings}
                disabled={updateSettings.isPending}
                className="w-full py-2 bg-cyan-700 hover:bg-cyan-600 rounded-lg text-sm font-medium disabled:opacity-50"
              >
                {updateSettings.isPending ? 'Saving...' : 'Save Modern Settings'}
              </button>
            </>
          )}
        </div>
      </div>

      {jobStatus && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-400">{jobStatus.message}</span>
            <span className="text-xs font-mono text-gray-300">{jobStatus.progress}%</span>
          </div>
          <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={clsx(
                'h-full rounded-full transition-all',
                jobStatus.status === 'error' ? 'bg-red-600' : jobStatus.status === 'done' ? 'bg-green-600' : 'bg-cyan-600',
              )}
              style={{ width: `${jobStatus.progress}%` }}
            />
          </div>
          <div className="flex items-center gap-4 text-xs text-gray-500 flex-wrap">
            <span>Fetched: {jobStatus.metrics.fetched_count ?? 0}</span>
            <span>Shortlisted: {jobStatus.metrics.shortlisted_count ?? 0}</span>
            <span>Deep scraped: {jobStatus.metrics.deep_scraped_count ?? 0}</span>
            <span>Qualified: {jobStatus.metrics.qualified_count ?? 0}</span>
          </div>
          {Object.keys(jobStatus.scraper_status).length > 0 && (
            <div className="flex items-center gap-3 text-xs">
              {Object.entries(jobStatus.scraper_status).map(([platform, ok]) => (
                <span key={platform} className={clsx('flex items-center gap-1', ok ? 'text-green-400' : 'text-red-400')}>
                  {ok ? <CheckCircle size={12} /> : <XCircle size={12} />}
                  {platform}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 bg-gray-900/80">
              <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Item</th>
              <th className="px-3 py-3 text-right text-xs text-gray-400 uppercase">Bid</th>
              <th className="px-3 py-3 text-right text-xs text-gray-400 uppercase">Anchor</th>
              <th className="px-3 py-3 text-right text-xs text-gray-400 uppercase">Steal%</th>
              <th className="px-3 py-3 text-right text-xs text-gray-400 uppercase">Winability</th>
              <th className="px-3 py-3 text-right text-xs text-gray-400 uppercase">Margin%</th>
              <th className="px-3 py-3 text-right text-xs text-gray-400 uppercase">Final</th>
              <th className="px-3 py-3 text-center text-xs text-gray-400 uppercase">Gate</th>
              <th className="px-3 py-3 text-left text-xs text-gray-400 uppercase">Gate Reason</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td className="px-3 py-6 text-center text-gray-500" colSpan={9}>Loading...</td></tr>
            ) : (oppsData?.items.length ?? 0) === 0 ? (
              <tr>
                <td className="px-3 py-6 text-center text-gray-500" colSpan={9}>
                  {filters.qualifiedOnly
                    ? 'No qualified opportunities yet. Disable "Qualified only" to inspect near-miss rows.'
                    : 'No modern opportunities yet.'}
                </td>
              </tr>
            ) : (
              (oppsData?.items ?? []).map(item => (
                <tr key={item.ebay_item_id} className="border-b border-gray-800/60 hover:bg-gray-800/30">
                  <td className="px-3 py-2.5 min-w-80">
                    <a href={item.item_url} target="_blank" rel="noreferrer" className="text-gray-100 hover:text-cyan-400">
                      {item.title}
                    </a>
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono">${item.current_bid_usd.toFixed(2)}</td>
                  <td className="px-3 py-2.5 text-right font-mono">{item.anchor_price_usd != null ? `$${item.anchor_price_usd.toFixed(2)}` : '-'}</td>
                  <td className="px-3 py-2.5 text-right font-mono">{item.current_discount_pct != null ? `${(item.current_discount_pct * 100).toFixed(1)}%` : '-'}</td>
                  <td className="px-3 py-2.5 text-right font-mono">{(item.winability_score * 100).toFixed(0)}%</td>
                  <td className="px-3 py-2.5 text-right font-mono">{item.profit_margin_pct != null ? `${item.profit_margin_pct.toFixed(1)}%` : '-'}</td>
                  <td className="px-3 py-2.5 text-right font-mono">{item.final_score.toFixed(1)}</td>
                  <td className="px-3 py-2.5 text-center">
                    <span
                      className={clsx(
                        'px-2 py-0.5 text-xs rounded-full border',
                        item.demand_gate_passed
                          ? 'bg-green-900/40 text-green-300 border-green-700'
                          : 'bg-red-900/40 text-red-300 border-red-700',
                      )}
                    >
                      {item.demand_gate_passed ? 'pass' : 'fail'}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-gray-400">{item.gate_reason ?? '-'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
