import { useState } from 'react'
import { Bookmark, BookmarkCheck, Trash2, Crosshair } from 'lucide-react'
import { clsx } from 'clsx'
import { Category } from '../api/hooks'

export interface Filters {
  categoryId: string
  minProfitPct: string
  minProfitUsd: string
  maxBidUsd: string
  minBudgetUsd: string
  maxBudgetUsd: string
  sortBy: string
  order: string
  hasGeorgianData: boolean | null  // null = show all
}

interface Preset {
  name: string
  filters: Filters
}

interface Props {
  filters: Filters
  onFilterChange: (f: Partial<Filters>) => void
  categories: Category[]
  totalCount: number
}

const SORT_OPTIONS = [
  { value: 'opportunity_score', label: 'Score' },
  { value: 'ends_at', label: 'Ends Soon' },
  { value: 'profit_margin_pct', label: 'Profit %' },
  { value: 'demand_score', label: 'Demand' },
  { value: 'current_bid_usd', label: 'Current Bid' },
  { value: 'total_landed_cost_usd', label: 'Landed Cost' },
]

const BUILT_IN_PRESETS: Preset[] = [
  {
    name: 'Sniper ($40+ profit, ending soon)',
    filters: {
      categoryId: '',
      minProfitPct: '',
      minProfitUsd: '40',
      maxBidUsd: '',
      minBudgetUsd: '',
      maxBudgetUsd: '100',
      sortBy: 'ends_at',
      order: 'asc',
      hasGeorgianData: true,
    },
  },
]

const PRESETS_KEY = 'ebay_arbitrage_filter_presets'

function loadPresets(): Preset[] {
  try {
    return JSON.parse(localStorage.getItem(PRESETS_KEY) || '[]')
  } catch {
    return []
  }
}

function savePresets(presets: Preset[]) {
  localStorage.setItem(PRESETS_KEY, JSON.stringify(presets))
}

