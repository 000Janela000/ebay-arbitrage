import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from './client'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Settings {
  ebay_client_id: string
  ebay_client_secret: string
  ebay_environment: string
  shipping_rate_per_kg: number
  default_weight_kg: number
  vat_enabled: boolean
  vat_rate: number
  platform_fee_pct: number
  payment_fee_pct: number
  handling_fee_usd: number
}

export interface Category {
  ebay_category_id: string
  name: string
  avg_ebay_sold_usd: number | null
  avg_georgian_price_usd: number | null
  avg_profit_margin_pct: number | null
  avg_weight_kg: number | null
  total_active_auctions: number
  last_analyzed_at: string | null
}

export interface AuctionOpportunity {
  ebay_item_id: string
  title: string
  image_url: string | null
  item_url: string
  current_bid_usd: number
  estimated_final_usd: number
  bid_count: number
  ends_at: string
  seconds_remaining: number
  weight_kg: number
  weight_source: string
  shipping_cost_usd: number
  vat_usd: number
  total_landed_cost_usd: number
  total_landed_cost_gel: number
  georgian_median_price_gel: number | null
  georgian_median_price_usd: number | null
  net_revenue_usd: number | null
  selling_fees_usd: number | null
  georgian_listing_count: number
  profit_margin_pct: number | null
  profit_usd: number | null
  profit_gel: number | null
  opportunity_score: number
  margin_score: number
  urgency_score: number
  confidence_score: number
  demand_score: number | null
  competition_score: number
  ebay_category_id: string
  has_georgian_data: boolean
  data_quality_warning: string | null
}

export interface CurrencyRateResponse {
  usd_gel: number
  from: string
  to: string
  is_stale: boolean
  is_fallback: boolean
  fetched_at: string | null
  age_minutes: number | null
}

export interface OpportunitiesResponse {
  total: number
  offset: number
  limit: number
  items: AuctionOpportunity[]
  api_usage: {
    calls_made: number
    remaining: number
    limit: number
    warn: boolean
  }
}

export interface JobStatus {
  job_id: string
  status: 'running' | 'done' | 'error'
  progress: number
  message: string
  scraper_status?: Record<string, boolean>
}

// Category tree types
export interface CategoryNode {
  ebay_category_id: string
  name: string
  child_count: number
  is_leaf: boolean
  is_tracked: boolean
  avg_profit_margin_pct: number | null
  last_analyzed_at: string | null
}

export interface CategoryBreadcrumb {
  ebay_category_id: string
  name: string
}

export interface CategorySearchResult {
  ebay_category_id: string
  name: string
  breadcrumb_path: string
  is_leaf: boolean
  is_tracked: boolean
  avg_profit_margin_pct: number | null
}

export interface TrackedCategory {
  ebay_category_id: string
  name: string
  breadcrumb_path: string
  is_leaf: boolean
  avg_ebay_sold_usd: number | null
  avg_georgian_price_usd: number | null
  avg_profit_margin_pct: number | null
  avg_weight_kg: number | null
  total_active_auctions: number
  last_analyzed_at: string | null
  manual_pin: boolean
  manual_block: boolean
  track_source: 'manual' | 'auto' | 'none'
  auto_track_score: number | null
  auto_tracked_at: string | null
}

export interface TreeMeta {
  tree_version: string | null
  last_fetched_at: string | null
  total_categories: number | null
}

export interface AuctionDetail {
  item: {
    ebay_item_id: string
    title: string
    current_bid_usd: number
    bid_count: number
    condition: string | null
    item_url: string
    image_url: string | null
    weight_kg: number | null
    weight_source: string | null
    seller_feedback_pct: number | null
    ends_at: string
    ebay_category_id: string
  }
  price_estimate: {
    estimated_final_usd: number
    confidence_score: number
    estimation_method: string
    bin_sample_count: number
    bin_price_median_usd: number | null
    bin_price_min_usd: number | null
    bin_price_max_usd: number | null
  } | null
  opportunity: {
    total_landed_cost_usd: number
    total_landed_cost_gel: number
    georgian_median_price_gel: number | null
    georgian_median_price_usd: number | null
    net_revenue_usd: number | null
    selling_fees_usd: number | null
    profit_margin_pct: number | null
    profit_gel: number | null
    profit_usd: number | null
    opportunity_score: number
    margin_score: number
    urgency_score: number
    confidence_score: number
    demand_score: number | null
    competition_score: number
    shipping_cost_usd: number
    vat_usd: number
    gel_rate_used: number
    data_quality_warning: string | null
  } | null
  georgian_listings: {
    platform: string
    title: string
    price_gel: number
    price_usd: number
    url: string
    image_url: string | null
    similarity_score: number
    price_mismatch: boolean
  }[]
}

