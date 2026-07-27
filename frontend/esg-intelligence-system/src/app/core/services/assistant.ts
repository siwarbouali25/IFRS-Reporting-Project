import {
  Component,
  ElementRef,
  OnInit,
  ViewChild,
  AfterViewChecked,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import {
  AssistantService,
  ChatMessage,
  ConversationSummary,
} from '../../core/services/assistant';
import {
  Risk as RiskService,
  PayloadManifestSummary,
} from '../../core/services/risk';

interface BankOption {
  code: string;
  name: string;
}

@Component({
  selector: 'app-assistant',
  imports: [CommonModule, FormsModule],
  templateUrl: './assistant.html',
  styleUrl: './assistant.css',
})
export class Assistant
  implements OnInit, AfterViewChecked
{
  @ViewChild('scrollAnchor')
  scrollAnchor?: ElementRef<HTMLDivElement>;

  messages: ChatMessage[] = [];
  conversations: ConversationSummary[] = [];
  banks: BankOption[] = [];

  conversationId: string | null = null;
  bankCode = '';
  draft = '';

  sending = false;
  error: string | null = null;

  private shouldScroll = false;

  constructor(
    private assistant: AssistantService,
    private risk: RiskService
  ) {}

  ngOnInit(): void {
    this.loadBanks();
    this.loadConversations();
  }

  ngAfterViewChecked(): void {
    if (this.shouldScroll) {
      this.scrollToBottom();
      this.shouldScroll = false;
    }
  }

  private loadBanks(): void {
    this.risk.getPayloadManifests().subscribe({
      next: (manifests) => {
        const seen = new Set<string>();
        const options: BankOption[] = [];

        for (const m of manifests) {
          if (m.bank_code && !seen.has(m.bank_code)) {
            seen.add(m.bank_code);
            options.push({
              code: m.bank_code,
              name: m.bank_name,
            });
          }
        }
        this.banks = options.sort((a, b) =>
          a.code.localeCompare(b.code)
        );
      },
      error: () => {
        // Bank scoping is optional; ignore load failures.
      },
    });
  }

  private loadConversations(): void {
    this.assistant.listConversations().subscribe({
      next: (list) => {
        this.conversations = list;
      },
      error: () => {},
    });
  }

  newConversation(): void {
    this.conversationId = null;
    this.messages = [];
    this.error = null;
    this.draft = '';
  }

  openConversation(id: string): void {
    this.assistant.getConversation(id).subscribe({
      next: (conv) => {
        this.conversationId = conv.id;
        this.bankCode = conv.bank_code ?? '';
        this.messages = conv.messages.filter(
          (m) =>
            m.role === 'user' ||
            m.role === 'assistant'
        );
        this.shouldScroll = true;
      },
      error: () => {
        this.error = 'Could not load conversation.';
      },
    });
  }

  send(): void {
    const text = this.draft.trim();
    if (!text || this.sending) {
      return;
    }

    this.error = null;
    this.sending = true;

    // Optimistically render the user turn.
    this.messages = [
      ...this.messages,
      this.localMessage('user', text),
    ];
    this.draft = '';
    this.shouldScroll = true;

    this.assistant
      .chat(
        text,
        this.conversationId ?? undefined,
        this.bankCode || undefined
      )
      .subscribe({
        next: (res) => {
          this.conversationId = res.conversation_id;
          this.messages = [
            ...this.messages,
            res.message,
          ];
          this.sending = false;
          this.shouldScroll = true;
          this.loadConversations();
        },
        error: (err: HttpErrorResponse) => {
          this.sending = false;
          this.error =
            err.status === 0
              ? 'Cannot reach the server.'
              : `Request failed (${err.status}).`;
        },
      });
  }

  onKeydown(event: KeyboardEvent): void {
    if (
      event.key === 'Enter' &&
      !event.shiftKey
    ) {
      event.preventDefault();
      this.send();
    }
  }

  hasGaps(message: ChatMessage): boolean {
    return message.citations.some(
      (c) => c.data_gaps && c.data_gaps.length > 0
    );
  }

  gapList(message: ChatMessage) {
    return message.citations.flatMap(
      (c) => c.data_gaps ?? []
    );
  }

  private localMessage(
    role: 'user' | 'assistant',
    content: string
  ): ChatMessage {
    return {
      id: `local-${Date.now()}`,
      role,
      content,
      citations: [],
      model_used: '',
      is_fallback: false,
      created_at: new Date().toISOString(),
    };
  }

  private scrollToBottom(): void {
    this.scrollAnchor?.nativeElement.scrollIntoView({
      behavior: 'smooth',
    });
  }
}
