export interface ChannelManagementBootstrapActions {
  loadBoundUsers: boolean
  generateQrcodeUserId: string | null
}

export type ChannelManagementPage = 'weixin' | 'feishu'

interface ChannelManagementQrRenderStateInput {
  qrcode?: string | null
  qrcodeUrl?: string | null
  generatedDataUrl: string
}

export interface ChannelManagementQrRenderState {
  imageSrc: string
  shouldGenerateDataUrl: boolean
  payload: string
}

interface ChannelBindingLike {
  channel: string
  owner_user_id?: string
  manager_user_id?: string
  display_name?: string | null
  status?: string
  runtime_state?: Record<string, unknown> | null
  updated_at?: string
}

interface ChannelBindingFilters {
  ownerUserId: string
  channel: string
  status: string
}

interface ChannelNavItem {
  page: ChannelManagementPage
  label: string
  total: number
  summary: {
    total: number
    connected: number
    pending: number
    error: number
  }
}

export interface ChannelBindingOwnerRow {
  ownerUserId: string
  total: number
  displayNames: string[]
  summary: {
    total: number
    connected: number
    pending: number
    error: number
  }
  latestUpdatedAt: string
  managerUserIds: string[]
}

function isDirectImageUrl(value: string): boolean {
  const normalized = value.toLowerCase()
  return (
    normalized.startsWith('data:image/') ||
    normalized.endsWith('.png') ||
    normalized.endsWith('.jpg') ||
    normalized.endsWith('.jpeg') ||
    normalized.endsWith('.gif') ||
    normalized.endsWith('.webp') ||
    normalized.endsWith('.svg')
  )
}

export function getChannelManagementBootstrapActions(
  _userId: string
): ChannelManagementBootstrapActions {
  return {
    loadBoundUsers: true,
    generateQrcodeUserId: null,
  }
}

export function getChannelManagementQrRenderState({
  qrcode,
  qrcodeUrl,
  generatedDataUrl,
}: ChannelManagementQrRenderStateInput): ChannelManagementQrRenderState {
  const normalizedUrl = typeof qrcodeUrl === 'string' ? qrcodeUrl.trim() : ''
  const normalizedPayload = typeof qrcode === 'string' ? qrcode.trim() : ''

  if (normalizedUrl && isDirectImageUrl(normalizedUrl)) {
    return {
      imageSrc: normalizedUrl,
      shouldGenerateDataUrl: false,
      payload: normalizedPayload,
    }
  }

  return {
    imageSrc: generatedDataUrl,
    shouldGenerateDataUrl: Boolean(normalizedUrl || normalizedPayload),
    payload: normalizedUrl || normalizedPayload,
  }
}

export function normalizeChannelManagementPage(
  value?: string
): ChannelManagementPage {
  return value === 'feishu' ? 'feishu' : 'weixin'
}

export function resolveChannelEntryPage(
  requestedPage?: string,
  lastVisitedPage: ChannelManagementPage = 'weixin'
): ChannelManagementPage {
  if (requestedPage) return normalizeChannelManagementPage(requestedPage)
  return normalizeChannelManagementPage(lastVisitedPage)
}

export function mergeGeneratedQrcodes(
  current: Record<number, string>,
  next: Record<number, string>
): Record<number, string> {
  const nextEntries = Object.entries(next)
  if (nextEntries.length === 0) return current

  let changed = false
  for (const [bindingId, dataUrl] of nextEntries) {
    if (current[Number(bindingId)] !== dataUrl) {
      changed = true
      break
    }
  }
  if (!changed) return current
  return { ...current, ...next }
}

export function groupBindingsByChannel<T extends ChannelBindingLike>(bindings: T[]) {
  return bindings.reduce<Record<string, T[]>>((groups, binding) => {
    const existing = groups[binding.channel] || []
    existing.push(binding)
    groups[binding.channel] = existing
    return groups
  }, {})
}

