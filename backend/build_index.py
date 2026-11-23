import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.config import settings
from app.services.rag import RAGService

def main():
    print("=" * 60)
    print("NetraCare Knowledge Base Indexer (Iteration 3)")
    print("=" * 60)
    print(f"Data directory: {settings.resolved_iter3_data_dir / 'documents'}")
    print(f"Chroma persist directory: {settings.resolved_chroma_dir}")
    print(f"Embedding model: {settings.EMBEDDING_MODEL}")
    
    chunks = RAGService.load_and_chunk_documents()
    print(f"Extracted {len(chunks)} chunks across the 3 clinic documents.")

    # Show section summary
    sections_by_doc = {}
    for c in chunks:
        sections_by_doc.setdefault(c.source, set()).add(c.section)

    for doc, secs in sections_by_doc.items():
        print(f"  - {doc}: {len(secs)} sections")

    print("\nBuilding and persisting Chroma vector index...")
    try:
        count = RAGService.build_index()
        print(f"SUCCESS: Indexed and persisted {count} chunks in Chroma collection 'netracare_kb'.")
    except Exception as e:
        print(f"ERROR: Failed to build index: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
