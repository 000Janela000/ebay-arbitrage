import { useState } from 'react'
import type { AuctionOpportunity } from '../api/hooks'
import OpportunityRow from './OpportunityRow'
import AuctionDetailModal from './AuctionDetailModal'

interface Props {
  items: AuctionOpportunity[]
  isLoading: boolean
}

const COLUMNS = [
  { key: 'item', label: 'Item', width: 'w-96' },
  { key: 'current_bid', label: 'Current Bid', width: 'w-28' },
  { key: 'est_final', label: 'Est. Final', width: 'w-28' },
  { key: 'landed', label: 'Landed Cost', width: 'w-28' },
  { key: 'georgian', label: 'Georgian Price', width: 'w-28' },
  { key: 'profit', label: 'Profit %', width: 'w-24' },
  { key: 'ends', label: 'Ends In', width: 'w-24' },
  { key: 'score', label: 'Score', width: 'w-28' },
]

export default function OpportunityTable({ items, isLoading }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-gray-500">
        <p className="text-lg mb-2">No opportunities found</p>
        <p className="text-sm">Try refreshing data or adjusting your filters</p>
      </div>
    )
  }

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-900/80 border-b border-gray-800">
              {COLUMNS.map(col => (
                <th
                  key={col.key}
                  className={`px-3 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider text-left ${col.key !== 'item' ? 'text-right' : ''} ${col.key === 'ends' || col.key === 'score' ? 'text-center' : ''}`}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-gray-950">
            {items.map(item => (
              <OpportunityRow
                key={item.ebay_item_id}
                item={item}
                onClick={() => setSelectedId(item.ebay_item_id)}
              />
            ))}
          </tbody>
        </table>
      </div>

      {selectedId && (
        <AuctionDetailModal
          ebayItemId={selectedId}
          onClose={() => setSelectedId(null)}
        />
      )}
    </>
  )
}
