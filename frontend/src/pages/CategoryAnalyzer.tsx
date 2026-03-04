import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw, BarChart2 } from 'lucide-react'
import CategoryCard from '../components/CategoryCard'
import { useCategories, useStartCategoryAnalysis, fetchJobStatus } from '../api/hooks'

export default function CategoryAnalyzer() {
  const { data: categories, isLoading, refetch } = useCategories('avg_profit_margin_pct')
  const startAnalysis = useStartCategoryAnalysis()
  const [jobId, setJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<{ status: string; progress: number; message: string } | null>(null)
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
          if (status.status === 'done') {
            refetch()
          }
        }
      } catch {
        clearInterval(pollRef.current!)
        pollRef.current = null
      }
    }, 1500)
  }

  const handleAnalyze = async () => {
    setJobStatus(null)
    const result = await startAnalysis.mutateAsync()
    setJobId(result.job_id)
    setJobStatus({ status: 'running', progress: 0, message: 'Starting...' })
    startPolling(result.job_id)
  }

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const isRunning = jobStatus?.status === 'running'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-100 flex items-center gap-2">
            <BarChart2 size={22} className="text-blue-400" />
            Category Profitability Analyzer
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Identify which product categories have the highest profit margins before diving in.
          </p>
        </div>
        <button
          onClick={handleAnalyze}
          disabled={isRunning || startAnalysis.isPending}
          className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-medium disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={16} className={isRunning ? 'animate-spin' : ''} />
          {isRunning ? 'Analyzing...' : 'Analyze All'}
        </button>
      </div>

      {/* Progress */}
      {jobStatus && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-400">{jobStatus.message}</span>
            <span className="text-sm font-mono text-gray-300">{jobStatus.progress}%</span>
          </div>
          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${jobStatus.status === 'error' ? 'bg-red-600' : jobStatus.status === 'done' ? 'bg-green-600' : 'bg-blue-600'}`}
              style={{ width: `${jobStatus.progress}%` }}
            />
          </div>
          {jobStatus.status === 'done' && (
            <p className="text-xs text-green-400 mt-2">Analysis complete! Categories updated.</p>
          )}
          {jobStatus.status === 'error' && (
            <p className="text-xs text-red-400 mt-2">Error: {jobStatus.message}</p>
          )}
        </div>
      )}

      {/* Grid */}
      {isLoading ? (
        <div className="flex items-center justify-center h-40">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {(categories ?? []).map(cat => (
            <CategoryCard key={cat.ebay_category_id} category={cat} />
          ))}
        </div>
      )}

      {!isLoading && (!categories || categories.length === 0) && (
        <div className="text-center py-16 text-gray-500">
          <BarChart2 size={40} className="mx-auto mb-3 opacity-30" />
          <p>No category data yet. Click "Analyze All" to get started.</p>
        </div>
      )}
    </div>
  )
}