export function summarizeChannelBindings(bindings: ChannelBindingLike[]) {
  return bindings.reduce(
    (summary, binding) => {
      summary.total += 1
      const runtimeStatus = String(binding.runtime_state?.status || binding.status || '')
      if (runtimeStatus === 'connected') {
        summary.connected += 1
      } else if (runtimeStatus === 'error') {
        summary.error += 1
      } else {
        summary.pending += 1
      }
      return summary
    },
    { total: 0, connected: 0, pending: 0, error: 0 }
  )
}

export function selectBindingsByChannelPage<T extends ChannelBindingLike>(
  bindings: T[],
  page: ChannelManagementPage
) {
  const targetChannel = page === 'feishu' ? 'feishu' : 'weixin_clawbot'
  return bindings.filter((binding) => binding.channel === targetChannel)
}

export function buildChannelNavItems(
  bindings: ChannelBindingLike[]
): ChannelNavItem[] {
  const weixinBindings = selectBindingsByChannelPage(bindings, 'weixin')
  const feishuBindings = selectBindingsByChannelPage(bindings, 'feishu')

  return [
    {
      page: 'weixin',
      label: '微信绑定',
      total: weixinBindings.length,
      summary: summarizeChannelBindings(weixinBindings),
    },
    {
      page: 'feishu',
      label: '飞书绑定',
      total: feishuBindings.length,
      summary: summarizeChannelBindings(feishuBindings),
    },
  ]
}

export function buildBindingOwnerRows<T extends ChannelBindingLike>(
  bindings: T[]
): ChannelBindingOwnerRow[] {
  const groups = bindings.reduce<
    Record<
      string,
      {
        bindings: T[]
        latestUpdatedAt: string
        managerUserIds: Set<string>
        displayNames: Set<string>
      }
    >
  >((accumulator, binding) => {
    const ownerUserId = String(binding.owner_user_id || '').trim()
    if (!ownerUserId) return accumulator

    const existing =
      accumulator[ownerUserId] ||
      {
        bindings: [],
        latestUpdatedAt: '',
        managerUserIds: new Set<string>(),
        displayNames: new Set<string>(),
      }
    existing.bindings.push(binding)
    if (binding.updated_at && binding.updated_at > existing.latestUpdatedAt) {
      existing.latestUpdatedAt = binding.updated_at
    }
    if (binding.manager_user_id) {
      existing.managerUserIds.add(binding.manager_user_id)
    }
    if (binding.display_name) {
      existing.displayNames.add(binding.display_name)
    }
    accumulator[ownerUserId] = existing
    return accumulator
  }, {})

  return Object.entries(groups)
    .map(([ownerUserId, group]) => ({
      ownerUserId,
      total: group.bindings.length,
      displayNames: Array.from(group.displayNames),
      summary: summarizeChannelBindings(group.bindings),
      latestUpdatedAt: group.latestUpdatedAt,
      managerUserIds: Array.from(group.managerUserIds).sort(),
    }))
    .sort((left, right) => {
      if (left.latestUpdatedAt !== right.latestUpdatedAt) {
        return right.latestUpdatedAt.localeCompare(left.latestUpdatedAt)
      }
      if (left.total !== right.total) {
        return right.total - left.total
      }
      return left.ownerUserId.localeCompare(right.ownerUserId)
    })
}

export function filterBindingsForAdminOverview<T extends ChannelBindingLike>(
  bindings: T[],
  filters: ChannelBindingFilters
) {
  return bindings.filter((binding) => {
    if (filters.ownerUserId && binding.owner_user_id !== filters.ownerUserId) {
      return false
    }
    if (filters.channel && binding.channel !== filters.channel) {
      return false
    }
    if (filters.status) {
      const runtimeStatus = String(binding.runtime_state?.status || binding.status || '')
      if (runtimeStatus !== filters.status) {
        return false
      }
    }
    return true
  })
}

export function normalizeBindingOwnerUserId(input: string, fallbackUserId: string): string {
  const normalized = input.trim()
  if (normalized) return normalized
  return fallbackUserId.trim()
}
