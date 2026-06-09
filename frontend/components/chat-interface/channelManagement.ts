export interface ChannelManagementBootstrapActions {
  loadBoundUsers: boolean
  generateQrcodeUserId: string | null
}

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
  status?: string
  runtime_state?: Record<string, unknown> | null
}

interface ChannelBindingFilters {
  ownerUserId: string
  channel: string
  status: string
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