export default function FilterBar({ filters, onFilterChange, categories, totalCount }: Props) {
  const [presets, setPresets] = useState<Preset[]>(loadPresets)
  const [presetName, setPresetName] = useState('')
  const [showPresets, setShowPresets] = useState(false)

  const handleSavePreset = () => {
    const name = presetName.trim() || `Preset ${presets.length + 1}`
    const updated = [...presets, { name, filters }]
    setPresets(updated)
    savePresets(updated)
    setPresetName('')
    setShowPresets(false)
  }

  const handleDeletePreset = (index: number) => {
    const updated = presets.filter((_, i) => i !== index)
    setPresets(updated)
    savePresets(updated)
  }

  const handleLoadPreset = (preset: Preset) => {
    onFilterChange(preset.filters)
    setShowPresets(false)
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3 p-3 bg-gray-900/60 rounded-xl border border-gray-800">
        {/* Category */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 whitespace-nowrap">Category</label>
          <select
            value={filters.categoryId}
            onChange={e => onFilterChange({ categoryId: e.target.value })}
            className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm min-w-32"
          >
            <option value="">All Categories</option>
            {categories.map(c => (
              <option key={c.ebay_category_id} value={c.ebay_category_id}>
                {c.name}{c.avg_profit_margin_pct != null ? ` (${c.avg_profit_margin_pct.toFixed(0)}%)` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Min profit */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 whitespace-nowrap">Min Profit %</label>
          <input
            type="number"
            value={filters.minProfitPct}
            onChange={e => onFilterChange({ minProfitPct: e.target.value })}
            placeholder="0"
            step="5"
            className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm w-20 font-mono"
          />
        </div>

        {/* Min profit USD */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 whitespace-nowrap">Min Profit $</label>
          <input
            type="number"
            value={filters.minProfitUsd}
            onChange={e => onFilterChange({ minProfitUsd: e.target.value })}
            placeholder="0"
            step="5"
            className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm w-20 font-mono"
          />
        </div>

        {/* Budget (total landed cost) range */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 whitespace-nowrap">Budget $</label>
          <input
            type="number"
            value={filters.minBudgetUsd}
            onChange={e => onFilterChange({ minBudgetUsd: e.target.value })}
            placeholder="Min"
            step="10"
            className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm w-20 font-mono"
          />
          <span className="text-gray-600 text-xs">–</span>
          <input
            type="number"
            value={filters.maxBudgetUsd}
            onChange={e => onFilterChange({ maxBudgetUsd: e.target.value })}
            placeholder="Max"
            step="10"
            className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm w-20 font-mono"
          />
        </div>

        {/* Georgian data toggle */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 whitespace-nowrap">Georgian data</label>
          <div className="flex rounded-lg overflow-hidden border border-gray-700 text-xs">
            {([null, true, false] as const).map((val, i) => (
              <button
                key={i}
                onClick={() => onFilterChange({ hasGeorgianData: val })}
                className={clsx(
                  'px-2 py-1.5 transition-colors',
                  filters.hasGeorgianData === val
                    ? 'bg-blue-700 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700',
                )}
              >
                {val === null ? 'All' : val ? 'Has data' : 'No data'}
              </button>
            ))}
          </div>
        </div>

        {/* Sort */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 whitespace-nowrap">Sort by</label>
          <select
            value={filters.sortBy}
            onChange={e => onFilterChange({ sortBy: e.target.value })}
            className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm"
          >
            {SORT_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button
            onClick={() => onFilterChange({ order: filters.order === 'desc' ? 'asc' : 'desc' })}
            className="px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-sm hover:bg-gray-700"
            title="Toggle sort direction"
          >
            {filters.order === 'desc' ? '↓' : '↑'}
          </button>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-gray-500">{totalCount} items</span>
          {/* Saved presets */}
          <div className="relative">
            <button
              onClick={() => setShowPresets(v => !v)}
              className="flex items-center gap-1 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-xs text-gray-400 hover:text-gray-100 hover:bg-gray-700"
              title="Saved filter presets"
            >
              <Bookmark size={13} />
              Presets{presets.length > 0 ? ` (${presets.length})` : ''}
            </button>
            {showPresets && (
              <div className="absolute right-0 top-8 z-20 w-72 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl p-3 space-y-2">
                {/* Built-in presets */}
                {BUILT_IN_PRESETS.map((preset, i) => (
                  <button
                    key={`builtin-${i}`}
                    onClick={() => handleLoadPreset(preset)}
                    className="w-full text-left text-xs text-purple-300 hover:text-white px-2 py-1.5 rounded hover:bg-purple-900/30 flex items-center gap-1.5"
                  >
                    <Crosshair size={12} className="text-purple-400 shrink-0" />
                    {preset.name}
                  </button>
                ))}
                <div className="border-t border-gray-800" />
                <p className="text-xs text-gray-400 font-medium">Saved Presets</p>
                {presets.length === 0 && (
                  <p className="text-xs text-gray-600">No presets saved yet.</p>
                )}
                {presets.map((preset, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <button
                      onClick={() => handleLoadPreset(preset)}
                      className="flex-1 text-left text-xs text-gray-300 hover:text-white px-2 py-1 rounded hover:bg-gray-800 truncate"
                    >
                      <BookmarkCheck size={11} className="inline mr-1 text-blue-400" />
                      {preset.name}
                    </button>
                    <button
                      onClick={() => handleDeletePreset(i)}
                      className="p-1 text-gray-600 hover:text-red-400"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
                <div className="border-t border-gray-800 pt-2 flex gap-2">
                  <input
                    value={presetName}
                    onChange={e => setPresetName(e.target.value)}
                    placeholder="Preset name..."
                    className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs"
                    onKeyDown={e => e.key === 'Enter' && handleSavePreset()}
                  />
                  <button
                    onClick={handleSavePreset}
                    className="px-2 py-1 bg-blue-700 hover:bg-blue-600 rounded text-xs"
                  >
                    Save
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
