"""
Materialise the retrieval corpus into the Qdrant vector index.

    python manage.py index_corpus             # every process
    python manage.py index_corpus --recreate  # drop and rebuild the collection

The corpus of record is ``processes.CorpusDocument``; the index is derived
from it with the BGE embedder, so it has to be rebuilt whenever the corpus is
(``import_benchmark`` rebuilds the corpus).  The retrievers recall their
candidates from this index; without it they fall back to scoring every
document of the process in-process.
"""
import time

from django.core.management.base import BaseCommand, CommandError

from apps.processes.models import CorpusDocument, Process
from carma_engine.retriever.embedder import BGEEmbedder


class Command(BaseCommand):
    help = 'Embed the retrieval corpus with BGE and upsert it into Qdrant.'

    def add_arguments(self, parser):
        parser.add_argument('--recreate', action='store_true',
                            help='Drop the collection before indexing.')

    def handle(self, *args, **options):
        try:
            embedder = BGEEmbedder()
        except Exception as exc:
            raise CommandError(f'The BGE embedder or Qdrant is not available: {exc}') from exc

        if options['recreate']:
            embedder.qdrant.delete_collection(embedder.collection)
            # The server removes the collection asynchronously.
            for _ in range(60):
                if not embedder.qdrant.collection_exists(embedder.collection):
                    break
                time.sleep(0.5)
            embedder._ensure_collection()

        for process in Process.objects.order_by('name'):
            documents = CorpusDocument.objects.filter(process=process).order_by('id')
            indexed = embedder.index_documents(documents)
            self.stdout.write(f'{process.name}: {indexed} documents indexed '
                              f'({embedder.count(str(process.id))} in the index)')

        self.stdout.write(self.style.SUCCESS(
            f'Done — {embedder.count()} documents in "{embedder.collection}".'))