// ─── Fetch functions (exported for use without hooks) ─────────────────────────

export const fetchSettings = () => client.get<Settings>('/settings').then(r => r.data)
export const fetchCurrencyRate = () => client.get<CurrencyRateResponse>('/settings/currency-rate').then(r => r.data)
export const fetchCategories = (sortBy = 'avg_profit_margin_pct') =>
  client.get<Category[]>('/categories', { params: { sort_by: sortBy } }).then(r => r.data)
export const fetchOpportunities = (params: Record<string, unknown> = {}) =>
  client.get<OpportunitiesResponse>('/opportunities', { params }).then(r => r.data)
export const fetchAuctions = (params: Record<string, unknown> = {}) =>
  client.get<AuctionOpportunity[]>('/auctions', { params }).then(r => r.data)
export const fetchAuctionDetail = (id: string) =>
  client.get<AuctionDetail>(`/auctions/${id}`).then(r => r.data)
export const fetchJobStatus = (jobId: string) =>
  client.get<JobStatus>('/categories/analyze/status', { params: { job_id: jobId } }).then(r => r.data)
export const fetchRefreshStatus = (jobId: string) =>
  client.get<JobStatus>('/auctions/refresh/status', { params: { job_id: jobId } }).then(r => r.data)

// Category tree fetch functions
export const fetchCategoryRoots = () =>
  client.get<CategoryNode[]>('/categories/tree/roots').then(r => r.data)
export const fetchCategoryChildren = (parentId: string) =>
  client.get<CategoryNode[]>(`/categories/tree/${parentId}/children`).then(r => r.data)
export const fetchCategoryBreadcrumb = (categoryId: string) =>
  client.get<CategoryBreadcrumb[]>(`/categories/tree/${categoryId}/breadcrumb`).then(r => r.data)
export const fetchCategorySearch = (q: string) =>
  client.get<CategorySearchResult[]>('/categories/search', { params: { q } }).then(r => r.data)
export const fetchTrackedCategories = () =>
  client.get<TrackedCategory[]>('/categories/tracked').then(r => r.data)
export const fetchTreeMeta = () =>
  client.get<TreeMeta>('/categories/tree/meta').then(r => r.data)

// ─── React Query hooks ────────────────────────────────────────────────────────

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
}

export function useCurrencyRate() {
  return useQuery({
    queryKey: ['currency-rate'],
    queryFn: fetchCurrencyRate,
    refetchInterval: 60_000,
  })
}

export function downloadCsv(params: Record<string, unknown> = {}) {
  const query = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') query.set(k, String(v))
  }
  const url = `/api/opportunities/export.csv?${query.toString()}`
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

export function useCategories(sortBy = 'avg_profit_margin_pct') {
  return useQuery({
    queryKey: ['categories', sortBy],
    queryFn: () => fetchCategories(sortBy),
  })
}

export function useOpportunities(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['opportunities', params],
    queryFn: () => fetchOpportunities(params),
    refetchInterval: 60_000,
  })
}

export function useAuctions(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['auctions', params],
    queryFn: () => fetchAuctions(params),
    refetchInterval: 60_000,
  })
}

export function useAuctionDetail(id: string | null) {
  return useQuery({
    queryKey: ['auction-detail', id],
    queryFn: () => fetchAuctionDetail(id!),
    enabled: !!id,
  })
}

export function useUpdateSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Settings>) => client.put('/settings', data).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })
}

export function useValidateEbay() {
  return useMutation({
    mutationFn: (data: { client_id: string; client_secret: string; environment: string }) =>
      client.post('/settings/validate-ebay', data).then(r => r.data),
  })
}

