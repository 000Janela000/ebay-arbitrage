import { useState, useEffect, useRef } from 'react'
import { RefreshCw, BarChart2, Star, TreePine } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import CategoryTreeBrowser from '../components/CategoryTreeBrowser'
import TrackedCategoryCard from '../components/TrackedCategoryCard'
import {
  useTrackedCategories,
  useStartCategoryAnalysis,
  useStartSingleCategoryAnalysis,
  useTreeMeta,
  useSyncCategoryTree,
  fetchJobStatus,
} from '../api/hooks'

export default function CategoryAnalyzer() {
  const { data: tracked, isLoading: trackedLoading, refetch: refetchTracked } = useTrackedCategories()
  const { data: treeMeta } = useTreeMeta()
  const startBatchAnalysis = useStartCategoryAnalysis()
  const startSingleAnalysis = useStartSingleCategoryAnalysis()
  const syncTree = useSyncCategoryTree()
  const navigate = useNavigate()

  const [jobId, setJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<{ status: string; progress: number; message: string } | null>(null)
  const [activeTab, setActiveTab] = useState<'browse' | 'tracked'>('tracked')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

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

  const handleAnalyzeAll = async () => {
    setJobStatus(null)
    const result = await startBatchAnalysis.mutateAsync()
    setJobId(result.job_id)
    setJobStatus({ status: 'running', progress: 0, message: 'Starting...' })
    startPolling(result.job_id)
  }

  const handleAnalyzeSingle = async (categoryId: string) => {
    setJobStatus(null)
    const result = await startSingleAnalysis.mutateAsync(categoryId)
    setJobId(result.job_id)
    setJobStatus({ status: 'running', progress: 0, message: 'Analyzing...' })
    startPolling(result.job_id)
  }

  const handleSyncTree = async () => {
    setJobStatus(null)
    const result = await syncTree.mutateAsync()
    setJobId(result.job_id)
    setJobStatus({ status: 'running', progress: 0, message: 'Fetching category tree...' })
    startPolling(result.job_id)
  }

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const isRunning = jobStatus?.status === 'running'
  const trackedCount = tracked?.length ?? 0

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-100 flex items-center gap-2">
            <BarChart2 size={22} className="text-blue-400" />
            Category Analyzer
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Browse eBay's category tree, track categories you care about, and analyze their profitability.
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

      {/* Progress */}
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

      {/* Tab bar */}
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

      {/* Content */}
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
            setJobId(id)
            setJobStatus({ status: 'running', progress: 0, message: 'Discovering subcategories...' })
            startPolling(id)
          }}
        />
      )}
    </div>
  )
}
