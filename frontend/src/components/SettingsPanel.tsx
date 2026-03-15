import { useState, useEffect } from 'react'
import { X, Eye, EyeOff, CheckCircle, XCircle } from 'lucide-react'
import { useSettings, useUpdateSettings, useValidateEbay, useCurrencyRate } from '../api/hooks'

interface Props {
  open: boolean
  onClose: () => void
}

export default function SettingsPanel({ open, onClose }: Props) {
  const { data: settings } = useSettings()
  const { data: rateData } = useCurrencyRate()
  const updateSettings = useUpdateSettings()
  const validateEbay = useValidateEbay()

  const [form, setForm] = useState({
    ebay_client_id: '',
    ebay_client_secret: '',
    ebay_environment: 'production',
    shipping_rate_per_kg: 9.0,
    default_weight_kg: 0.5,
    vat_enabled: false,
    vat_rate: 0.18,
    platform_fee_pct: 0,
    payment_fee_pct: 0,
    handling_fee_usd: 0,
  })
  const [showSecret, setShowSecret] = useState(false)
  const [validateStatus, setValidateStatus] = useState<'idle' | 'ok' | 'fail'>('idle')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (settings) {
      setForm({
        ebay_client_id: settings.ebay_client_id,
        ebay_client_secret: settings.ebay_client_secret,
        ebay_environment: settings.ebay_environment,
        shipping_rate_per_kg: settings.shipping_rate_per_kg,
        default_weight_kg: settings.default_weight_kg,
        vat_enabled: settings.vat_enabled,
        vat_rate: settings.vat_rate,
        platform_fee_pct: settings.platform_fee_pct,
        payment_fee_pct: settings.payment_fee_pct,
        handling_fee_usd: settings.handling_fee_usd,
      })
    }
  }, [settings])

  if (!open) return null

  const handleSave = async () => {
    await updateSettings.mutateAsync(form)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleValidate = async () => {
    setValidateStatus('idle')
    try {
      await validateEbay.mutateAsync({
        client_id: form.ebay_client_id,
        client_secret: form.ebay_client_secret,
        environment: form.ebay_environment,
      })
      setValidateStatus('ok')
    } catch {
      setValidateStatus('fail')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-gray-900 border-l border-gray-800 w-full max-w-md p-6 overflow-y-auto shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold">Settings</h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-800 rounded">
            <X size={20} />
          </button>
        </div>

        {/* eBay API */}
        <section className="mb-6">
          <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">
            eBay API Credentials
          </h3>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Environment</label>
              <select
                value={form.ebay_environment}
                onChange={e => setForm(f => ({ ...f, ebay_environment: e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              >
                <option value="production">Production</option>
                <option value="sandbox">Sandbox</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Client ID</label>
              <input
                value={form.ebay_client_id}
                onChange={e => setForm(f => ({ ...f, ebay_client_id: e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono"
                placeholder="Your eBay Client ID"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Client Secret</label>
              <div className="relative">
                <input
                  type={showSecret ? 'text' : 'password'}
                  value={form.ebay_client_secret}
                  onChange={e => setForm(f => ({ ...f, ebay_client_secret: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 pr-10 text-sm font-mono"
                  placeholder="Your eBay Client Secret"
                />
                <button
                  onClick={() => setShowSecret(v => !v)}
                  className="absolute right-3 top-2.5 text-gray-500 hover:text-gray-300"
                >
                  {showSecret ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>
            <button
              onClick={handleValidate}
              disabled={validateEbay.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-blue-700 hover:bg-blue-600 rounded-lg text-sm disabled:opacity-50"
            >
              {validateEbay.isPending ? 'Validating...' : 'Validate Credentials'}
              {validateStatus === 'ok' && <CheckCircle size={16} className="text-green-400" />}
              {validateStatus === 'fail' && <XCircle size={16} className="text-red-400" />}
            </button>
            {validateStatus === 'ok' && <p className="text-xs text-green-400">Credentials valid!</p>}
            {validateStatus === 'fail' && <p className="text-xs text-red-400">Invalid credentials. Check and retry.</p>}
          </div>
        </section>

        {/* Shipping */}
        <section className="mb-6">
          <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">Shipping</h3>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Rate ($/kg)</label>
              <input
                type="number"
                value={form.shipping_rate_per_kg}
                onChange={e => setForm(f => ({ ...f, shipping_rate_per_kg: Number(e.target.value) }))}
                step="0.5"
                min="0"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Default Weight (kg)</label>
              <input
                type="number"
                value={form.default_weight_kg}
                onChange={e => setForm(f => ({ ...f, default_weight_kg: Number(e.target.value) }))}
                step="0.1"
                min="0.1"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>
        </section>

        {/* Selling fees */}
        <section className="mb-6">
          <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">Selling Fees</h3>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Marketplace fee (%)</label>
              <input
                type="number"
                value={form.platform_fee_pct * 100}
                onChange={e => setForm(f => ({ ...f, platform_fee_pct: Number(e.target.value) / 100 }))}
                step="0.5"
                min="0"
                max="100"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Payment processing fee (%)</label>
              <input
                type="number"
                value={form.payment_fee_pct * 100}
                onChange={e => setForm(f => ({ ...f, payment_fee_pct: Number(e.target.value) / 100 }))}
                step="0.5"
                min="0"
                max="100"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Fixed handling fee ($)</label>
              <input
                type="number"
                value={form.handling_fee_usd}
                onChange={e => setForm(f => ({ ...f, handling_fee_usd: Number(e.target.value) }))}
                step="0.5"
                min="0"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>
        </section>

        {/* VAT */}
        <section className="mb-6">
          <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">VAT</h3>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <label className="text-sm">Enable VAT</label>
              <button
                onClick={() => setForm(f => ({ ...f, vat_enabled: !f.vat_enabled }))}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${form.vat_enabled ? 'bg-blue-600' : 'bg-gray-700'}`}
              >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${form.vat_enabled ? 'translate-x-6' : 'translate-x-1'}`} />
              </button>
            </div>
            {form.vat_enabled && (
              <div>
                <label className="text-xs text-gray-400 mb-1 block">VAT Rate (%)</label>
                <input
                  type="number"
                  value={form.vat_rate * 100}
                  onChange={e => setForm(f => ({ ...f, vat_rate: Number(e.target.value) / 100 }))}
                  step="1"
                  min="0"
                  max="100"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
                />
              </div>
            )}
          </div>
        </section>

        {/* Currency */}
        <section className="mb-6">
          <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">Currency</h3>
          <p className="text-sm text-gray-300">
            USD/GEL: <span className="font-mono text-blue-400">{rateData?.usd_gel?.toFixed(4) ?? '—'}</span>
            {rateData?.is_fallback && (
              <span className="ml-2 text-xs text-orange-400">(stale{rateData.age_minutes ? `, ${rateData.age_minutes}min old` : ''})</span>
            )}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            {rateData?.is_fallback
              ? 'NBG API unreachable — using cached rate. Profit margins may be slightly off.'
              : 'Fetched from NBG (National Bank of Georgia). Cached 1 hour.'}
          </p>
        </section>

        <button
          onClick={handleSave}
          disabled={updateSettings.isPending}
          className="w-full py-2 bg-green-700 hover:bg-green-600 rounded-lg text-sm font-medium disabled:opacity-50"
        >
          {saved ? '✓ Saved!' : updateSettings.isPending ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  )
}