export function useStartCategoryAnalysis() {
  return useMutation({
    mutationFn: () => client.post<{ job_id: string }>('/categories/analyze').then(r => r.data),
  })
}

export function useStartSingleCategoryAnalysis() {
  return useMutation({
    mutationFn: (categoryId: string) =>
      client.post<{ job_id: string }>(`/categories/${categoryId}/analyze`).then(r => r.data),
  })
}

// Category tree hooks
export function useCategoryChildren(parentId: string | null) {
  return useQuery({
    queryKey: ['category-children', parentId],
    queryFn: () => parentId ? fetchCategoryChildren(parentId) : fetchCategoryRoots(),
  })
}

export function useCategoryBreadcrumb(categoryId: string | null) {
  return useQuery({
    queryKey: ['category-breadcrumb', categoryId],
    queryFn: () => fetchCategoryBreadcrumb(categoryId!),
    enabled: !!categoryId,
  })
}

export function useCategorySearch(query: string) {
  return useQuery({
    queryKey: ['category-search', query],
    queryFn: () => fetchCategorySearch(query),
    enabled: query.length >= 2,
  })
}

export function useTrackedCategories() {
  return useQuery({
    queryKey: ['tracked-categories'],
    queryFn: fetchTrackedCategories,
  })
}

export function useTreeMeta() {
  return useQuery({
    queryKey: ['tree-meta'],
    queryFn: fetchTreeMeta,
  })
}

export function useTrackCategory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (categoryId: string) =>
      client.post(`/categories/${categoryId}/track`).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tracked-categories'] })
      qc.invalidateQueries({ queryKey: ['category-children'] })
      qc.invalidateQueries({ queryKey: ['category-search'] })
      qc.invalidateQueries({ queryKey: ['categories'] })
    },
  })
}

export function useUntrackCategory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (categoryId: string) =>
      client.delete(`/categories/${categoryId}/track`).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tracked-categories'] })
      qc.invalidateQueries({ queryKey: ['category-children'] })
      qc.invalidateQueries({ queryKey: ['category-search'] })
      qc.invalidateQueries({ queryKey: ['categories'] })
    },
  })
}

export function useSyncCategoryTree() {
  return useMutation({
    mutationFn: () => client.post<{ job_id: string }>('/categories/sync-tree').then(r => r.data),
  })
}

export interface DiscoverPreview {
  category_id: string
  category_name: string
  leaf_count: number
  api_calls_needed: number
  budget_pct: number
}

export const fetchDiscoverPreview = (categoryId: string) =>
  client.get<DiscoverPreview>(`/categories/${categoryId}/discover/preview`).then(r => r.data)

export function useDiscoverPreview(categoryId: string | null) {
  return useQuery({
    queryKey: ['discover-preview', categoryId],
    queryFn: () => fetchDiscoverPreview(categoryId!),
    enabled: !!categoryId,
  })
}

export function useDiscoverCategory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ categoryId, maxCategories }: { categoryId: string; maxCategories?: number }) =>
      client.post<{ job_id: string; leaf_count: number }>(
        `/categories/${categoryId}/discover`,
        null,
        { params: maxCategories ? { max_categories: maxCategories } : {} },
      ).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tracked-categories'] })
      qc.invalidateQueries({ queryKey: ['category-children'] })
      qc.invalidateQueries({ queryKey: ['categories'] })
    },
  })
}

export function useStartRefresh() {
  return useMutation({
    mutationFn: (categoryId?: string) =>
      client.post<{ job_id: string }>('/auctions/refresh', null, {
        params: categoryId ? { category_id: categoryId } : {},
      }).then(r => r.data),
  })
}

export function useOverrideWeight() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ ebayItemId, weightKg }: { ebayItemId: string; weightKg: number }) =>
      client.put(`/auctions/${ebayItemId}/weight`, { weight_kg: weightKg }).then(r => r.data),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['auction-detail', vars.ebayItemId] })
      qc.invalidateQueries({ queryKey: ['opportunities'] })
      qc.invalidateQueries({ queryKey: ['auctions'] })
    },
  })
}

