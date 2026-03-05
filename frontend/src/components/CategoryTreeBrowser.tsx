import { useState } from 'react'
import { Search, ChevronRight, Star, StarOff, FolderOpen, FileText, TrendingUp, TrendingDown, Minus, Sparkles } from 'lucide-react'
import { clsx } from 'clsx'
import {
  useCategoryChildren,
  useCategoryBreadcrumb,
  useCategorySearch,
  useTrackCategory,
  useUntrackCategory,
  useDiscoverPreview,
  useDiscoverCategory,
  type CategoryNode,
} from '../api/hooks'

interface Props {
  onAnalyze?: (categoryId: string) => void
  onDiscoverStarted?: (jobId: string) => void
}

function MarginBadge({ pct }: { pct: number | null }) {
  if (pct === null) return null
  const cls = pct >= 30 ? 'text-green-400' : pct >= 15 ? 'text-yellow-400' : 'text-red-400'
  const Icon = pct >= 30 ? TrendingUp : pct >= 0 ? Minus : TrendingDown
  return (
    <span className={clsx('flex items-center gap-0.5 text-xs font-mono', cls)}>
      <Icon size={11} />
      {pct >= 0 ? '+' : ''}{pct.toFixed(0)}%
    </span>
  )
}

export default function CategoryTreeBrowser({ onAnalyze, onDiscoverStarted }: Props) {
  const [currentParentId, setCurrentParentId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const [discoverTarget, setDiscoverTarget] = useState<string | null>(null)

  const { data: children, isLoading } = useCategoryChildren(currentParentId)
  const { data: breadcrumb } = useCategoryBreadcrumb(currentParentId)
  const { data: searchResults } = useCategorySearch(isSearching ? searchQuery : '')
  const { data: discoverPreview, isLoading: previewLoading } = useDiscoverPreview(discoverTarget)
  const trackMutation = useTrackCategory()
  const untrackMutation = useUntrackCategory()
  const discoverMutation = useDiscoverCategory()

  const handleSearch = (q: string) => {
    setSearchQuery(q)
    setIsSearching(q.length >= 2)
  }

  const handleNavigate = (categoryId: string) => {
    setCurrentParentId(categoryId)
    setIsSearching(false)
    setSearchQuery('')
  }

  const handleTrackToggle = (cat: CategoryNode, e: React.MouseEvent) => {
    e.stopPropagation()
    if (cat.is_tracked) {
      untrackMutation.mutate(cat.ebay_category_id)
    } else {
      trackMutation.mutate(cat.ebay_category_id)
    }
  }

  const displayItems = isSearching ? null : children

  return (
    <div className="space-y-3">
      {/* Search */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
        <input
          value={searchQuery}
          onChange={e => handleSearch(e.target.value)}
          placeholder="Search categories (e.g. iPhone, LEGO, Nike)..."
          className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-9 pr-3 py-2 text-sm placeholder-gray-500 focus:border-blue-600 focus:outline-none"
        />
        {isSearching && (
          <button
            onClick={() => { setSearchQuery(''); setIsSearching(false) }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500 hover:text-gray-300"
          >
            Clear
          </button>
        )}
      </div>

      {/* Breadcrumb */}
      {!isSearching && (
        <div className="flex items-center gap-1 text-xs text-gray-500 flex-wrap min-h-6">
          <button
            onClick={() => setCurrentParentId(null)}
            className={clsx(
              'hover:text-blue-400 transition-colors',
              currentParentId === null && 'text-gray-300 font-medium',
            )}
          >
            Root
          </button>
          {breadcrumb?.map((crumb, i) => (
            <span key={crumb.ebay_category_id} className="flex items-center gap-1">
              <ChevronRight size={10} />
              <button
                onClick={() => setCurrentParentId(crumb.ebay_category_id)}
                className={clsx(
                  'hover:text-blue-400 transition-colors',
                  i === breadcrumb.length - 1 && 'text-gray-300 font-medium',
                )}
              >
                {crumb.name}
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Category list */}
      <div className="border border-gray-800 rounded-xl overflow-hidden max-h-[500px] overflow-y-auto">
        {isSearching ? (
          // Search results
          searchResults && searchResults.length > 0 ? (
            searchResults.map(cat => (
              <div
                key={cat.ebay_category_id}
                className="flex items-center gap-3 px-4 py-2.5 border-b border-gray-800/50 hover:bg-gray-800/40 transition-colors group"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-200 truncate">{cat.name}</p>
                  <p className="text-xs text-gray-500 truncate">{cat.breadcrumb_path}</p>
                </div>
                <MarginBadge pct={cat.avg_profit_margin_pct} />
                <button
                  onClick={() => {
                    if (cat.is_tracked) {
                      untrackMutation.mutate(cat.ebay_category_id)
                    } else {
                      trackMutation.mutate(cat.ebay_category_id)
                    }
                  }}
                  className={clsx(
                    'p-1.5 rounded-lg transition-colors',
                    cat.is_tracked
                      ? 'text-yellow-400 hover:text-yellow-300 bg-yellow-900/20'
                      : 'text-gray-600 hover:text-yellow-400',
                  )}
                  title={cat.is_tracked ? 'Untrack' : 'Track'}
                >
                  {cat.is_tracked ? <Star size={14} /> : <StarOff size={14} />}
                </button>
                {!cat.is_leaf && (
                  <button
                    onClick={() => handleNavigate(cat.ebay_category_id)}
                    className="p-1.5 text-gray-500 hover:text-blue-400 rounded-lg transition-colors"
                    title="Browse subcategories"
                  >
                    <ChevronRight size={14} />
                  </button>
                )}
                {onAnalyze && (
                  <button
                    onClick={() => onAnalyze(cat.ebay_category_id)}
                    className="px-2 py-1 text-xs bg-blue-900/40 text-blue-400 hover:bg-blue-800/60 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                  >
                    Analyze
                  </button>
                )}
              </div>
            ))
          ) : searchQuery.length >= 2 ? (
            <div className="px-4 py-8 text-center text-gray-500 text-sm">
              No categories found for "{searchQuery}"
            </div>
          ) : null
        ) : isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
          </div>
        ) : displayItems && displayItems.length > 0 ? (
          displayItems.map(cat => (
            <div
              key={cat.ebay_category_id}
              className="flex items-center gap-3 px-4 py-2.5 border-b border-gray-800/50 hover:bg-gray-800/40 transition-colors group cursor-pointer"
              onClick={() => !cat.is_leaf && handleNavigate(cat.ebay_category_id)}
            >
              {cat.is_leaf ? (
                <FileText size={14} className="text-gray-600 shrink-0" />
              ) : (
                <FolderOpen size={14} className="text-blue-500/60 shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-200 truncate">{cat.name}</p>
                {!cat.is_leaf && (
                  <p className="text-xs text-gray-600">{cat.child_count} subcategories</p>
                )}
              </div>
              <MarginBadge pct={cat.avg_profit_margin_pct} />
              <button
                onClick={e => handleTrackToggle(cat, e)}
                className={clsx(
                  'p-1.5 rounded-lg transition-colors',
                  cat.is_tracked
                    ? 'text-yellow-400 hover:text-yellow-300 bg-yellow-900/20'
                    : 'text-gray-600 hover:text-yellow-400 opacity-0 group-hover:opacity-100',
                )}
                title={cat.is_tracked ? 'Untrack' : 'Track this category'}
              >
                {cat.is_tracked ? <Star size={14} /> : <StarOff size={14} />}
              </button>
              {onAnalyze && (
                <button
                  onClick={e => { e.stopPropagation(); onAnalyze(cat.ebay_category_id) }}
                  className="px-2 py-1 text-xs bg-blue-900/40 text-blue-400 hover:bg-blue-800/60 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                >
                  Analyze
                </button>
              )}
              {!cat.is_leaf && (
                <button
                  onClick={e => { e.stopPropagation(); setDiscoverTarget(cat.ebay_category_id) }}
                  className="px-2 py-1 text-xs bg-purple-900/40 text-purple-400 hover:bg-purple-800/60 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                  title="Auto-discover all subcategories"
                >
                  <Sparkles size={11} className="inline mr-0.5" />
                  Discover
                </button>
              )}
              {!cat.is_leaf && (
                <ChevronRight size={14} className="text-gray-600 shrink-0" />
              )}
            </div>
          ))
        ) : (
          <div className="px-4 py-8 text-center text-gray-500 text-sm">
            {currentParentId ? 'No subcategories (leaf category)' : 'Category tree not loaded. Sync it from Settings.'}
          </div>
        )}
      </div>

      {/* Discover confirmation modal */}
      {discoverTarget && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setDiscoverTarget(null)}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-md w-full mx-4 space-y-4" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-gray-100 flex items-center gap-2">
              <Sparkles size={18} className="text-purple-400" />
              Auto-Discover Subcategories
            </h3>
            {previewLoading ? (
              <div className="flex items-center justify-center py-6">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-500" />
              </div>
            ) : discoverPreview ? (
              <div className="space-y-3">
                <p className="text-sm text-gray-300">
                  Discover all leaf categories under <span className="font-medium text-gray-100">{discoverPreview.category_name}</span>
                </p>
                <div className="grid grid-cols-2 gap-3 bg-gray-800 rounded-lg p-3">
                  <div>
                    <p className="text-xs text-gray-500">Categories</p>
                    <p className="text-lg font-mono text-gray-100">{discoverPreview.leaf_count}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">API calls</p>
                    <p className="text-lg font-mono text-gray-100">{discoverPreview.api_calls_needed}</p>
                  </div>
                  <div className="col-span-2">
                    <p className="text-xs text-gray-500">Daily budget usage</p>
                    <p className={clsx(
                      'text-lg font-mono',
                      discoverPreview.budget_pct > 20 ? 'text-red-400' : discoverPreview.budget_pct > 10 ? 'text-yellow-400' : 'text-green-400'
                    )}>
                      {discoverPreview.budget_pct}%
                    </p>
                  </div>
                </div>
                <p className="text-xs text-gray-500">
                  This will track and analyze up to {Math.min(discoverPreview.leaf_count, 200)} leaf categories. Results sorted by profit margin.
                </p>
              </div>
            ) : (
              <p className="text-sm text-red-400">Failed to load preview</p>
            )}
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => setDiscoverTarget(null)}
                className="flex-1 px-4 py-2 text-sm bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  if (!discoverTarget) return
                  const result = await discoverMutation.mutateAsync({ categoryId: discoverTarget })
                  setDiscoverTarget(null)
                  onDiscoverStarted?.(result.job_id)
                }}
                disabled={previewLoading || !discoverPreview || discoverMutation.isPending}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm bg-purple-600 hover:bg-purple-500 rounded-lg font-medium disabled:opacity-50 transition-colors"
              >
                <Sparkles size={14} />
                {discoverMutation.isPending ? 'Starting...' : 'Discover'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
