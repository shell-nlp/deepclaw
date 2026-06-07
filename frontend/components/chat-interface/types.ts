export interface Message {
  id: string
  role: 'user' | 'ai'
  content: string
  reasoningContent?: string
  reasoningBlocks?: ReasoningBlock[]
  contentBlocks?: ReasoningBlock[]
  messageItems?: AssistantMessageItem[]
  toolData?: ToolData[]
}

export interface ReasoningBlock {
  id: string
  content: string
}

export type AssistantMessageItem =
  | {
      id: string
      type: 'reasoning'
      reasoningBlockId: string
    }
  | {
      id: string
      type: 'tool'
      toolCallId: string
    }
  | {
      id: string
      type: 'content'
      contentBlockId: string
    }

export interface ToolData {
  toolCall: {
    id: string
    name: string
    args: Record<string, unknown>
  }
  toolOutput?: Array<{
    tool_call_id: string
    content: string
  }>
}

export interface StreamEvent {
  event: 'token' | 'tool_calls' | 'tool_output' | '__interrupt__'
  data: {
    id?: string
    token?: string
    reasoning_token?: string
    tool_calls?: Array<{
      id: string
      name: string
      args: Record<string, unknown>
    }>
    tool_output?: Array<{
      tool_call_id: string
      content: unknown
    }>
    __interrupt__?: {
      action_requests: Array<{
        name: string
        description?: string
        args?: Record<string, unknown>
        arguments?: Record<string, unknown>
      }>
      review_configs?: Array<{
        action_name: string
        allowed_decisions: Array<'approve' | 'edit' | 'reject'>
        args_schema?: Record<string, unknown>
      }>
    }
  } | null
}

export interface KnowledgeBase {
  knowledge_base_id: string
  user_id: string
  name: string
  description: string
  index_prefix: string
  passage_index: string
  entity_index: string
  relation_index: string
  document_count: number
  chunk_count: number
  created_at: string
  updated_at: string
}

export interface KnowledgeDocument {
  document_id: string
  knowledge_base_id: string
  user_id: string
  file_name: string
  display_name: string
  content_type: string
  file_size: number
  chunk_count: number
  storage_path: string
  created_at: string
  updated_at: string
}

export interface UploadResult {
  knowledge_base: KnowledgeBase
  documents: KnowledgeDocument[]
  errors: Array<{
    file_name: string
    error: string
  }>
}

export interface PaginatedKnowledgeBaseResponse {
  items: KnowledgeBase[]
  total: number
  page: number
  page_size: number
}

export interface PaginatedKnowledgeDocumentResponse {
  items: KnowledgeDocument[]
  total: number
  page: number
  page_size: number
}

export interface BulkDeleteKnowledgeBaseResponse {
  deleted_ids: string[]
  failed: Record<string, string>
}

export interface BulkDeleteDocumentResponse {
  deleted_ids: string[]
  failed: Record<string, string>
  knowledge_base?: KnowledgeBase | null
}

export type ViewMode = 'chat' | 'knowledge' | 'mcp' | 'skills' | 'channels'
export type KnowledgePage =
  | 'libraries'
  | 'library-detail'
  | 'document-detail'
  | 'users'
export type RequestMode = 'agent' | 'rag'
export type ChatStatus = 'ready' | 'connecting' | 'error'
export type InterruptData = NonNullable<
  NonNullable<StreamEvent['data']>['__interrupt__']
>

export interface KnowledgeChunk {
  chunk_id: string
  document_id: string
  segment_id?: number | string | null
  content: string
  metadata: Record<string, unknown>
}

export interface KnowledgeDocumentDetailResponse {
  knowledge_base: KnowledgeBase
  document: KnowledgeDocument
  chunks: KnowledgeChunk[]
  total_chunks: number
  page: number
  page_size: number
}

export interface McpServerSummary {
  name: string
  transport: string
  endpoint: string
}

export interface SkillRecord {
  skill_name: string
  path: string
  description: string
  file_count: number
  created_at: string
  updated_at: string
}

export interface SkillListResponse {
  items: SkillRecord[]
  total: number
}

export interface SkillUploadResponse {
  skill: SkillRecord
  extracted_files: number
}

export interface SkillDeleteResponse {
  skill_name: string
  deleted_path: string
}

export interface AuthUserSummary {
  email: string
  role: 'admin' | 'user'
  is_active: boolean
  user_id: string
}

export interface AuthLoginResponse {
  token: string
  user: AuthUserSummary
}

export interface AuthUserListResponse {
  items: AuthUserSummary[]
  total: number
}

export interface WeixinClawBotQrcodeResponse {
  qrcode?: string | null
  qrcode_url?: string | null
  raw?: Record<string, unknown>
}

export interface WeixinClawBotQrcodeStatusResponse {
  status?: string | null
  bot_token?: string | null
  baseurl?: string | null
  base_url?: string | null
  qrcode?: string | null
  qrcode_url?: string | null
  raw?: Record<string, unknown>
}

export interface WeixinClawBotBoundUser {
  user_id: string
  state_key: string
  connected: boolean
  status: string
  bot_token?: string | null
  qrcode_url?: string | null
  base_url?: string | null
  updated_at: string
}

export interface WeixinClawBotBoundUserListResponse {
  items: WeixinClawBotBoundUser[]
  total: number
}

export interface WeixinClawBotBoundUserDeleteResponse {
  user_id: string
  deleted: boolean
}