export function usePinCategory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (categoryId: string) => client.post(`/categories/${categoryId}/pin`).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tracked-categories'] })
      qc.invalidateQueries({ queryKey: ['category-children'] })
      qc.invalidateQueries({ queryKey: ['category-search'] })
      qc.invalidateQueries({ queryKey: ['categories'] })
    },
  })
}

export function useBlockCategory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (categoryId: string) => client.post(`/categories/${categoryId}/block`).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tracked-categories'] })
      qc.invalidateQueries({ queryKey: ['category-children'] })
      qc.invalidateQueries({ queryKey: ['category-search'] })
      qc.invalidateQueries({ queryKey: ['categories'] })
    },
  })
}

export function useClearCategoryOverride() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (categoryId: string) => client.delete(`/categories/${categoryId}/override`).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tracked-categories'] })
      qc.invalidateQueries({ queryKey: ['category-children'] })
      qc.invalidateQueries({ queryKey: ['category-search'] })
      qc.invalidateQueries({ queryKey: ['categories'] })
    },
  })
}

// Modern hunter types
export interface ModernSettings {
  strategy_profile: 'balanced' | 'aggressive' | 'conservative'
  target_margin_floor_pct: number
  demand_gate_min_listings: number
  demand_gate_min_score: number
  auction_window_min_hours: number
  auction_window_max_hours: number
  max_categories_per_refresh: number
  max_items_per_category: number
  deep_scrape_top_k: number
}

export interface ModernOpportunity {
  ebay_item_id: string
  title: string
  image_url: string | null
  item_url: string
  current_bid_usd: number
  estimated_final_usd: number
  anchor_price_usd: number | null
  current_discount_pct: number | null
  projected_discount_pct: number | null
  steal_score: number
  winability_score: number
  demand_gate_passed: boolean
  gate_reason: string | null
  final_score: number
  bid_count: number
  ends_at: string
  seconds_remaining: number
  weight_kg: number
  weight_source: string
  shipping_cost_usd: number
  vat_usd: number
  total_landed_cost_usd: number
  total_landed_cost_gel: number
  georgian_median_price_gel: number | null
  georgian_median_price_usd: number | null
  net_revenue_usd: number | null
  selling_fees_usd: number | null
  georgian_listing_count: number
  profit_margin_pct: number | null
  profit_usd: number | null
  profit_gel: number | null
  margin_score: number
  urgency_score: number
  confidence_score: number
  demand_score: number | null
  competition_score: number
  ebay_category_id: string
  has_georgian_data: boolean
  data_quality_warning: string | null
}

export interface ModernOpportunitiesResponse {
  total: number
  offset: number
  limit: number
  items: ModernOpportunity[]
  api_usage: {
    calls_made: number
    remaining: number
    limit: number
    warn: boolean
  }
}

export interface ModernRefreshStatus {
  job_id: string
  status: 'running' | 'done' | 'error'
  progress: number
  message: string
  metrics: Record<string, number>
  scraper_status: Record<string, boolean>
}

export interface ModernTrackingSettings {
  tracking_mode: 'hybrid_auto_manual' | 'auto_only' | 'manual_only'
  auto_track_enabled: boolean
  auto_track_max_categories: number
  auto_track_refresh_hours: number
  auto_track_min_liquidity: number
  auto_track_min_score: number
  focus_policy: 'weekly_winner' | 'per_refresh_winner' | 'mixed_fixed'
  focus_bucket: 'auto' | 'electronics_small' | 'antiques_decor' | 'mixed'
  focus_last_decided_at: string
  realism_max_extreme_margin_pct: number
  realism_min_positive_discount_share: number
}

export interface ModernTrackingRecommendation {
  category_id: string
  category_name: string
  is_leaf: boolean
  is_tracked: boolean
  source: 'manual' | 'auto' | 'none'
  category_track_score: number
  factor_breakdown: {
    liquidity: number
    qualification: number
    comparables: number
    realism: number
    stability: number
    data_health: number
  }
  decision: 'track' | 'hold' | 'drop'
  reasons: string[]
}

