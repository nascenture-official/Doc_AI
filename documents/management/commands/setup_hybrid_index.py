import os
import time

from django.core.management.base import BaseCommand
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

EMBEDDING_DIM = 1536  # text-embedding-3-small


class Command(BaseCommand):
    help = "Creates a Pinecone index with dotproduct metric for hybrid search (if it doesn't exist)."

    def handle(self, *args, **options):
        api_key = os.getenv("PINECONE_API_KEY")
        index_name = os.getenv("PINECONE_INDEX_NAME", "doc-chat-index")
        cloud = os.getenv("PINECONE_CLOUD", "aws")
        region = os.getenv("PINECONE_REGION", "us-east-1")

        if not api_key:
            self.stderr.write(self.style.ERROR("PINECONE_API_KEY is not set in environment."))
            return

        pc = Pinecone(api_key=api_key)
        existing = [idx.name for idx in pc.list_indexes()]

        if index_name in existing:
            index_info = pc.describe_index(index_name)
            metric = index_info.metric
            self.stdout.write(
                self.style.WARNING(
                    f"Index '{index_name}' already exists (metric={metric})."
                )
            )
            if metric != "dotproduct":
                self.stderr.write(
                    self.style.ERROR(
                        f"Index uses '{metric}' metric. Hybrid search requires 'dotproduct'.\n"
                        f"Set PINECONE_INDEX_NAME to a new name and re-run this command to create a fresh index."
                    )
                )
            else:
                self.stdout.write(self.style.SUCCESS("Index is ready for hybrid search."))
            return

        self.stdout.write(f"Creating index '{index_name}' (dim={EMBEDDING_DIM}, metric=dotproduct, {cloud}/{region})...")
        pc.create_index(
            name=index_name,
            dimension=EMBEDDING_DIM,
            metric="dotproduct",
            spec=ServerlessSpec(cloud=cloud, region=region),
        )

        # Wait for the index to be ready
        for _ in range(30):
            info = pc.describe_index(index_name)
            if info.status.get("ready", False):
                break
            time.sleep(2)

        self.stdout.write(self.style.SUCCESS(f"Index '{index_name}' created and ready."))
        self.stdout.write(
            "Next step: run 'python manage.py reindex_hybrid' to re-upsert existing documents."
        )
