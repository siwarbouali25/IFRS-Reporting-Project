import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, map } from 'rxjs';

import { TokenService } from '../auth/token.service';

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
  streaming?: boolean;
}

export type StreamEvent =
  | { type: 'status'; text: string }
  | { type: 'token'; text: string }
  | { type: 'citations'; citations: Citation[] }
  | {
      type: 'done';
      conversation_id: string;
      message_id: string;
      model_used: string;
      is_fallback: boolean;
    }
  | { type: 'error'; message: string };

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
    private http: HttpClient,
    private tokenService: TokenService
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

  /**
   * Streams a turn via SSE. EventSource can't send the JWT header, so we use
   * fetch + a ReadableStream reader, attaching the Bearer token manually and
   * parsing `data:` frames into StreamEvents.
   */
  chatStream(
    message: string,
    conversationId?: string,
    bankCode?: string
  ): Observable<StreamEvent> {
    const body: ChatRequest = { message };
    if (conversationId) {
      body.conversation_id = conversationId;
    }
    if (bankCode) {
      body.bank_code = bankCode;
    }

    const token = this.tokenService.getAccessToken();

    return new Observable<StreamEvent>((subscriber) => {
      const controller = new AbortController();

      (async () => {
        try {
          const res = await fetch(
            `${this.apiUrl}/assistant/chat/stream/`,
            {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                ...(token
                  ? { Authorization: `Bearer ${token}` }
                  : {}),
              },
              body: JSON.stringify(body),
              signal: controller.signal,
            }
          );

          if (!res.ok || !res.body) {
            subscriber.next({
              type: 'error',
              message: `Request failed (${res.status}).`,
            });
            subscriber.complete();
            return;
          }

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              break;
            }
            buffer += decoder.decode(value, { stream: true });

            // SSE frames are separated by a blank line.
            const frames = buffer.split('\n\n');
            buffer = frames.pop() ?? '';

            for (const frame of frames) {
              const line = frame
                .split('\n')
                .find((l) => l.startsWith('data:'));
              if (!line) {
                continue;
              }
              const payload = line.slice(5).trim();
              if (!payload) {
                continue;
              }
              try {
                subscriber.next(
                  JSON.parse(payload) as StreamEvent
                );
              } catch {
                // ignore malformed frame
              }
            }
          }
          subscriber.complete();
        } catch (err: unknown) {
          if (
            err instanceof DOMException &&
            err.name === 'AbortError'
          ) {
            subscriber.complete();
          } else {
            subscriber.error(err);
          }
        }
      })();

      return () => controller.abort();
    });
  }
}
