import { useState, useEffect, useRef } from 'react'
import { RefreshCw, BarChart2, Star, TreePine, Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import axios from 'axios'
import CategoryTreeBrowser from '../components/CategoryTreeBrowser'
import TrackedCategoryCard from '../components/TrackedCategoryCard'
import {
  useTrackedCategories,
  useStartCategoryAnalysis,
  useStartSingleCategoryAnalysis,
  useTreeMeta,
  useSyncCategoryTree,
  fetchJobStatus,
  useModernTrackingSettings,
  useUpdateModernTrackingSettings,
  useModernTrackingRecommendations,
  useStartModernTrackingRefresh,
  fetchModernTrackingRefreshStatus,
  type ModernTrackingSettings,
} from '../api/hooks'

export default function CategoryAnalyzer() {
  const { data: tracked, isLoading: trackedLoading, refetch: refetchTracked } = useTrackedCategories()
  const { data: treeMeta } = useTreeMeta()
  const startBatchAnalysis = useStartCategoryAnalysis()
  const startSingleAnalysis = useStartSingleCategoryAnalysis()
  const syncTree = useSyncCategoryTree()
  const navigate = useNavigate()

  const { data: trackingSettingsData } = useModernTrackingSettings()
  const updateTrackingSettings = useUpdateModernTrackingSettings()
  const startTrackingRefresh = useStartModernTrackingRefresh()
  const { data: trackingRecs, refetch: refetchTrackingRecs } = useModernTrackingRecommendations({ limit: 12 })

  const [jobStatus, setJobStatus] = useState<{ status: string; progress: number; message: string } | null>(null)
  const [trackingJobStatus, setTrackingJobStatus] = useState<{ status: string; progress: number; message: string; metrics?: Record<string, number | string> } | null>(null)
  const [activeTab, setActiveTab] = useState<'browse' | 'tracked'>('tracked')
  const [trackingSettingsForm, setTrackingSettingsForm] = useState<ModernTrackingSettings | null>(null)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const trackingPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (trackingSettingsData) setTrackingSettingsForm(trackingSettingsData)
  }, [trackingSettingsData])

  const startPolling = (id: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const status = await fetchJobStatus(id)
        setJobStatus({ status: status.status, progress: status.progress, message: status.message })
        if (status.status === 'done' || status.status === 'error') {
          clearInterval(pollRef.current!)
          pollRef.current = null
          if (status.status === 'done') refetchTracked()
        }
      } catch {
        clearInterval(pollRef.current!)
        pollRef.current = null
      }
    }, 1500)
  }

  const startTrackingPolling = (id: string) => {
    if (trackingPollRef.current) clearInterval(trackingPollRef.current)
    trackingPollRef.current = setInterval(async () => {
      try {
        const status = await fetchModernTrackingRefreshStatus(id)
        setTrackingJobStatus({
          status: status.status,
          progress: status.progress,
          message: status.message,
          metrics: status.metrics,
        })
        if (status.status === 'done' || status.status === 'error') {
          clearInterval(trackingPollRef.current!)
          trackingPollRef.current = null
          if (status.status === 'done') {
            refetchTracked()
            refetchTrackingRecs()
          }
        }
      } catch {
        clearInterval(trackingPollRef.current!)
        trackingPollRef.current = null
      }
    }, 2000)
  }

  const handleAnalyzeAll = async () => {
    try {
      setJobStatus(null)
      const result = await startBatchAnalysis.mutateAsync()
      setJobStatus({ status: 'running', progress: 0, message: 'Starting...' })
      startPolling(result.job_id)
    } catch (e) {
      const message = axios.isAxiosError(e)
        ? (e.response?.data?.detail || e.response?.data?.error || e.message)
        : 'Failed to start analysis'
      setJobStatus({ status: 'error', progress: 0, message })
    }
  }

  const handleAnalyzeSingle = async (categoryId: string) => {
    try {
      setJobStatus(null)
      const result = await startSingleAnalysis.mutateAsync(categoryId)
      setJobStatus({ status: 'running', progress: 0, message: 'Analyzing...' })
      startPolling(result.job_id)
    } catch (e) {
      const message = axios.isAxiosError(e)
        ? (e.response?.data?.detail || e.response?.data?.error || e.message)
        : 'Failed to start category analysis'
      setJobStatus({ status: 'error', progress: 0, message })
    }
  }

  const handleSyncTree = async () => {
    try {
      setJobStatus(null)
      const result = await syncTree.mutateAsync()
      setJobStatus({ status: 'running', progress: 0, message: 'Fetching category tree...' })
      startPolling(result.job_id)
    } catch (e) {
      const message = axios.isAxiosError(e)
        ? (e.response?.data?.detail || e.response?.data?.error || e.message)
        : 'Failed to start tree sync'
      setJobStatus({ status: 'error', progress: 0, message })
    }
  }

  const handleRunAdvisor = async () => {
    try {
      setTrackingJobStatus(null)
      const result = await startTrackingRefresh.mutateAsync({ apply_changes: true })
      setTrackingJobStatus({ status: 'running', progress: 0, message: 'Running tracking advisor...' })
      startTrackingPolling(result.job_id)
    } catch (e) {
      const message = axios.isAxiosError(e)
        ? (e.response?.data?.detail || e.response?.data?.error || e.message)
        : 'Failed to start tracking advisor'
      setTrackingJobStatus({ status: 'error', progress: 0, message })
    }
  }

  const handleSaveTrackingSettings = async () => {
    if (!trackingSettingsForm) return
    await updateTrackingSettings.mutateAsync({
      tracking_mode: trackingSettingsForm.tracking_mode,
      auto_track_enabled: trackingSettingsForm.auto_track_enabled,
      auto_track_max_categories: trackingSettingsForm.auto_track_max_categories,
      auto_track_refresh_hours: trackingSettingsForm.auto_track_refresh_hours,
      auto_track_min_liquidity: trackingSettingsForm.auto_track_min_liquidity,
      auto_track_min_score: trackingSettingsForm.auto_track_min_score,
      focus_policy: trackingSettingsForm.focus_policy,
      focus_bucket: trackingSettingsForm.focus_bucket,
      realism_max_extreme_margin_pct: trackingSettingsForm.realism_max_extreme_margin_pct,
      realism_min_positive_discount_share: trackingSettingsForm.realism_min_positive_discount_share,
    })
    refetchTrackingRecs()
  }

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current)
    if (trackingPollRef.current) clearInterval(trackingPollRef.current)
  }, [])

  const isRunning = jobStatus?.status === 'running'
  const trackedCount = tracked?.length ?? 0

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-100 flex items-center gap-2">
            <BarChart2 size={22} className="text-blue-400" />
            Category Analyzer
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Browse the tree, track categories, and let the advisor keep tracked categories liquid and realistic.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {treeMeta?.total_categories && (
            <span className="text-xs text-gray-500">
              {treeMeta.total_categories.toLocaleString()} categories loaded
            </span>
          )}
          <button
            onClick={handleSyncTree}
            disabled={isRunning || syncTree.isPending}
            className="flex items-center gap-1.5 px-3 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-xl text-sm text-gray-300 transition-colors disabled:opacity-50"
            title="Re-fetch category tree from eBay"
          >
            <TreePine size={14} />
            Sync Tree
          </button>
          <button
            onClick={handleAnalyzeAll}
            disabled={isRunning || startBatchAnalysis.isPending || trackedCount === 0}
            className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-medium disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={16} className={isRunning ? 'animate-spin' : ''} />
            {isRunning ? 'Analyzing...' : `Analyze Tracked (${trackedCount})`}
          </button>
        </div>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h2 className="text-sm font-semibold text-gray-100 flex items-center gap-2">
            <Sparkles size={15} className="text-cyan-400" />
            Tracking Advisor
          </h2>
          <div className="text-xs text-gray-400">
            Focus bucket: <span className="text-cyan-300">{trackingRecs?.focus_bucket ?? trackingSettingsData?.focus_bucket ?? 'auto'}</span>
          </div>
        </div>
        <p className="text-xs text-gray-400">
          Hybrid mode keeps your manual pins/blocks and auto-selects the rest using liquidity, qualification, comparables, realism, and stability.
        </p>

        {trackingSettingsForm && (
          <div className="grid grid-cols-1 xl:grid-cols-6 gap-2">
            <select
              value={trackingSettingsForm.tracking_mode}
              onChange={e => setTrackingSettingsForm(s => s ? { ...s, tracking_mode: e.target.value as ModernTrackingSettings['tracking_mode'] } : s)}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs"
            >
              <option value="hybrid_auto_manual">Hybrid auto+manual</option>
              <option value="auto_only">Auto only</option>
              <option value="manual_only">Manual only</option>
            </select>
            <input
              type="number"
              value={trackingSettingsForm.auto_track_max_categories}
              onChange={e => setTrackingSettingsForm(s => s ? { ...s, auto_track_max_categories: Number(e.target.value) } : s)}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs"
              placeholder="Max auto categories"
            />
            <input
              type="number"
              step="0.01"
              value={trackingSettingsForm.auto_track_min_liquidity}
              onChange={e => setTrackingSettingsForm(s => s ? { ...s, auto_track_min_liquidity: Number(e.target.value) } : s)}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs"
              placeholder="Min liquidity"
            />
            <input
              type="number"
              step="0.01"
              value={trackingSettingsForm.auto_track_min_score}
              onChange={e => setTrackingSettingsForm(s => s ? { ...s, auto_track_min_score: Number(e.target.value) } : s)}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs"
              placeholder="Min score"
            />
            <select
              value={trackingSettingsForm.focus_policy}
              onChange={e => setTrackingSettingsForm(s => s ? { ...s, focus_policy: e.target.value as ModernTrackingSettings['focus_policy'] } : s)}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs"
            >
              <option value="weekly_winner">Weekly winner</option>
              <option value="per_refresh_winner">Per refresh winner</option>
              <option value="mixed_fixed">Mixed fixed</option>
            </select>
            <div className="flex items-center gap-2">
              <button
                onClick={handleSaveTrackingSettings}
                disabled={updateTrackingSettings.isPending}
                className="flex-1 py-1.5 bg-cyan-700 hover:bg-cyan-600 rounded text-xs font-medium disabled:opacity-50"
              >
                {updateTrackingSettings.isPending ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={handleRunAdvisor}
                disabled={startTrackingRefresh.isPending || trackingJobStatus?.status === 'running'}
                className="flex-1 py-1.5 bg-indigo-700 hover:bg-indigo-600 rounded text-xs font-medium disabled:opacity-50"
              >
                {trackingJobStatus?.status === 'running' ? 'Running...' : 'Run Advisor'}
              </button>
            </div>
          </div>
        )}

        {trackingJobStatus && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-gray-400">
              <span>{trackingJobStatus.message}</span>
              <span>{trackingJobStatus.progress}%</span>
            </div>
            <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div
                className={clsx(
                  'h-full transition-all',
                  trackingJobStatus.status === 'error' ? 'bg-red-600' : trackingJobStatus.status === 'done' ? 'bg-green-600' : 'bg-cyan-600',
                )}
                style={{ width: `${trackingJobStatus.progress}%` }}
              />
            </div>
          </div>
        )}

        <div className="overflow-x-auto border border-gray-800 rounded-lg">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-900/80 border-b border-gray-800 text-gray-400 uppercase">
                <th className="px-2 py-2 text-left">Category</th>
                <th className="px-2 py-2 text-right">Score</th>
                <th className="px-2 py-2 text-right">Liquidity</th>
                <th className="px-2 py-2 text-right">Qual</th>
                <th className="px-2 py-2 text-right">Comparables</th>
                <th className="px-2 py-2 text-right">Realism</th>
                <th className="px-2 py-2 text-right">Stability</th>
                <th className="px-2 py-2 text-center">Decision</th>
              </tr>
            </thead>
            <tbody>
              {(trackingRecs?.items ?? []).slice(0, 10).map(r => (
                <tr key={r.category_id} className="border-b border-gray-800/60">
                  <td className="px-2 py-1.5 text-gray-200">{r.category_name}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{(r.category_track_score * 100).toFixed(0)}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{(r.factor_breakdown.liquidity * 100).toFixed(0)}%</td>
                  <td className="px-2 py-1.5 text-right font-mono">{(r.factor_breakdown.qualification * 100).toFixed(0)}%</td>
                  <td className="px-2 py-1.5 text-right font-mono">{(r.factor_breakdown.comparables * 100).toFixed(0)}%</td>
                  <td className="px-2 py-1.5 text-right font-mono">{(r.factor_breakdown.realism * 100).toFixed(0)}%</td>
                  <td className="px-2 py-1.5 text-right font-mono">{(r.factor_breakdown.stability * 100).toFixed(0)}%</td>
                  <td className="px-2 py-1.5 text-center">
                    <span className={clsx(
                      'px-2 py-0.5 rounded-full border',
                      r.decision === 'track'
                        ? 'bg-green-900/40 text-green-300 border-green-700'
                        : r.decision === 'drop'
                          ? 'bg-red-900/40 text-red-300 border-red-700'
                          : 'bg-gray-800 text-gray-300 border-gray-700',
                    )}>
                      {r.decision}
                    </span>
                  </td>
                </tr>
              ))}
              {(!trackingRecs || trackingRecs.items.length === 0) && (
                <tr>
                  <td className="px-2 py-4 text-center text-gray-500" colSpan={8}>No recommendations yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {jobStatus && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-3 space-y-2">
          <div className="flex items-center justify-between mb-1">
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
          {jobStatus.status === 'done' && <p className="text-xs text-green-400">Complete!</p>}
          {jobStatus.status === 'error' && <p className="text-xs text-red-400">Error: {jobStatus.message}</p>}
        </div>
      )}

      <div className="flex items-center gap-1 border-b border-gray-800">
        <button
          onClick={() => setActiveTab('tracked')}
          className={clsx(
            'flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-lg transition-colors border-b-2',
            activeTab === 'tracked'
              ? 'border-yellow-500 text-yellow-400 bg-yellow-950/20'
              : 'border-transparent text-gray-500 hover:text-gray-300',
          )}
        >
          <Star size={14} />
          Tracked Categories
          <span className="ml-1 text-xs bg-gray-800 text-gray-400 px-1.5 rounded-full">{trackedCount}</span>
        </button>
        <button
          onClick={() => setActiveTab('browse')}
          className={clsx(
            'flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-lg transition-colors border-b-2',
            activeTab === 'browse'
              ? 'border-blue-500 text-blue-400 bg-blue-950/20'
              : 'border-transparent text-gray-500 hover:text-gray-300',
          )}
        >
          <TreePine size={14} />
          Browse All
        </button>
      </div>

      {activeTab === 'tracked' ? (
        <>
          {trackedLoading ? (
            <div className="flex items-center justify-center h-40">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
            </div>
          ) : trackedCount > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {tracked!.map(cat => (
                <TrackedCategoryCard
                  key={cat.ebay_category_id}
                  category={cat}
                  onAnalyze={() => handleAnalyzeSingle(cat.ebay_category_id)}
                  onViewDashboard={() => navigate(`/dashboard?category=${cat.ebay_category_id}`)}
                />
              ))}
            </div>
          ) : (
            <div className="text-center py-16 text-gray-500">
              <Star size={40} className="mx-auto mb-3 opacity-30" />
              <p className="mb-2">No tracked categories yet.</p>
              <button
                onClick={() => setActiveTab('browse')}
                className="text-blue-400 hover:text-blue-300 text-sm"
              >
                Browse the category tree to start tracking
              </button>
            </div>
          )}
        </>
      ) : (
        <CategoryTreeBrowser
          onAnalyze={handleAnalyzeSingle}
          onDiscoverStarted={(id) => {
            setJobStatus({ status: 'running', progress: 0, message: 'Discovering subcategories...' })
            startPolling(id)
          }}
        />
      )}
    </div>
  )
}
