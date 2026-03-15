import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import Layout from './components/Layout'
import CategoryAnalyzer from './pages/CategoryAnalyzer'
import AuctionDashboard from './pages/AuctionDashboard'
import ModernHunter from './pages/ModernHunter'
import SetupWizard from './components/SetupWizard'
import { fetchSettings } from './api/hooks'

function App() {
  const { data: settings, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-3 px-4 text-center">
        <p className="text-sm text-red-400">Failed to load settings: {(error as Error)?.message || 'Unknown error'}</p>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium"
        >
          Retry
        </button>
      </div>
    )
  }

  // Show setup wizard if no eBay credentials configured
  if (settings && !settings.ebay_client_id) {
    return (
      <BrowserRouter>
        <SetupWizard />
      </BrowserRouter>
    )
  }

  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/categories" element={<CategoryAnalyzer />} />
          <Route path="/dashboard" element={<AuctionDashboard />} />
          <Route path="/modern" element={<ModernHunter />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}

export default App
