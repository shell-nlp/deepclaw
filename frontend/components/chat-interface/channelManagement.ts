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
