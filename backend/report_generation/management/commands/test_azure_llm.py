from django.core.management.base import BaseCommand

from generation_engine.llm.azure_client import AzureURLLLMClient


class Command(BaseCommand):
    help = "Smoke test the Azure LLM client."

    def handle(self, *args, **options):
        client = AzureURLLLMClient()

        response = client.generate_writer_text(
            system_prompt=(
                "You are a concise assistant. Return only one sentence."
            ),
            user_prompt=(
                "Write one sentence confirming that the IFRS report generation "
                "LLM client is working."
            ),
            temperature=0.0,
            max_tokens=80,
        )

        self.stdout.write(self.style.SUCCESS("Azure LLM client works."))
        self.stdout.write("")
        self.stdout.write(response.content)