import {
  Component,
  ElementRef,
  NgZone,
  OnInit,
  ViewChild,
  AfterViewChecked,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import {
  AssistantService,
  ChatMessage,
  ConversationSummary,
  StreamEvent,
} from '../../core/services/assistant';
import {
  Risk as RiskService,
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
  streamStatus: string | null = null;
  error: string | null = null;

  private shouldScroll = false;

  private readonly decimalRe =
    /(?<![\d.])(\d+\.\d+)(?!\.?\d)/g;

  constructor(
    private assistant: AssistantService,
    private risk: RiskService,
    private zone: NgZone
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

  get selectedBankName(): string {
    return (
      this.banks.find(
        (bank) =>
          bank.code === this.bankCode
      )?.name ?? ''
    );
  }

  private loadBanks(): void {
    this.risk
      .getPayloadManifests()
      .subscribe({
        next: (manifests) => {
          const seen =
            new Set<string>();
          const options:
            BankOption[] = [];

          for (const manifest of manifests) {
            if (
              manifest.bank_code &&
              !seen.has(
                manifest.bank_code
              )
            ) {
              seen.add(
                manifest.bank_code
              );
              options.push({
                code:
                  manifest.bank_code,
                name:
                  manifest.bank_name,
              });
            }
          }

          this.banks = options.sort(
            (a, b) =>
              a.name.localeCompare(
                b.name
              )
          );
        },
        error: () => {},
      });
  }

  private loadConversations(): void {
    this.assistant
      .listConversations()
      .subscribe({
        next: (list) => {
          this.conversations =
            list;
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

  openConversation(
    id: string
  ): void {
    this.assistant
      .getConversation(id)
      .subscribe({
        next: (conversation) => {
          this.conversationId =
            conversation.id;
          this.bankCode =
            conversation.bank_code
            ?? '';
          this.messages =
            conversation.messages.filter(
              (message) =>
                message.role ===
                  'user' ||
                message.role ===
                  'assistant'
            );
          this.shouldScroll = true;
        },
        error: () => {
          this.error =
            'Could not load conversation.';
        },
      });
  }

  useSuggestion(
    question: string
  ): void {
    this.draft = question;
    this.send();
  }

  send(): void {
    const text =
      this.draft.trim();

    if (!text || this.sending) {
      return;
    }

    this.error = null;
    this.sending = true;
    this.streamStatus = null;

    const assistantMessage =
      this.localMessage(
        'assistant',
        ''
      );
    assistantMessage.streaming =
      true;

    this.messages = [
      ...this.messages,
      this.localMessage(
        'user',
        text
      ),
      assistantMessage,
    ];

    this.draft = '';
    this.resetComposerHeight();
    this.shouldScroll = true;

    this.assistant
      .chatStream(
        text,
        this.conversationId
          ?? undefined,
        this.bankCode
          || undefined
      )
      .subscribe({
        next: (event) =>
          this.zone.run(() =>
            this.handleStreamEvent(
              event,
              assistantMessage
            )
          ),
        error: () =>
          this.zone.run(() => {
            this.error =
              'Cannot reach the server.';
            assistantMessage.streaming =
              false;
            this.sending = false;
            this.streamStatus = null;
          }),
        complete: () =>
          this.zone.run(() => {
            assistantMessage.streaming =
              false;
            this.sending = false;
            this.streamStatus = null;
          }),
      });
  }

  private handleStreamEvent(
    event: StreamEvent,
    target: ChatMessage
  ): void {
    switch (event.type) {
      case 'status':
        this.streamStatus =
          event.text;
        break;

      case 'token':
        target.content +=
          event.text;
        this.streamStatus = null;
        this.shouldScroll = true;
        break;

      case 'citations':
        target.citations =
          event.citations;
        break;

      case 'done':
        this.conversationId =
          event.conversation_id;
        target.model_used =
          event.model_used;
        target.is_fallback =
          event.is_fallback;
        target.streaming = false;
        this.sending = false;
        this.streamStatus = null;
        this.shouldScroll = true;
        this.loadConversations();
        break;

      case 'error':
        this.error =
          event.message;
        target.streaming = false;
        this.sending = false;
        this.streamStatus = null;
        break;
    }

    this.messages = [
      ...this.messages,
    ];
  }

  onKeydown(
    event: KeyboardEvent
  ): void {
    if (
      event.key === 'Enter' &&
      !event.shiftKey
    ) {
      event.preventDefault();
      this.send();
    }
  }

  autoGrow(event: Event): void {
    const element = event.target;

    if (!(element instanceof HTMLTextAreaElement)) {
      return;
    }

    element.style.height = 'auto';
    element.style.height = `${Math.min(
      element.scrollHeight,
      160
    )}px`;
  }

  private resetComposerHeight():
    void {
    const element =
      document.querySelector(
        '.composer textarea'
      ) as
        | HTMLTextAreaElement
        | null;

    if (element) {
      element.style.height =
        'auto';
    }
  }

  hasGaps(
    message: ChatMessage
  ): boolean {
    return message.citations.some(
      (citation) =>
        citation.data_gaps &&
        citation.data_gaps.length > 0
    );
  }

  gapList(
    message: ChatMessage
  ) {
    return message.citations.flatMap(
      (citation) =>
        citation.data_gaps
        ?? []
    );
  }

  renderContent(
    text: string
  ): string {
    if (!text) {
      return '';
    }

    let output = text
      .replace(
        /[ \t]+\n/g,
        '\n'
      )
      .replace(
        /\n{2,}/g,
        '\n'
      )
      .trim();

    output = output
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    output = output.replace(
      this.decimalRe,
      (match) => {
        const number =
          Number(match);

        return isFinite(number)
          ? number.toLocaleString(
              'en-US',
              {
                maximumFractionDigits:
                  3,
              }
            )
          : match;
      }
    );

    output = output
      .replace(
        /\*\*(.+?)\*\*/g,
        '<strong>$1</strong>'
      )
      .replace(
        /`([^`]+)`/g,
        '<code>$1</code>'
      );

    return output;
  }

  private localMessage(
    role: 'user' | 'assistant',
    content: string
  ): ChatMessage {
    return {
      id:
        `local-${Date.now()}-`
        + Math.random()
          .toString(36)
          .slice(2, 8),
      role,
      content,
      citations: [],
      model_used: '',
      is_fallback: false,
      created_at:
        new Date().toISOString(),
    };
  }

  private scrollToBottom():
    void {
    this.scrollAnchor
      ?.nativeElement
      .scrollIntoView({
        behavior: 'smooth',
      });
  }
}
