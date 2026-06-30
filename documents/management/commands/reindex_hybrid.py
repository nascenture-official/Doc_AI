from django.core.management.base import BaseCommand

from documents.models import Document
from documents.services.pdf_processor import extract_and_chunk_pdf
from documents.services.vector_store import create_vector_index, delete_vector_index


class Command(BaseCommand):
    help = "Re-upserts all ready documents with hybrid (dense+sparse) vectors for Pinecone hybrid search."

    def add_arguments(self, parser):
        parser.add_argument(
            "--doc-id",
            type=int,
            help="Re-index a single document by ID (omit to re-index all ready documents).",
        )

    def handle(self, *args, **options):
        doc_id = options.get("doc_id")

        if doc_id:
            qs = Document.objects.filter(id=doc_id)
            if not qs.exists():
                self.stderr.write(self.style.ERROR(f"Document with id={doc_id} not found."))
                return
        else:
            qs = Document.objects.filter(status="ready")

        total = qs.count()
        self.stdout.write(f"Re-indexing {total} document(s)...")

        success = 0
        failed = 0

        for doc in qs:
            try:
                self.stdout.write(f"  Processing: {doc.title} (id={doc.id})")
                delete_vector_index(doc.id)
                chunks = extract_and_chunk_pdf(doc.file.path, doc.title)
                create_vector_index(doc.id, doc.user_id, chunks)
                self.stdout.write(self.style.SUCCESS(f"    Done — {len(chunks)} chunks"))
                success += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"    Failed: {e}"))
                failed += 1

        self.stdout.write(f"\nFinished: {success} succeeded, {failed} failed.")
