import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, map } from 'rxjs';

export type ChatRole =
  | 'user'
  | 'assistant'
  | 'tool'
  | 'system';

export interface DataGap {
  field: string;
  reason: string;
  instruction: string;
  affected_years: number[];
}

export interface Citation {
  tool: string;
  provenance: {
    bank_code?: string;
    source?: string;
    [key: string]: unknown;
  };
  data_gaps: DataGap[];
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  citations: Citation[];
  model_used: string;
  is_fallback: boolean;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  bank_code: string | null;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export interface ConversationSummary {
  id: string;
  title: string;
  bank_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatResponse {
  conversation_id: string;
  message: ChatMessage;
}

interface ChatRequest {
  message: string;
  conversation_id?: string;
  bank_code?: string;
}

type ListResponse<T> =
  | T[]
  | { results: T[] };

@Injectable({
  providedIn: 'root',
})
export class AssistantService {
  private readonly apiUrl =
    'http://127.0.0.1:8000/api';

  constructor(
    private http: HttpClient
  ) {}

  chat(
    message: string,
    conversationId?: string,
    bankCode?: string
  ): Observable<ChatResponse> {
    const body: ChatRequest = { message };

    if (conversationId) {
      body.conversation_id = conversationId;
    }
    if (bankCode) {
      body.bank_code = bankCode;
    }

    return this.http.post<ChatResponse>(
      `${this.apiUrl}/assistant/chat/`,
      body
    );
  }

  listConversations():
    Observable<ConversationSummary[]> {
    return this.http
      .get<
        ListResponse<ConversationSummary>
      >(
        `${this.apiUrl}/assistant/conversations/`
      )
      .pipe(
        map((response) =>
          Array.isArray(response)
            ? response
            : response.results
        )
      );
  }

  getConversation(
    id: string
  ): Observable<Conversation> {
    return this.http.get<Conversation>(
      `${this.apiUrl}/assistant/conversations/${id}/`
    );
  }
}