export interface ModernTrackingRecommendationsResponse {
  focus_bucket: 'electronics_small' | 'antiques_decor' | 'mixed'
  focus_metrics: Record<string, Record<string, number>>
  total: number
  items: ModernTrackingRecommendation[]
}

export interface ModernTrackingRefreshStatus {
  job_id: string
  status: 'running' | 'done' | 'error'
  progress: number
  message: string
  metrics: Record<string, number | string>
}

export interface ModernTrackingAuditEntry {
  id: number
  run_at: string
  focus_bucket: string
  category_id: string
  score: number | null
  decision: string
  reasons: Record<string, unknown>
}

export interface ModernTrackingAuditResponse {
  total: number
  items: ModernTrackingAuditEntry[]
}

export const fetchModernSettings = () =>
  client.get<ModernSettings>('/modern/settings').then(r => r.data)

export const fetchModernOpportunities = (params: Record<string, unknown> = {}) =>
  client.get<ModernOpportunitiesResponse>('/modern/opportunities', { params }).then(r => r.data)

export const fetchModernRefreshStatus = (jobId: string) =>
  client.get<ModernRefreshStatus>('/modern/refresh/status', { params: { job_id: jobId } }).then(r => r.data)

export const fetchModernTrackingSettings = () =>
  client.get<ModernTrackingSettings>('/modern/tracking/settings').then(r => r.data)

export const fetchModernTrackingRecommendations = (params: Record<string, unknown> = {}) =>
  client.get<ModernTrackingRecommendationsResponse>('/modern/tracking/recommendations', { params }).then(r => r.data)

export const fetchModernTrackingRefreshStatus = (jobId: string) =>
  client.get<ModernTrackingRefreshStatus>('/modern/tracking/refresh/status', { params: { job_id: jobId } }).then(r => r.data)

export const fetchModernTrackingAudit = (params: Record<string, unknown> = {}) =>
  client.get<ModernTrackingAuditResponse>('/modern/tracking/audit', { params }).then(r => r.data)

export function downloadModernCsv(params: Record<string, unknown> = {}) {
  const query = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') query.set(k, String(v))
  }
  const url = `/api/modern/opportunities/export.csv?${query.toString()}`
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

export function useModernSettings() {
  return useQuery({
    queryKey: ['modern-settings'],
    queryFn: fetchModernSettings,
  })
}

export function useUpdateModernSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<ModernSettings>) =>
      client.put<ModernSettings>('/modern/settings', data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['modern-settings'] })
    },
  })
}

export function useModernOpportunities(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['modern-opportunities', params],
    queryFn: () => fetchModernOpportunities(params),
    refetchInterval: 60_000,
  })
}

export function useStartModernRefresh() {
  return useMutation({
    mutationFn: (body?: { strategy_profile?: 'balanced' | 'aggressive' | 'conservative' }) =>
      client.post<{ job_id: string }>('/modern/refresh', body ?? null).then(r => r.data),
  })
}

export function useModernTrackingSettings() {
  return useQuery({
    queryKey: ['modern-tracking-settings'],
    queryFn: fetchModernTrackingSettings,
  })
}

export function useUpdateModernTrackingSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<ModernTrackingSettings>) =>
      client.put<ModernTrackingSettings>('/modern/tracking/settings', data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['modern-tracking-settings'] })
      qc.invalidateQueries({ queryKey: ['modern-tracking-recommendations'] })
    },
  })
}

export function useModernTrackingRecommendations(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['modern-tracking-recommendations', params],
    queryFn: () => fetchModernTrackingRecommendations(params),
    refetchInterval: 120_000,
  })
}

export function useModernTrackingAudit(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['modern-tracking-audit', params],
    queryFn: () => fetchModernTrackingAudit(params),
  })
}

export function useStartModernTrackingRefresh() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body?: { apply_changes?: boolean; force_focus_recompute?: boolean }) =>
      client.post<{ job_id: string }>('/modern/tracking/refresh', body ?? null).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['modern-tracking-recommendations'] })
      qc.invalidateQueries({ queryKey: ['modern-tracking-audit'] })
      qc.invalidateQueries({ queryKey: ['tracked-categories'] })
      qc.invalidateQueries({ queryKey: ['categories'] })
    },
  })
}
