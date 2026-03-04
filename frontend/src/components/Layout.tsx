import { ReactNode, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { BarChart3, LayoutDashboard, Settings } from 'lucide-react'
import SettingsPanel from './SettingsPanel'
import { useOpportunities } from '../api/hooks'
import { clsx } from 'clsx'

interface Props {
  children: ReactNode
}

export default function Layout({ children }: Props) {
  const location = useLocation()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const { data: oppsData } = useOpportunities({ limit: 1 })
  const usage = oppsData?.api_usage

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top nav */}
      <header className="bg-gray-900 border-b border-gray-800 sticky top-0 z-40">
        <div className="max-w-screen-2xl mx-auto px-4 h-14 flex items-center gap-6">
          <span className="font-bold text-blue-400 text-lg tracking-tight">
            eBay Arbitrage
          </span>

          <nav className="flex items-center gap-1 flex-1">
            <NavLink to="/categories" active={location.pathname === '/categories'}>
              <BarChart3 size={16} />
              Categories
            </NavLink>
            <NavLink to="/dashboard" active={location.pathname === '/dashboard'}>
              <LayoutDashboard size={16} />
              Dashboard
            </NavLink>
          </nav>

          {/* API quota warning */}
          {usage?.warn && (
            <div className="text-xs bg-yellow-900/60 text-yellow-300 px-3 py-1 rounded-full border border-yellow-700">
              ⚠ {usage.remaining} eBay API calls left today
            </div>
          )}

          <button
            onClick={() => setSettingsOpen(true)}
            className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-100 transition-colors"
            title="Settings"
          >
            <Settings size={18} />
          </button>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 max-w-screen-2xl mx-auto w-full px-4 py-6">
        {children}
      </main>

      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  )
}

function NavLink({ to, active, children }: { to: string; active: boolean; children: ReactNode }) {
  return (
    <Link
      to={to}
      className={clsx(
        'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
        active
          ? 'bg-blue-600 text-white'
          : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800',
      )}
    >
      {children}
    </Link>
  )
}
