import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ExternalLink, CheckCircle, XCircle } from 'lucide-react'
import { useUpdateSettings, useValidateEbay } from '../api/hooks'

const STEPS = [
  {
    title: 'Create an eBay Developer Account',
    content: (
      <div className="space-y-3 text-sm text-gray-300">
        <p>First, register as an eBay developer to get free API access (5,000 calls/day).</p>
        <ol className="list-decimal list-inside space-y-2">
          <li>Go to <a href="https://developer.ebay.com" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline inline-flex items-center gap-1">developer.ebay.com <ExternalLink size={12} /></a></li>
          <li>Sign in with your regular eBay account or create one</li>
          <li>Accept the API License Agreement</li>
        </ol>
      </div>
    ),
  },
  {
    title: 'Get Your Production API Keys',
    content: (
      <div className="space-y-3 text-sm text-gray-300">
        <p>In the eBay Developer portal:</p>
        <ol className="list-decimal list-inside space-y-2">
          <li>Navigate to <strong>My Account → Application Keys</strong></li>
          <li>Click <strong>Get a Production Key</strong></li>
          <li>Enter an application name (e.g., "Arbitrage Analyzer")</li>
          <li>Copy your <strong>App ID (Client ID)</strong> and <strong>Cert ID (Client Secret)</strong></li>
        </ol>
        <p className="text-yellow-400 text-xs">Note: The Browse API is available with a free account — no special approval needed.</p>
      </div>
    ),
  },
  {
    title: 'Enter Your Credentials',
    isCredentialStep: true,
  },
]

export default function SetupWizard() {
  const [step, setStep] = useState(0)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [environment, setEnvironment] = useState('production')
  const [validateStatus, setValidateStatus] = useState<'idle' | 'ok' | 'fail'>('idle')

  const updateSettings = useUpdateSettings()
  const validateEbay = useValidateEbay()
  const qc = useQueryClient()

  const handleValidate = async () => {
    setValidateStatus('idle')
    try {
      await validateEbay.mutateAsync({ client_id: clientId, client_secret: clientSecret, environment })
      setValidateStatus('ok')
    } catch {
      setValidateStatus('fail')
    }
  }

  const handleFinish = async () => {
    await updateSettings.mutateAsync({
      ebay_client_id: clientId,
      ebay_client_secret: clientSecret,
      ebay_environment: environment,
    })
    qc.invalidateQueries({ queryKey: ['settings'] })
  }

  const current = STEPS[step]

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 p-4">
      <div className="w-full max-w-lg bg-gray-900 rounded-2xl border border-gray-800 shadow-2xl p-8">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-blue-400">eBay Arbitrage Analyzer</h1>
          <p className="text-gray-400 text-sm mt-2">Let's get you set up in a few steps</p>
        </div>

        {/* Step indicators */}
        <div className="flex items-center mb-8">
          {STEPS.map((s, i) => (
            <div key={i} className="flex items-center flex-1">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${i < step ? 'bg-green-600' : i === step ? 'bg-blue-600' : 'bg-gray-800 text-gray-600'}`}>
                {i < step ? '✓' : i + 1}
              </div>
              {i < STEPS.length - 1 && (
                <div className={`h-0.5 flex-1 mx-2 ${i < step ? 'bg-green-600' : 'bg-gray-800'}`} />
              )}
            </div>
          ))}
        </div>

        <h2 className="text-lg font-semibold mb-4">{current.title}</h2>

        {current.isCredentialStep ? (
          <div className="space-y-4">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Environment</label>
              <select
                value={environment}
                onChange={e => setEnvironment(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              >
                <option value="production">Production</option>
                <option value="sandbox">Sandbox (testing)</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Client ID (App ID)</label>
              <input
                value={clientId}
                onChange={e => setClientId(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono"
                placeholder="YourName-AppName-PRD-..."
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Client Secret (Cert ID)</label>
              <input
                type="password"
                value={clientSecret}
                onChange={e => setClientSecret(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono"
                placeholder="PRD-..."
              />
            </div>
            <button
              onClick={handleValidate}
              disabled={!clientId || !clientSecret || validateEbay.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm disabled:opacity-50"
            >
              {validateEbay.isPending ? 'Validating...' : 'Test Connection'}
              {validateStatus === 'ok' && <CheckCircle size={16} className="text-green-400" />}
              {validateStatus === 'fail' && <XCircle size={16} className="text-red-400" />}
            </button>
            {validateStatus === 'fail' && (
              <p className="text-xs text-red-400">Connection failed. Double-check your credentials.</p>
            )}
          </div>
        ) : (
          current.content
        )}

        <div className="flex justify-between mt-8">
          <button
            onClick={() => setStep(s => s - 1)}
            disabled={step === 0}
            className="px-4 py-2 text-sm text-gray-400 hover:text-gray-100 disabled:opacity-30"
          >
            Back
          </button>
          {step < STEPS.length - 1 ? (
            <button
              onClick={() => setStep(s => s + 1)}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium"
            >
              Next
            </button>
          ) : (
            <button
              onClick={handleFinish}
              disabled={!clientId || !clientSecret || updateSettings.isPending}
              className="px-6 py-2 bg-green-600 hover:bg-green-500 rounded-lg text-sm font-medium disabled:opacity-50"
            >
              {updateSettings.isPending ? 'Saving...' : 'Finish Setup'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
